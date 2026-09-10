"""Keep a runner alive across hourly sends; cron only starts/replaces sessions.

All callers must share the workflow's hourly-news concurrency group and check
out current main. Save each completed slot immediately, before waiting again.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data/hourly_delivery_state.json"
SESSION_LIMIT = timedelta(hours=5, minutes=20)
COLLECTION_BUDGET = timedelta(minutes=5)


def operating_window(now):
    return 3 <= now.astimezone(KST).hour < 17


def next_slot(now, state):
    now = now.astimezone(KST)
    done = state.get("hours", {}) if state.get("date") == now.date().isoformat() else {}
    # Recover only the current hour, never burst-send every missed hour.
    for hour in range(max(8, now.hour), 17):
        if str(hour) not in done:
            return now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return None


def read_state():
    if not STATE.exists():
        return {}
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("hours", {}), dict):
        raise ValueError("Invalid hourly delivery ledger; refusing duplicate-prone recovery")
    return state


def record_slot(state, slot, result):
    if result not in ("sent", "no_article"):
        raise ValueError(f"Unexpected result: {result}")
    if state.get("date") != slot.date().isoformat():
        state = {"date": slot.date().isoformat(), "hours": {}}
    state.setdefault("hours", {})[str(slot.hour)] = result
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE)
    return state


def persist_history():
    def git(*args, **kwargs):
        return subprocess.run(["git", *args], cwd=ROOT, check=True, **kwargs)
    paths = [p for p in ("data/hourly_sent_log.json", "data/hourly_delivery_state.json")
             if (ROOT / p).exists()]
    if not paths:
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git("add", "--", *paths)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if changed.returncode == 0:
        return
    if changed.returncode != 1:
        raise RuntimeError("Cannot inspect delivery ledger changes")
    git("commit", "-m", "chore: persist hourly news delivery slot")
    for attempt in range(3):
        git("pull", "--rebase", "origin", "main")
        pushed = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=ROOT)
        if pushed.returncode == 0:
            return
        time.sleep(2)
    raise RuntimeError("Delivery ledger could not be saved; check before retrying")


def collect_and_send():
    result = subprocess.run(
        [sys.executable, str(ROOT / "pharma-news/scripts/send_hourly_news.py")],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=COLLECTION_BUDGET.total_seconds(),
    )
    print(result.stdout, end="", flush=True)
    result.check_returncode()
    lines = result.stdout.splitlines()
    if not lines or lines[-1] not in ("HOURLY_RESULT=sent", "HOURLY_RESULT=no_article", "HOURLY_RESULT=outside_window"):
        raise RuntimeError("News sender did not report a recognized outcome")
    return lines[-1].split("=", 1)[1]


def run_session(*, manual=False, now_fn=None, sleep_fn=time.sleep, send_fn=collect_and_send,
                persist_fn=persist_history, monotonic_fn=time.monotonic):
    now_fn = now_fn or (lambda: datetime.now(KST))
    deadline = monotonic_fn() + SESSION_LIMIT.total_seconds()
    state = read_state()
    if manual:
        now = now_fn().astimezone(KST)
        result = send_fn()
        if 8 <= now.hour < 17 and result in ("sent", "no_article"):
            record_slot(state, now, result)
        persist_fn()
        return
    while True:
        now = now_fn().astimezone(KST)
        if not operating_window(now):
            return
        slot = next_slot(now, state)
        if slot is None:
            return
        wait = max(0, (slot - now).total_seconds())
        if monotonic_fn() + wait + COLLECTION_BUDGET.total_seconds() > deadline:
            print("다음 정각은 새 대기 작업에 넘깁니다.", flush=True)
            return
        if wait:
            sleep_fn(min(wait, 60))
            continue
        print(f"시간별 뉴스 회차 시작: {slot.isoformat()}", flush=True)
        result = send_fn()
        if result == "outside_window":
            return
        state = record_slot(state, slot, result)
        persist_fn()  # Checkpoint every hour, not just at the end of the session.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("gate", "run"))
    args = parser.parse_args()
    manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if args.mode == "gate":
        output = f"proceed={str(manual or operating_window(datetime.now(KST))).lower()}\n"
        print(output, end="")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                stream.write(output)
    else:
        run_session(manual=manual)


if __name__ == "__main__":
    main()
