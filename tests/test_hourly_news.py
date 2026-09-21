import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hourly', ROOT / 'pharma-news/scripts/send_hourly_news.py')
news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(news)


class HourlyNewsTests(unittest.TestCase):
    def test_naver_subheading_photo_table_and_publisher_are_removed(self):
        from unittest.mock import Mock
        body = '현대자동차는 수소 사업 확대를 위한 일관된 정책 지원이 필요하다고 밝혔다.'
        html = ('<article id="dic_area"><strong class="media_end_summary">부사장 토론회 참석<br>장기 투자 요구</strong>'
                '<table><tr><td><table><tr><td><img src="photo.jpg"></td></tr>'
                '<tr><td>부사장은 현장에서 인터뷰를 하고 있다. (사진=공동취재단)</td></tr></table></td></tr></table>'
                '[파이낸셜뉴스]' + body + '</article>')
        with patch.object(news.requests, 'get', return_value=Mock(text=html)):
            self.assertEqual(news.get_article_summary('https://example.com'), body)

    def test_press_labels_removed_without_losing_business_content(self):
        body = '회사는 [ESS] 사업의 공급계약을 체결하고 해외 공장 생산을 확대한다고 밝혔다.'
        self.assertEqual(news.compact_summary('(사진=공동취재단) [파이낸셜뉴스]' + body), body)
        self.assertEqual(news.compact_summary('[사진] [이데일리]' + body), body)

    def test_research_report_hidden_behind_neutral_headline(self):
        title = 'LG에너지솔루션, 실적 개선세 지속'
        body = 'iM증권은 LG에너지솔루션의 목표주가 55만원, 투자의견 매수를 유지했다.'
        self.assertTrue(news.is_research_report(title, body))
        self.assertTrue(news.is_invalid('셀트리온 목표가 상향…성장 기대'))
        self.assertTrue(news.is_research_report('실적 개선 기대', '박정하 연구원은 신규 수주가 확대될 것으로 전망했다.'))
        self.assertFalse(news.is_research_report('LG에너지솔루션, ESS 공급계약 체결', '회사는 해외 고객과 공급계약을 체결했다고 밝혔다.'))

    def test_research_report_is_skipped_in_favor_of_company_event(self):
        research = ('LG에너지솔루션, 실적 개선세 지속', 'https://example.com/report', 200)
        event = ('새빛테크, 해외 공급계약 체결', 'https://example.com/event', 100)
        with patch.object(news, 'fetch_popular_articles', return_value=[research, event]), patch.object(news, 'fetch_articles', return_value=[]), patch.object(news, 'get_article_date', return_value=news.datetime.now(news.KST).date()), patch.object(news, 'get_article_summary', side_effect=['iM증권은 목표주가 55만원을 유지했다.', '해외 고객과 공급계약을 체결했다.']):
            self.assertEqual(news.pick_best_article([], [], {}), event[:2])

    def test_actual_celltrion_buyback_cancellation_republication(self):
        records = json.loads((ROOT / 'tests/fixtures/celltrion_duplicate.json').read_text(encoding='utf-8'))
        first, second = [row for row in records if row['title'].startswith('셀트리온,')][-2:]
        first = dict(first, date=news.datetime.now(news.KST).date().isoformat())
        self.assertTrue(news.already_covered(second['title'], second['url'], [first], second['summary']))

    def test_company_event_dedup_is_not_limited_to_company_allowlist(self):
        today = news.datetime.now(news.KST).date().isoformat()
        previous = [{'title': '새빛테크, 1000억원 자사주 소각 결정', 'date': today}]
        self.assertTrue(news.already_covered('새빛테크, 주주가치 높인다', 'https://example.com/new', previous,
                                            '자기주식 962억원을 소각하기로 했다.'))
        self.assertFalse(news.already_covered('다른기업, 1000억원 자사주 소각', 'https://example.com/new', previous))
        self.assertFalse(news.already_covered('새빛테크, 신약 임상 성공', 'https://example.com/new', previous))
        previous[0]['date'] = '2020-01-01'
        self.assertFalse(news.already_covered('새빛테크, 주주가치 높인다', 'https://example.com/new', previous,
                                             '자기주식 962억원을 소각하기로 했다.'))

    def test_same_battery_order_issue_across_companies_is_skipped_today(self):
        records = [{'title': 'LG에너지솔루션, 하반기 대규모 수주 예상…매수 기회',
                    'date': news.datetime.now(news.KST).date().isoformat()}]
        self.assertTrue(news.already_covered('ESS 성장에 수주 경쟁력 강화…삼성SDI 목표가 상향', 'https://example.com/new', records))
        self.assertFalse(news.already_covered('삼성SDI, 신형 배터리 공개', 'https://example.com/new', records))
        records[0]['date'] = '2020-01-01'
        self.assertFalse(news.already_covered('삼성SDI ESS 공급계약 체결', 'https://example.com/new', records))

    def test_same_url_and_republished_content_are_duplicates(self):
        body = '기업은 해외 생산 공장의 신규 공급계약을 체결했다. 이번 계약은 현지 공장의 생산 규모 확대를 위한 것이다.'
        records = [{'title': '첫 번째 기사 제목', 'url': 'https://n.news.naver.com/mnews/article/018/123?sid=101', 'summary': body}]
        self.assertTrue(news.already_covered('완전히 바뀐 기사 제목', 'https://n.news.naver.com/article/018/123', records))
        self.assertTrue(news.already_covered('다른 언론사의 기사 제목', 'https://example.com/2', records, body))
        self.assertTrue(news.similar_text('HD현대그룹 주가 불기둥…기대치 웃돈 성장사업 베팅 [줍줍리포트]',
                                          'HD현대그룹 주가 불기둥…기대치 웃돈 성장사업 베팅'))

    def test_duplicate_summary_advances_to_next_candidate(self):
        first = ('새빛테크, 해외 공급계약 체결', 'https://example.com/first', 100)
        second = ('다른기업, 신약 임상 성공 발표', 'https://example.com/second', 90)
        body = '기업은 해외 생산 공장의 신규 공급계약을 체결했다. 이번 계약은 현지 공장의 생산 규모 확대를 위한 것이다.'
        records = [{'title': '이전 발송 기사', 'summary': body}]
        summaries = {}
        with patch.object(news, 'fetch_popular_articles', return_value=[first, second]), patch.object(news, 'fetch_articles', return_value=[]), patch.object(news, 'get_article_date', return_value=news.datetime.now(news.KST).date()), patch.object(news, 'get_article_summary', side_effect=[body, '새로운 임상 결과를 발표했다.']):
            self.assertEqual(news.pick_best_article([], records, summaries), second[:2])

    def test_article_history_persists_summary_url_and_date(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(news, 'ARTICLE_LOG_PATH', str(Path(directory) / 'articles.json')):
                news.save_sent_article([], ('새 기업 공급계약', 'https://example.com/1'), '기사 내용')
                records = news.load_sent_articles()
                self.assertEqual(records[0]['summary'], '기사 내용')
                self.assertEqual(records[0]['date'], news.datetime.now(news.KST).date().isoformat())

    def test_summary_removes_dateline_with_optional_reporter(self):
        body = '오픈AI가 금융회사의 주식 리서치를 지원하는 서비스를 출시했다.'
        for prefix in ['(서울=연합뉴스) ', '(샌프란시스코 = 연합뉴스) 김철수 특파원 = ', '[서울=뉴시스] ']:
            self.assertEqual(news.compact_summary(prefix + body), body)
        ordinary = '(잠정 실적) 회사는 올해 매출이 지난해보다 크게 증가했다고 밝혔다.'
        self.assertEqual(news.compact_summary(ordinary), ordinary)

    def test_appliance_launches_excluded_but_material_company_news_kept(self):
        for title in ['LG전자, 차세대 OLED TV 출시', '삼성전자 AI 냉장고 신제품 공개',
                      'LG전자, 프리미엄 가전 선보인다', '새로운 로봇청소기 사전예약 시작']:
            self.assertTrue(news.is_invalid(title), title)
        for title in ['오픈AI, 주식리서치 특화 챗GPT 출시',
                      'LG전자, 가전 사업 영업이익 사상 최대', 'LG전자 TV 사업부 매각 추진']:
            self.assertFalse(news.is_invalid(title), title)

    def test_summary_preserves_decimal_and_limits_sentences(self):
        first = 'SOL AI반도체소부장 ETF의 최근 1개월 수익률은 23.14%를 기록했다.'
        second = 'AI 인프라 투자 확대와 반도체 업황 회복이 영향을 줬다.'
        summary = news.compact_summary(first + ' ' + second + ' ' + second)
        self.assertEqual(summary, first + '\n\n' + second)

    def test_long_sentence_and_incomplete_tail_do_not_overflow(self):
        summary = news.compact_summary('반도체 기업의 실적 개선 기대가 높아지고 있다. 미완성 문장')
        self.assertEqual(summary, '반도체 기업의 실적 개선 기대가 높아지고 있다.')
        self.assertEqual(news.compact_summary('가' * 651 + '. 다음 문장은 앞 문장을 건너뛰어 발췌하지 않는다.'), '')
        self.assertLessEqual(len(summary), 650)

    def test_telegram_escapes_article_html(self):
        with patch.object(news, 'get_article_summary', return_value='실적 <개선> & 성장.\n\n두 번째 문장.'):
            msg = news.build_message(('반도체 <기업> & 실적', 'https://example.com/?a=1&b=2'))
        self.assertIn('&lt;기업&gt; &amp;', msg)
        self.assertEqual(msg, '🔜 <b>반도체 &lt;기업&gt; &amp; 실적</b>\n\n실적 &lt;개선&gt; &amp; 성장.\n\n두 번째 문장.\n\nhttps://example.com/?a=1&amp;b=2')

    def test_product_news_is_excluded_even_with_company_event(self):
        for title in ['신한운용 SOL AI반도체 ETF 순자산 1조 돌파',
                      '삼성자산운용, 반도체 신제품 etf 출시',
                      '반도체 수주 기업 담은 펀드 수익률 1위']:
            self.assertTrue(news.is_invalid(title), title)

    def test_company_events_include_small_companies_and_negative_events(self):
        for title in ['새빛테크, 글로벌 고객과 공급계약 체결',
                      '한미약품 신약 임상 3상 성공', '삼성전자 대규모 리콜 발표']:
            self.assertFalse(news.is_invalid(title), title)
            self.assertTrue(news.has_company_event(title), title)
        self.assertFalse(news.has_company_event('반도체 AI 기대감에 코스피 상승'))

    def test_no_matching_company_event_skips_round(self):
        with patch.object(news, 'fetch_popular_articles', return_value=[]), patch.object(news, 'fetch_articles', return_value=[('신한운용 반도체 ETF 수익률 1위', 'https://example.com', 99)]):
            self.assertIsNone(news.pick_best_article([]))

    def test_excerpt_uses_original_sentences_in_order(self):
        sentences = [f'기업은 신규 생산 시설에 대한 투자 계획 {i}단계를 공개했다.' for i in range(4)]
        self.assertEqual(news.compact_summary(' '.join(sentences)), sentences[0] + '\n\n' + ' '.join(sentences[1:3]))

    def test_naver_mobile_article_is_collected_but_external_host_is_not(self):
        from unittest.mock import Mock
        html = '<a href="https://n.news.naver.com/mnews/article/001/123">새빛테크, 글로벌 공급계약 체결</a><a href="https://example.com/news.naver.com/article">다른기업, 글로벌 공급계약 체결</a>'
        with patch.object(news.requests, 'get', return_value=Mock(text=html)):
            articles = news.fetch_articles('https://news.naver.com/list', 'https://news.naver.com', 'article')
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0][1], 'https://n.news.naver.com/mnews/article/001/123')

    def test_history_keeps_chronological_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sent.json'
            path.write_text(json.dumps(['old', 'middle', 'new']), encoding='utf-8')
            with patch.object(news, 'SENT_LOG_PATH', str(path)), patch.object(news, 'SENT_LOG_KEEP', 3):
                news.save_sent_titles(news.load_sent_titles(), 'latest')
                self.assertEqual(news.load_sent_titles(), ['middle', 'new', 'latest'])

    def test_workflow_uses_persistent_runner_and_current_ledger(self):
        import yaml
        workflow = (ROOT / '.github/workflows/hourly_news.yml').read_text(encoding='utf-8')
        config = yaml.load(workflow, Loader=yaml.BaseLoader)
        self.assertEqual(config['concurrency']['cancel-in-progress'], 'false')
        job = config['jobs']['send-news']
        self.assertEqual(job['steps'][0]['with']['ref'], 'main')
        self.assertIn('hourly_news_runner.py run', workflow)
        self.assertLessEqual(int(job['timeout-minutes']), 360)

    def test_send_window_uses_korea_time_and_allows_delayed_final_run(self):
        from datetime import datetime, timezone
        for hour, expected in [(7, False), (8, True), (16, True), (17, False)]:
            now = datetime(2026, 9, 9, hour, 30, tzinfo=news.KST)
            self.assertEqual(news.in_send_window(now.astimezone(timezone.utc)), expected)

    def test_popular_parser_filters_products_and_non_business_press(self):
        from unittest.mock import Mock
        def item(press, rank, title):
            return f'<li><em class="list_ranking_num">{rank}위</em><a class="list_title" href="https://n.news.naver.com/article/{press}/123?ntype=RANKING">{title}</a></li>'
        html = '<div class="rankingnews_box"><ul class="rankingnews_list">' + ''.join([
            item('015', 2, '새빛테크, 해외 공급계약 체결'),
            item('009', 1, '반도체 ETF 신제품 수익률 1위'),
            item('025', 1, '유명인 소송 새로운 소식 공개'),
        ]) + '</ul></div>'
        with patch.object(news.requests, 'get', return_value=Mock(text=html)):
            result = news.fetch_popular_articles()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 'https://n.news.naver.com/article/015/123')
        self.assertEqual(result[0][2], news.get_priority(result[0][0]) + 40)

    def test_major_companies_and_growth_news_are_eligible(self):
        for title in ['애플 차세대 아이폰 공개 행사 예고', '삼성전자 글로벌 전략 새판 짠다', '한화에어로스페이스 유럽 생산시설 투자 확대']:
            self.assertTrue(news.has_company_event(title))
            self.assertFalse(news.is_invalid(title))
        self.assertGreater(news.get_priority('삼성전자 차세대 반도체 양산'), news.get_priority('기업 소송 관련 새 소식'))
        self.assertGreater(news.get_priority('삼성전자 신제품 출시'), news.get_priority('삼성전자 신제품 출시 취소'))

    def test_mk_title_excludes_long_preview(self):
        from unittest.mock import Mock
        html = '<a href="/news/view/123"><h3 class="news_ttl">삼성전자 신제품 공개 예고</h3><p>' + '미리보기 ' * 100 + '</p></a>'
        with patch.object(news.requests, 'get', return_value=Mock(text=html)):
            result = news.fetch_articles('https://stock.mk.co.kr/news/company', 'https://stock.mk.co.kr', '/news/view/')
        self.assertEqual(result[0][0], '삼성전자 신제품 공개 예고')

    def test_popular_article_beats_keyword_score_and_stale_is_skipped(self):
        today = news.datetime.now(news.KST).date()
        popular = ('새빛테크, 해외 공급계약 체결', 'https://example.com/popular', 14020)
        ordinary = ('삼성전자 반도체 양산 수주 신제품 공개', 'https://example.com/ordinary', 80)
        with patch.object(news, 'fetch_popular_articles', return_value=[popular]), patch.object(news, 'fetch_articles', return_value=[ordinary]):
            with patch.object(news, 'get_article_date', return_value=today):
                self.assertEqual(news.pick_best_article([]), popular[:2])
            with patch.object(news, 'get_article_date', side_effect=[today - news.timedelta(days=1), today]):
                self.assertEqual(news.pick_best_article([]), ordinary[:2])
            with patch.object(news, 'get_article_date', return_value=None):
                self.assertIsNone(news.pick_best_article([]))


if __name__ == '__main__':
    unittest.main()
