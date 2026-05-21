import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def clean_title(title):
    # 앞에 붙은 숫자 제거 (예: "1제목", "10제목", "1'제목")
    return re.sub(r'^\d+', '', title).strip()

def fetch_yakup(limit=12):
    url = "https://www.yakup.com/news/index.html?cat=all"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    articles = []
    seen = set()
    for a in soup.select("a"):
        href = a.get("href", "")
        title = clean_title(a.get_text(strip=True))
        if "mode=view" not in href:
            continue
        if len(title) < 10 or len(title) > 100:
            continue
        full_url = "https://www.yakup.com" + href if href.startswith("/") else
