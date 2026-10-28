import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import crawler


def article(aid='0000000001', date='2026-10-28 09:30:00'):
    return dict(officeId='001', articleId=aid, title='금융 &amp; 경제',
                datetime=date, officeHname='언론사', subcontent='<b>요약</b>')


class Tests(unittest.TestCase):
    def test_normalize(self):
        row = crawler.normalize(article())
        self.assertEqual(row['title'], '금융 & 경제')
        self.assertEqual(row['summary'], '요약')
        self.assertEqual(row['published_at'], '2026-10-28T09:30:00+09:00')
        self.assertEqual(row['url'], 'https://n.news.naver.com/article/001/0000000001')

    @patch('crawler.time.sleep')
    @patch('crawler.fetch_page')
    def test_dedup_and_exact_date(self, fetch, sleep):
        fetch.side_effect = [dict(articles=[article(), article('2')]),
                             dict(articles=[article('2'), article('3', '2026-10-27 23:59:00')])]
        self.assertEqual(len(crawler.crawl('2026-10-28', pages=5, page_size=2)), 2)
        self.assertEqual(fetch.call_count, 2)

    @patch('crawler.fetch_page', return_value={'articles': [article()]})
    def test_keyword(self, fetch):
        self.assertEqual(crawler.crawl('2026-10-28', keyword='없는단어'), [])
        self.assertEqual(len(crawler.crawl('2026-10-28', keyword='금융')), 1)

    @patch('crawler.urlopen')
    def test_schema_change(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"error":"bad"}'
        with self.assertRaises(crawler.CrawlError):
            crawler.fetch_page('2026-10-28', 1)

    @patch('crawler.time.sleep')
    @patch('crawler.urlopen')
    def test_retry(self, urlopen, sleep):
        urlopen.side_effect = HTTPError('url', 503, 'unavailable', {}, None)
        with self.assertRaises(crawler.CrawlError):
            crawler.fetch_page('2026-10-28', 1, retries=2)
        self.assertEqual(urlopen.call_count, 3)
        urlopen.reset_mock()
        urlopen.side_effect = HTTPError('url', 403, 'forbidden', {}, None)
        with self.assertRaises(crawler.CrawlError):
            crawler.fetch_page('2026-10-28', 1, retries=2)
        self.assertEqual(urlopen.call_count, 1)

    def test_required_field(self):
        with self.assertRaises(crawler.CrawlError):
            crawler.normalize({'title': 'broken'})

    def test_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = crawler.normalize(article()); row['title'] = '=1+1'
            p = Path(tmp) / 'news.json'
            crawler.save([row], p, 'json')
            self.assertEqual(json.loads(p.read_text())[0]['title'], '=1+1')
            p = p.with_suffix('.csv'); crawler.save([row], p, 'csv')
            with p.open(encoding='utf-8-sig') as f:
                self.assertEqual(next(csv.DictReader(f))['title'], "'=1+1")

if __name__ == '__main__':
    unittest.main()
