from datetime import datetime, timedelta, timezone
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runner', ROOT / 'pharma-news/scripts/hourly_news_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def at(hour, minute=0, day=10):
    return datetime(2026, 9, day, hour, minute, tzinfo=runner.KST)


class RunnerTests(unittest.TestCase):
    def simulate(self, start, state=None, outcome='sent', manual=False):
        now = [start]
        ticks = [0]
        sends, checkpoints = [], []
        def sleep(seconds):
            self.assertLessEqual(seconds, 60)
            now[0] += timedelta(seconds=seconds)
            ticks[0] += seconds
        def send():
            sends.append(now[0])
            return outcome
        def persist():
            checkpoints.append(json.loads(runner.STATE.read_text()) if runner.STATE.exists() else {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            if state is not None:
                path.write_text(json.dumps(state))
            with patch.object(runner, 'STATE', path), contextlib.redirect_stdout(io.StringIO()):
                runner.run_session(manual=manual, now_fn=lambda: now[0], sleep_fn=sleep,
                                   send_fn=send, persist_fn=persist, monotonic_fn=lambda: ticks[0])
        return sends, checkpoints

    def test_observed_0952_run_continues_at_following_hours(self):
        sends, checkpoints = self.simulate(at(9, 52))
        self.assertEqual(sends, [at(9, 52)] + [at(h) for h in range(10, 16)])
        self.assertEqual(len(checkpoints), len(sends))
        self.assertEqual(checkpoints[0]['hours'], {'9': 'sent'})

    def test_early_runner_waits_for_eight_then_hands_off(self):
        sends, _ = self.simulate(at(3))
        self.assertEqual(sends, [at(8)])

    def test_successor_skips_finished_slot_and_keeps_hourly_schedule(self):
        state = {'date': '2026-09-10', 'hours': {'8': 'sent'}}
        sends, _ = self.simulate(at(8), state)
        self.assertEqual(sends, [at(h) for h in range(9, 14)])

    def test_finish_after_last_slot_and_do_not_send_overnight(self):
        self.assertEqual(self.simulate(at(15))[0], [at(15), at(16)])
        for hour in (0, 2, 17, 23):
            self.assertEqual(self.simulate(at(hour))[0], [])

    def test_no_article_is_recorded_without_retry_storm(self):
        sends, checkpoints = self.simulate(at(16), outcome='no_article')
        self.assertEqual(sends, [at(16)])
        self.assertEqual(checkpoints[-1]['hours'], {'16': 'no_article'})

    def test_manual_run_is_exactly_once_even_outside_window(self):
        self.assertEqual(self.simulate(at(20), manual=True)[0], [at(20)])

    def test_next_slot_uses_kst_and_never_backfills_past_hours(self):
        self.assertEqual(runner.next_slot(at(14, 30).astimezone(timezone.utc), {}), at(14))
        yesterday = {'date': '2026-09-09', 'hours': {'14': 'sent'}}
        self.assertEqual(runner.next_slot(at(14), yesterday), at(14))

    def test_send_failure_does_not_mark_hour_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            with patch.object(runner, 'STATE', path), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    runner.run_session(now_fn=lambda: at(16),
                                       send_fn=lambda: (_ for _ in ()).throw(RuntimeError('send failed')))
            self.assertFalse(path.exists())

    def test_corrupt_ledger_does_not_reset_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text('not json')
            with patch.object(runner, 'STATE', path):
                with self.assertRaises(ValueError):
                    runner.read_state()


if __name__ == '__main__':
    unittest.main()
