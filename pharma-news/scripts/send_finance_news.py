import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

BROKER_KEYWORDS = [
    "미래에셋", "삼성증권", "키움", "한국투자", "NH투자", "KB증권", "신한투자",
    "하나증권", "메리츠", "대신증권", "유안타", "이베스트", "SK증권", "한화투자",
    "교보증권", "부국증권", "유진투자", "IBK투자", "DB금융", "BNK투자", "증권사"
]

def clean_title(title):
    return re.sub(r'^\d+', '', title).strip()

def is_broker_article(title):
    for keyword in BROKER_KEYWORDS:
        if keyword in title:
            return True
    return False

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

def fetch_naver_finance(limit=15):
    url = "https://news.naver.com/breakingnews/section/101/258"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    start, end = get_time_range()
    articles = []
    seen = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        title = clean_title(a.get_text(strip=True))

        if "article" not in href and "news.naver.com" not in href:
            continue
        if len(title) < 10 or len(title) > 100:
            continue
        if is_broker_article(title):
            continue
        if href.startswith("/"):
            full_url = "https://news.naver.com" + href
        else:
            full_url = href
        if full_url in seen:
            continue

        # 시간 확인
        parent = a.find_parent()
        art_time = None
        for _ in range(5):
            if parent is None:
                break
            time_tag = parent.find(string=re.compile(r'\d{4}[-\.]\d{2}[-\.]\d{2}'))
            if time_tag:
                art_time = parse_time(str(time_tag))
                break
            parent = parent.find_parent()

        if art_time is not None and not (start <= art_time <= end):
            continue

        seen.add(full_url)
        articles.append((title, full_url))
        if len(articles) >= limit:
            break

    return articles

def build_message(news):
    now = datetime.now(KST)
    weekday = WEEKDAYS[now.weekday()]
    header = now.strftime("%Y년 %m월 %d일") + "(" + weekday + ") Daily News"
    msg = header + "\n\n"
    if not news:
        msg += "오전 1시~7시 50분 사이 새 기사가 없습니다."
        return msg
    items = []
    for title, url in news:
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
    news = fetch_naver_finance(limit=15)
    print(str(len(news)) + "건")
    msg = build_message(news)
    print(msg)
    send_telegram(msg)
