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

EXCLUDE_KEYWORDS = [
    "동영상", "재생시간", "포토", "[영상]", "[사진]",
    "성매매", "음주운전", "논란", "실형", "사과", "반박", "오보",
    "후보", "선거", "투표", "국민의힘", "민주당", "대통령", "정치",
    "교육감", "현수막", "봉사", "캠프", "여학생"
]

FINANCE_KEYWORDS = [
    "주가", "증시", "코스피", "코스닥", "주식", "종목", "매수", "매도",
    "상장", "공모", "청약", "ETF", "펀드", "채권", "금리", "환율",
    "외국인", "기관", "수급", "실적", "영업이익", "순이익", "매출",
    "반도체", "삼성전자", "SK하이닉스", "배당", "자사주", "공매도",
    "선물", "옵션", "IPO", "M&A", "인수", "합병", "지수", "시총",
    "달러", "원화", "Fed", "연준", "금통위", "한국은행", "기준금리",
    "무역", "수출", "수입", "경상수지", "GDP", "CPI", "물가", "고용",
    "유가", "원자재", "구리", "금값", "비트코인", "암호화폐",
    "레버리지", "인버스", "리츠", "부동산", "PER", "PBR", "ROE"
]

def is_invalid_title(title):
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in title:
            return True
    if re.search(r'\d{2}:\d{2}', title):
        return True
    return False

def is_broker_article(title):
    for keyword in BROKER_KEYWORDS:
        if keyword in title:
            return True
    return False

def is_finance_related(title):
    for keyword in FINANCE_KEYWORDS:
        if keyword in title:
            return True
    return False

def normalize_url(href):
    article_id = re.search(r'article_id=(\d+)', href)
    office_id = re.search(r'office_id=(\d+)', href)
    if article_id and office_id:
        return f"https://n.news.naver.com/mnews/article/{office_id.group(1)}/{article_id.group(1)}"
    return None

def get_full_title(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
    except Exception:
        pass
    return None

def fetch_naver_finance(limit=15):
    articles = []
    seen = set()
    page = 1

    while len(articles) < limit and page <= 5:
        url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&date=&page={page}"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = "euc-kr"
        soup = BeautifulSoup(res.text, "html.parser")

        found_ids = False
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")

            if "article_id" not in href:
                continue
            found_ids = True

            clean_url = normalize_url(href)
            if not clean_url or clean_url in seen:
                continue

            title = get_full_title(clean_url)
            if not title:
                title = re.sub(r'^\d+', '', a.get_text(strip=True)).strip()

            if len(title) < 10 or len(title) > 150:
                continue
            if is_broker_article(title):
                continue
            if is_invalid_title(title):
                continue

            seen.add(clean_url)
            articles.append((title, clean_url))

            if len(articles) >= limit:
                break

        if not found_ids:
            break
        page += 1

    return articles

def build_message(news):
    now = datetime.now(KST)
    weekday = WEEKDAYS[now.weekday()]
    header = now.strftime("%Y년 %m월 %d일") + "(" + weekday + ") Daily News"
    msg = header + "\n\n"
    if not news:
        msg += "기사를 가져오지 못했습니다."
        return msg
    items = []
    for title, url in news:
        items.append('<a href="' + url + '"><b><u>' + title + '</u></b></a>')
    msg += "\n\n".join(items)
    msg += "\n\n* 위 내용은 국내외 언론사 뉴스 등을 인용한 자료로 별도의 승인절차 없이 제공합니다.\n\nhttps://t.me/hanyangresearch\n한양증권 스몰캡"
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
