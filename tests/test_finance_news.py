import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('finance', Path(__file__).resolve().parents[1] / 'pharma-news/scripts/send_finance_news.py')
finance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finance)

class FinanceTests(unittest.TestCase):
    def test_modern_links_and_deduplication(self):
        response = Mock(text='<a class="sa_text_title" href="https://n.news.naver.com/mnews/article/018/123?x=1">Company reports record earnings</a>' * 2)
        with patch.object(finance.requests, 'get', return_value=response):
            self.assertEqual(finance.fetch_naver_finance(), [('Company reports record earnings', 'https://n.news.naver.com/mnews/article/018/123')])
        self.assertEqual(response.encoding, 'utf-8')

    def test_request_failure_falls_back(self):
        response = Mock(text='<a class="sa_text_title" href="https://n.news.naver.com/mnews/article/018/123">Company reports record earnings</a>')
        with patch.object(finance.requests, 'get', side_effect=[finance.requests.Timeout(), response]):
            self.assertEqual(len(finance.fetch_naver_finance(limit=1)), 1)

    def test_empty_collection_never_sends(self):
        with patch.object(finance, 'fetch_naver_finance', return_value=[]), patch.object(finance.time, 'sleep'), patch.object(finance, 'send_telegram') as send:
            with self.assertRaises(RuntimeError):
                finance.main()
            send.assert_not_called()
        with self.assertRaises(RuntimeError):
            finance.build_message([])

    def test_transient_empty_recovers(self):
        articles = [('Company reports record earnings', 'https://example.com')]
        with patch.object(finance, 'fetch_naver_finance', side_effect=[[], articles]), patch.object(finance.time, 'sleep'):
            self.assertEqual(finance.collect_with_retry(), articles)
