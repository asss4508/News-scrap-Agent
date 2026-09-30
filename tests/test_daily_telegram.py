import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('daily_telegram', ROOT/'pharma-news/scripts/daily_telegram.py')
bot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

class DeliveryTests(unittest.TestCase):
    def test_timeout_does_not_block_other_stream_or_repeat_uncertain_send(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bot, 'STATE', Path(tmp)/'state.json'), patch.dict(bot.os.environ, {'FORCE_SEND':'false'}):
            success=Mock(json=lambda: {'ok':True})
            with patch.object(bot.requests,'post',side_effect=[bot.requests.ReadTimeout(),success]) as post:
                with self.assertRaises(RuntimeError): bot.send_daily('pharma','token','chat','message')
                bot.send_daily('finance','token','chat','message')
                bot.send_daily('finance','token','chat','message')
                with self.assertRaises(RuntimeError): bot.send_daily('pharma','token','chat','message')
                self.assertEqual(post.call_count,2)

    def test_workflow_preserves_partial_success(self):
        import yaml
        config=yaml.load((ROOT/'.github/workflows/daily_news.yml').read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
        steps=config['jobs']['send-news']['steps']
        senders=[s for s in steps if s.get('id') in ('pharma','finance')]
        self.assertEqual(len(senders),2)
        self.assertTrue(all(s['continue-on-error']=='true' for s in senders))
        ledger=next(s for s in steps if 'git add data/daily_news_last_sent.txt' in s.get('run',''))
        self.assertIn('always()',ledger['if'])
        self.assertIn('daily_delivery.json',ledger['run'])
