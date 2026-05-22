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

EXCLUDE_KEYWORDS = ["동영상", "재생시간", "포토", "[영상]", "[사진]", "부음", "부고"]

# 중요도 높은 키워드 (주식시장 연관)
HIGH_PRIORITY = [
    "금리", "환율", "코스피", "코스닥", "주가", "증시", "시장", "Fed", "연준",
    "금통위", "한국은행", "기준금리", "인플레", "CPI", "GDP", "무역",
    "수출", "반도체", "삼성전자", "SK하이닉스", "외국인", "기관", "매수", "매도",
    "IPO", "공매도", "선물", "옵션", "채권", "국채", "달러", "원화",
    "무역수지", "경상수지", "실업", "고용", "물가", "부동산", "PER", "실적",
    "어닝", "배당", "자사주", "M&A", "인수", "합병", "상장", "상폐"
]

def clean_title(title):
    return re.sub(r'^\d+', '', title).strip()

def is_invalid(title):
    for keyword in EXCLUDE_KEYWORDS + BROKER_KEYWORDS:
        if keyword in title:
            return True
    if len(title) < 10 or len(title) > 120:
        return True
    if re.search(r'\d{2}:\d{2}', title):
        return True
    return False

def get_priority(title):
    score = 0
    for keyword in HIGH_PRIORITY:
        if keyword in title:
            score += 1
    return score

def get_article_summary(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 200:
            text = text[:200] + "..."
        return text
    except:
        return ""

def fetch_naver():
    url = "https://news.naver.com/breakingnews/section/101/258"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        seen = set()
        for a in soup.select("a"):
            href = a.get("href", "")
            title = clean_title(a.get_text(strip=True))
            if "article" not in href or "news.naver.com" not in href:
                continue
            if is_invalid(title):
                continue
            if href not in seen:
                seen.add(href)
                articles.append((title, href, get_priority(title)))
    except:
        pass
    return articles

def fetch_fnnews():
    url = "https://www.fnnews.com/section/002001000"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        seen = set()
        for a in soup.select("a"):
            href = a.get("href", "")
            title = clean_title(a.get_text(strip=True))
            if len(title) < 10:
                continue
            if is_invalid(title):
                continue
            if href.startswith("/"):
                full_url = "https://www.fnnews.com" + href
            else:
                full_url = href
            if "fnnews.com" not in full_url:
                continue
            if full_url not in seen:
                seen.add(full_url)
                articles.append((title, full_url, get_priority(title)))
    except:
        pass
    return articles

def fetch_sedaily():
    articles = []
    for url in ["https://www.sedaily.com/market", "https://www.sedaily.com/economy"]:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            res.encoding = "utf-8"
            soup = BeautifulSoup(res.text, "html.parser")
            seen = set()
            for a in soup.select("a"):
                href = a.get("href", "")
                title = clean_title(a.get_text(strip=True))
                if len(title) < 10:
                    continue
                if is_invalid(title):
                    continue
                if href.startswith("/"):
                    full_url = "https://www.sedaily.com" + href
                else:
                    full_url = href
                if "sedaily.com" not in full_url:
                    continue
                if full_url not in seen:
                    seen.add(full_url)
                    articles.append((title, full_url, get_priority(title)))
        except:
            pass
    return articles

def fetch_businesspost():
    url = "https://www.businesspost.co.kr/BP?command=sub&sub=2"
    articles = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        seen = set()
        for a in soup.select("a"):
            href = a.get("href", "")
            title = clean_title(a.get_text(strip=True))
            if len(title) < 10:
                continue
            if is_invalid(title):
                continue
            if href.startswith("/"):
                full_url = "https://www.businesspost.co.kr" + href
            else:
                full_url = href
            if "businesspost.co.kr" not in full_url:
                continue
            if full_url not in seen:
                seen.add(full_url)
                articles.append((title, full_url, get_priority(title)))
    except:
        pass
    return articles

def pick_best_article():
    all_articles = []
    all_articles += fetch_naver()
    all_articles += fetch_fnnews()
    all_articles += fetch_sedaily()
    all_articles += fetch_businesspost()

    # 중복 제목 제거
    seen_titles = set()
    unique = []
    for title, url, score in all_articles:
        t = re.sub(r'[^\w]', '', title)
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append((title, url, score))

    # 우선순위 높은 순으로 정렬
    unique.sort(key=lambda x: x[2], reverse=True)

    if unique:
        return unique[0][0], unique[0][1]
    return None

def build_message(article):
    if article is None:
        return "기사를 가져오지 못했습니다."
    title, url = article
    summary = get_article_summary(url)
    msg = "🔜 <b>" + title + "</b>\n\n"
    if summary:
        msg += summary + "\n\n"
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
    article = pick_best_article()
    msg = build_message(article)
    print(msg)
    send_telegram(msg)
