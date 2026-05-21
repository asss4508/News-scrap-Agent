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
    today = datetime.now().strftime("%Y%EB%85%84 %m%EC%9B%94 %d%EC%9D%BC")
    msg = "📰 <b>제약·바이오 뉴스브리핑</b>\n" + today + " 오전 7시 50분\n\n"
    all_news = yakup_news + pharmnews_news
    items = []
    for title, url in all_news:
        items.append('<a href="' + url + '">' + title + '</a>')
    msg += "\n\n".join(items)
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
    print(str(len(yakup)) + "건 / " + str(len(pharmnews)) + "건")
    if not yakup and not pharmnews:
        print("뉴스 없음")
        exit(1)
    msg = build_message(yakup, pharmnews)
    print(msg)
    send_telegram(msg)
