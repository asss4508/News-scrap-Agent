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

KST = timezone(timedelta(hours=9))

BROKER_KEYWORDS = [
    "미래에셋", "삼성증권", "키움", "한국투자", "NH투자", "KB증권", "신한투자",
    "하나증권", "메리츠", "대신증권", "유안타", "이베스트", "SK증권", "한화투자",
    "교보증권", "부국증권", "유진투자", "IBK투자", "DB금융", "BNK투자", "증권사"
]

EXCLUDE_KEYWORDS = ["동영상", "재생시간", "포토", "[영상]", "[사진]"]

def clean_title(title):
    return re.sub(r'^\d+', '', title).strip()

def is_broker_article(title):
    for keyword in BROKER_KEYWORDS:
        if keyword in title:
            return True
    return False

def is_invalid_title(title):
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return True
    return False

def get_article_summary(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        # 본문 텍스트 추출
        for tag in soup(["script", "style", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        # 불필요한 공백 제거
        text = re.sub(r'\s+', ' ', text).strip()
        # 앞부분 200자 추출
        if len(text) > 200:
            text = text[:200] + "..."
        return text
    except:
        return ""

def fetch_top_news():
    url = "https://news.naver.com/breakingnews/section/101/258"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    seen = set()

    for a in soup.select("a"):
        href = a.get("href", "")
        title = clean_title(a.get_text(strip=True))
        if "article" not in href:
            continue
        if len(title) < 10 or len(title) > 100:
            continue
        if is_broker_article(title):
            continue
        if is_invalid_title(title):
            continue
        if href.startswith("/"):
            full_url = "https://news.naver.com" + href
        else:
            full_url = href
        if "news.naver.com" not in full_url:
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        return (title, full_url)

    return None

def build_message(article):
    if article is None:
        return "기사를 가져오지 못했습니다."
    title, url = article
    summary = get_article_summary(url)
    msg = "🔜 " + "<b>" + title + "</b>" + "\n"
    if summary:
        msg += summary + "\n"
    msg += url
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
    article = fetch_top_news()
    msg = build_message(article)
    print(msg)
    send_telegram(msg)
