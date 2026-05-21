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

def parse_time(time_str):
    time_str = time_str.strip()
    for fmt in ["%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d", "%Y.%m.%d"]:
        try:
            dt = datetime.strptime(time_str, fmt)
            return dt.replace(tzinfo=KST)
        except ValueError:
            pass
    return None

def get_article_time(a):
    parent = a.find_parent()
    for _ in range(5):
        if parent is None:
            break
        time_tag = parent.find(string=re.compile(r'\d{4}[-\.]\d{2}[-\.]\d{2}'))
        if time_tag:
            return parse_time(str(time_tag))
        parent = parent.find_parent()
    return None

def fetch_yakup(limit=12):
    url = "https://www.yakup.com/news/index.html?cat=all"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    start, end = get_time_range()
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
        art_time = get_article_time(a)
        if art_time is not None and not (start <= art_time <= end):
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
    start, end = get_time_range()
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
        art_time = get_article_time(a)
        if art_time is not None and not (start <= art_time <= end):
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
    if not all_news:
        msg += "오전 1시~7시 50분 사이 새 기사가 없습니다."
        return msg
    items = []
    for title, url in all_news:
        items.append('<a href="' + url + '"><b><u>' + title + '</u></b></a>')
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
    msg = build_message(yakup, pharmnews)
    print(msg)
    send_telegram(msg)
