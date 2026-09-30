"""Persist per-stream delivery outcomes; never automatically repeat uncertain sends."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

STATE = Path(__file__).resolve().parents[2] / 'data/daily_delivery.json'
KST = timezone(timedelta(hours=9))


def send_daily(stream, token, chat_id, message):
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    key = f'{datetime.now(KST).date().isoformat()}/{stream}'
    previous = state.get(key, {}).get('status')
    force = os.environ.get('FORCE_SEND', '').lower() == 'true' and os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
    if previous == 'sent' and not force:
        print(f'{stream}: already delivered today')
        return
    if previous in ('sending', 'uncertain') and not force:
        raise RuntimeError(f'{stream}: delivery uncertain; inspect Telegram before retrying')
    def save(status):
        state[key] = {'status': status}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
        temp.replace(STATE)
    save('sending')
    try:
        response = requests.post('https://api.telegram.org/bot' + token + '/sendMessage',
            json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': True},
            timeout=(10, 45))
        response.raise_for_status()
        if not response.json().get('ok'):
            raise RuntimeError('Telegram rejected delivery')
    except Exception:
        save('uncertain')
        raise RuntimeError(f'{stream}: Telegram delivery not confirmed') from None
    save('sent')
    print(f'{stream}: delivered')
