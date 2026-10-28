#!/usr/bin/env python3
"""Collect the Naver Stock flash-news list using Python's standard library."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import html
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE = "https://stock.naver.com/news/flashnews"
ENDPOINT = "https://stock.naver.com/api/domestic/news/list"
KST = timezone(timedelta(hours=9))
FIELDS = ["office_id", "article_id", "title", "publisher", "published_at",
          "summary", "url", "thumbnail_url"]
LOG = logging.getLogger(__name__)


class CrawlError(Exception):
    pass


def clean(value):
    return html.unescape(re.sub(r"<[^>]*>", "", str(value or ""))).strip()


def fetch_page(date, page, page_size=15, timeout=30, retries=3):
    query = urlencode(dict(category="FLASHNEWS", page=page,
                           pageSize=page_size, date=date.replace("-", "")))
    request = Request(ENDPOINT + "?" + query, headers={
        "User-Agent": "NaverFlashNewsCollector/1.0", "Referer": SOURCE,
        "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
                raise CrawlError("API 응답 구조가 변경되었습니다: articles 배열이 없습니다.")
            return payload
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise CrawlError(f"HTTP {exc.code}: {exc.reason}") from exc
            try:
                delay = min(60, max(1, int(exc.headers.get("Retry-After", str(2 ** attempt)))))
            except (ValueError, TypeError):
                delay = 2 ** attempt
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == retries:
                raise CrawlError(f"네트워크 요청 실패: {exc}") from exc
            delay = 2 ** attempt
        except (ValueError, UnicodeError) as exc:
            raise CrawlError("JSON 응답을 해석할 수 없습니다.") from exc
        LOG.warning("요청 재시도 %s/%s (%ss 후)", attempt + 1, retries, delay)
        time.sleep(delay)


def normalize(article):
    if not isinstance(article, dict):
        raise CrawlError("뉴스 항목이 객체가 아닙니다.")
    for key in ("officeId", "articleId", "title", "datetime"):
        if not isinstance(article.get(key), str) or not article[key].strip():
            raise CrawlError(f"뉴스 필수 필드 누락: {key}")
    try:
        published = datetime.strptime(article["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
    except ValueError as exc:
        raise CrawlError(f"알 수 없는 날짜 형식: {article['datetime']}") from exc
    office, aid = article["officeId"], article["articleId"]
    if not office.isdigit() or not aid.isdigit():
        raise CrawlError("뉴스 ID가 숫자 문자열이 아닙니다.")
    return dict(office_id=office, article_id=aid, title=clean(article["title"]),
                publisher=clean(article.get("officeHname")),
                published_at=published.isoformat(), summary=clean(article.get("subcontent")),
                url=f"https://n.news.naver.com/article/{office}/{aid}",
                thumbnail_url=article.get("thumbUrl") or "")


def crawl(date, pages=3, page_size=15, delay=1.0, timeout=30, retries=3, keyword=None):
    rows, seen = [], set()
    for page in range(1, pages + 1):
        if page > 1:
            time.sleep(delay)
        payload = fetch_page(date, page, page_size, timeout, retries)
        articles = payload["articles"]
        if not articles:
            break
        new_count = 0
        for article in articles:
            row = normalize(article)
            # The API can return a previous date; date mode must stay exact.
            if row["published_at"][:10] != date:
                continue
            key = (row["office_id"], row["article_id"])
            if key in seen:
                continue
            seen.add(key)
            new_count += 1
            if not keyword or keyword.casefold() in (row["title"] + " " + row["summary"]).casefold():
                rows.append(row)
        LOG.info("%s 페이지 %s: %s개 응답, %s개 신규", date, page, len(articles), new_count)
        if len(articles) < page_size or new_count == 0:
            break
    return rows


def save(rows, output, fmt):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after a successful write; do not truncate previous output on errors.
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=".news-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig" if fmt == "csv" else "utf-8", newline="") as stream:
            if fmt == "csv":
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                # Prevent spreadsheet formula execution in scraped text.
                writer.writerows({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v
                                  for k, v in row.items()} for row in rows)
            else:
                json.dump(rows, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description="네이버 증권 실시간 속보 목록 수집 (Python 3.10+)")
    parser.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"), help="수집 날짜 YYYY-MM-DD (기본: 한국 오늘)")
    parser.add_argument("--pages", type=int, default=3, help="최대 페이지 수 (기본 3)")
    parser.add_argument("--page-size", type=int, default=15, help="페이지당 기사 수 1~15 (기본 15)")
    parser.add_argument("--delay", type=float, default=1, help="페이지 사이 대기 초 (최소 1)")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--keyword", help="제목·요약에 포함된 검색어")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--output", help="저장 파일 경로 (기존 파일 교체)")
    args = parser.parse_args(argv)
    try:
        if datetime.strptime(args.date, "%Y-%m-%d").strftime("%Y-%m-%d") != args.date:
            raise ValueError
    except ValueError:
        parser.error("--date는 YYYY-MM-DD 형식의 실제 날짜여야 합니다.")
    if args.pages < 1 or not 1 <= args.page_size <= 15 or args.delay < 1 or args.timeout <= 0 or not 0 <= args.retries <= 10:
        parser.error("pages >= 1, page-size 1~15, delay >= 1, timeout > 0, retries 0~10 이어야 합니다.")
    output = args.output or f"news-{args.date}.{args.format}"
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        rows = crawl(args.date, args.pages, args.page_size, args.delay, args.timeout, args.retries, args.keyword)
        save(rows, output, args.format)
    except (CrawlError, OSError) as exc:
        LOG.error("수집 실패: %s", exc)
        return 1
    LOG.info("완료: %s개 → %s", len(rows), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
