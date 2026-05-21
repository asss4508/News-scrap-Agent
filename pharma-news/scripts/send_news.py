import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_yakup(limit=8):
    url = "https://www.yakup.com/news/index.html?cat=all"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    articles = []
    for a in soup.select("a"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if "mode=view" in href and len(title) > 10:
            full_url = "https://www.yakup.com" + href if href.startswith("/") else href
            if full_url not in [x[1] for x in articles]:
                articles.append((title, full_url))
        if len(articles) >= limit:
            break
    return articles

def fetch_pharmnews(limit=7):
    url = "https://www.pharmnews.com/news/articleList.html?view_type=sm"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    articles = []
    for a in soup.select("a"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        if "articleView" in href and len(title) > 10:
            full_url = "https://www.pharmnews.com" + href if href.startswith("/") else href
            if full_url not in [x[1] for x in articles]:
                articles.append((title, full_url))
        if len(articles) >= limit:
            break
    return articles

def build_message(yakup_news, pharmnews_news):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    lines = [f"📰 <b>제약·바이오 뉴스브리핑</b>", f"{today} 오전 8시\n"]
    lines.append("━━━━━━━━━━━━━━━━")
    lines.append("🔹 <b>약업닷컴</b>")
    for title, url in yakup_news:
        lines.append(f'<a href="{url}">{title}</a>')
    lines.append("\n━━━━━━━━━━━━━━━━")
    lines.append("🔹 <b>팜뉴스</b>")
    for title, url in pharmnews_news:
        lines.append(f'<a href="{url}">{title}</a>')
    lines.append("\n━━━━━━━━━━━━━━━━")
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n..."
    return msg

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    print("뉴스 수집 중...")
    yakup = fetch_yakup(limit=8)
    pharmnews = fetch_pharmnews(limit=7)
    print(f"약업닷컴: {len(yakup)}건, 팜뉴스: {len(pharmnews)}건")
    if not yakup and not pharmnews:
        print("❌ 뉴스를 가져오지 못했습니다.")
        exit(1)
    msg = build_message(yakup, pharmnews)
    print(msg)
    send_telegram(msg)
