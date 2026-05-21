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
        if href.startswith("/"):
            full_url = "https://www.yakup.com" + href
        else:
            full_url = href
        if full_url in seen:
            continue
        seen.add(full_url)
        articles.append((title, full_url))
        if len(articles) >= limit:
            break
    return articles

def fetch_pharmnews(limit=3):
    url = "https://www.pharmnews.com/news/articleList.html?view_type=sm"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    articles = []
    seen = set()
    for a in soup.select("a"):
        href = a.get("href", "")
        title = clean_title(a.get_text(strip=True))
        if "articleView" not in href:
            continue
        if len(title) < 10 or len(title) > 100:
            continue
        if href.startswith("/"):
            full_url = "https://www.pharmnews.com" + href
        else:
            full_url = href
        if full_url in seen:
            continue
        seen.add(full_url)
        articles.append((title, full_url))
        if len(articles) >= limit:
            break
    return articles

def build_message(yakup_news, pharmnews_news):
    now = datetime.now(KST)
    weekday = WEEKDAYS[now.weekday()]
    header = now.strftime("%Y년 %m월 %d일") + "(" + weekday + ") Daily News"
    msg = header + "\n\n"
    all_news = yakup_news + pharmnews_news
    items = []
    for title, url in all_news:
        items.append('<a href="' + url + '"><b><u>' + title + '</u></b></a>')
    msg += "\n\n".join(items)
    msg += "\n\n* 위 내용은 국내외 언론사 뉴스 등을 인용한 자료로 별도의 승인절차 없이 제공합니다.\n\nhttps://t.me/bdragon0808\n한양증권 제약/바이오"
    return msg

def send_telegram(message):
    api_url = "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = requests.post(api_url, json=payload, timeout=10)
    res.raise_for_status()
    print("전송 완료")

if __name__ == "__main__":
    print("뉴스 수집 중...")
    yakup = fetch_yakup(limit=12)
    pharmnews = fetch_pharmnews(limit=3)
    if not yakup and not pharmnews:
        print("뉴스 없음")
        exit(1)
    msg = build_message(yakup, pharmnews)
    print(msg)
    send_telegram(msg)
