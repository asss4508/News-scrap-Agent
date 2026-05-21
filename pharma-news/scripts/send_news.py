import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

def clean_title(title):
    return re.sub(r'^\d+', '', title).strip()

def get_time_range():
    now = datetime.now(KST)
    start = now.replace(hour=1, minute=0, second=0, microsecond=0)
    end = now.replace(hour=7, minute=50, second=0, microsecond=0)
    return start, end

def parse_yakup_time(time_str):
    # 약업닷컴 시간 형식: "2026-05-21 07:30" 또는 "2026.05.21 07:30"
    time_str = time_str.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(time_str, fmt)
            return dt.replace(tzinfo=KST)
        except:
