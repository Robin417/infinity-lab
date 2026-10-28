# 네이버 증권 실시간 속보 크롤러

대상: https://stock.naver.com/news/flashnews

Python 3.10 이상. 외부 패키지나 브라우저 설치 없이 사이트에서 사용하는 뉴스 목록 요청을 재현합니다.

## 실행

```bash
cd naver-flashnews
# 한국 시간 오늘, 최신순 최대 3페이지 (페이지당 15개)
python3 crawler.py
# 특정 날짜를 CSV로 저장
python3 crawler.py --date 2026-10-28 --pages 10 --format csv --output output/news.csv
# 조회한 페이지 내 제목·요약 검색
python3 crawler.py --pages 10 --keyword 반도체 --output output/semiconductor.json
```

수집 필드: `office_id`, `article_id`, `title`, `publisher`, `published_at`, `summary`, `url`, `thumbnail_url`.
ID는 앞자리 0을 보존하는 문자열, 발행 시간은 UTC+09:00입니다. 요약은 목록 제공 내용이며 기사 전문은 수집하지 않습니다.
CSV는 한글 Excel용 UTF-8 BOM을 사용하며 수식으로 해석될 수 있는 문자열 앞에 작은따옴표를 붙입니다.

## 옵션

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--date` | 한국 시간 오늘 | YYYY-MM-DD 날짜, 지정 날짜만 수집 |
| `--pages` | 3 | 최대 요청 페이지 수 |
| `--page-size` | 15 | 페이지당 1~15개 |
| `--delay` | 1 | 페이지 사이 대기 초, 최소 1초 |
| `--timeout` | 30 | 요청 제한 시간(초) |
| `--retries` | 3 | 일시적 오류 재시도 횟수(0~10) |
| `--keyword` | 없음 | 제목·요약 필터, 서버 검색 아님 |
| `--format` | json | json 또는 csv |
| `--output` | news-YYYY-MM-DD.json | 저장 경로, 형식은 --format으로 결정 |

기존 출력 파일은 성공한 실행 결과로 교체합니다. 한 실행 내에서 언론사 ID·기사 ID 기준으로 중복을 제거합니다.
실행 간 누적 기능은 없습니다. 날짜 전체 수집은 충분한 `--pages`를 지정하세요.
빈 페이지, 짧은 마지막 페이지, 새 기사가 없는 페이지에서 종료하며 이전 날짜로 자동 이동하지 않습니다.
기사가 없으면 빈 JSON 배열 또는 CSV 헤더를 저장합니다.

네트워크 오류 및 HTTP 429/500/502/503/504는 재시도합니다. 응답 구조 변경이나 요청 실패는 종료 코드 1,
잘못된 인수는 2를 반환합니다. 실패 시 기존 출력 파일은 보존합니다.
수집 중 목록이 바뀌면 페이지 경계에서 일부 기사가 누락될 수 있어 완전한 실시간 아카이브를 보장하지 않습니다.

## 검증

```bash
python3 -m unittest discover -s tests -v
python3 crawler.py --pages 2 --output /tmp/naver-news-smoke.json
```

2026-10-28 사이트의 배포 JavaScript 및 실제 응답에서 다음 요청을 확인했습니다.

```text
GET https://stock.naver.com/api/domestic/news/list?category=FLASHNEWS&page=1&pageSize=15&date=20261028
```

응답은 `articles` 배열과 `date`, `isFirstDate`를 포함합니다. 사이트 내부 API이므로 향후 변경될 수 있습니다.
운영 시 사이트 이용조건과 콘텐츠 이용 범위를 확인하고 요청 간격을 유지하세요. 자동 주기 실행은 설정하지 않았습니다.
