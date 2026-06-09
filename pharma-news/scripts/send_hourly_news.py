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

EXCLUDE_KEYWORDS = [
    "동영상", "재생시간", "포토", "[영상]", "[사진]",
    "부음", "부고", "마감시황", "장마감", "시황"
]

HIGH_PRIORITY = [
    "금리", "환율", "코스피", "코스닥", "주가", "증시", "시장", "Fed", "연준",
    "금통위", "한국은행", "기준금리", "인플레", "CPI", "GDP", "무역",
    "수출", "반도체", "삼성전자", "SK하이닉스", "외국인", "기관", "매수", "매도",
    "IPO", "공매도", "선물", "옵션", "채권", "국채", "달러", "원화",
    "무역수지", "경상수지", "실업", "고용", "물가", "PER", "실적",
    "어닝", "배당", "자사주", "M&A", "인수", "합병", "상장", "상폐"
]

def clean_title(title):
    title = re.sub(r'^\d+', '', title)
    title = re.sub(r'\[.*?기자.*?\]', '', title)
    title = re.sub(r'\[.*?특파원.*?\]', '', title)
    title = re.sub(r'·\[.*?\]', '', title)
    return title.strip()

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

def get_article_date(url):
    """기사 발행일을 og:article:published_time 또는 메타태그에서 추출"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(res.text, "html.parser")
        for prop in ["article:published_time", "og:regDate", "og:pub_date", "datePublished"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                raw = tag["content"][:10]
                try:
                    return datetime.strptime(raw, "%Y-%m-%d").date()
                except Exception:
                    pass
        # 날짜 패턴 직접 탐색
        text = res.text
        m = re.search(r'(\d{4})[.\-/](\d{2})[.\-/](\d{2})', text[:3000])
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            except Exception:
                pass
    except Exception:
        pass
    return None

def get_article_summary(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")

        # 불필요한 태그 제거
        for tag in soup(["script", "style", "header", "footer", "nav",
                         "aside", "iframe", "figure", "figcaption",
                         "button", "form", "input", "select"]):
            tag.decompose()

        # 사진 캡션, UI 버튼 영역 제거
        for tag in soup.select(
            ".image_caption, .caption, .img_desc, .photo_desc, .ImageCaption, "
            "[class*='caption'], [class*='Caption'], [class*='photo'], [class*='Photo'], "
            "[class*='share'], [class*='Share'], [class*='tool'], [class*='Tool'], "
            "[class*='font'], [class*='Font'], [class*='sns'], [class*='SNS'], "
            "[class*='subscribe'], [class*='Subscribe'], [class*='related'], "
            "[class*='button'], [class*='Button'], .article_util, .article-util"
        ):
            tag.decompose()

        content = None
        selectors = [
            "article", "#articleBody", "#article-view-content-div",
            ".article_body", ".news_body", "#newsct_article",
            "#articeBody", ".article-body", "#article_content",
            ".article_txt", "#news_body_area", ".news-article-body",
            "#cont_article", ".view_text", "#articleBodyContents",
            ".article-content", ".news_end_body"
        ]
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                break

        if not content:
            content = soup.body

        if content:
            for tag in content.select(
                "[class*='caption'], [class*='Caption'], [class*='photo'], "
                "[class*='Photo'], [class*='img'], [class*='Img'], "
                "[class*='share'], [class*='tool'], [class*='font'], "
                "[class*='sns'], [class*='button']"
            ):
                tag.decompose()

            text = content.get_text(separator=" ", strip=True)

            # UI 버튼 텍스트 패턴 제거
            text = re.sub(r'뉴스\s*듣기.*?크기', '', text)
            text = re.sub(r'글자\s*크기\s*가\s*보통.*?크게', '', text)
            text = re.sub(r'기사\s*공유\s*페이스북.*?프린트', '', text)
            text = re.sub(r'페이스북\s*엑스\s*카카오톡.*?북마크', '', text)
            text = re.sub(r'채널구독\s*다음\s*채널구독', '', text)
            text = re.sub(r'다크모드\s*프린트\s*네이버', '', text)
            text = re.sub(r'이메일\s*주소복사', '', text)

            # 기자 서명, 출처 제거
            text = re.sub(r'\S+@\S+\.\S+', '', text)
            text = re.sub(r'\d{4}-\d{2}-\d{2}\s*\d{2}:\d{2}:\d{2}', '', text)
            text = re.sub(r'\d{4}\.\d{2}\.\d{2}\s*[가-힣]+\s*기자', '', text)
            text = re.sub(r'[가-힣]+\s*기자\s*=?\s*', '', text)
            text = re.sub(r'\[.*?기자.*?\]', '', text)
            text = re.sub(r'\[.*?=.*?\]', '', text)
            text = re.sub(r'\d{4}\.\d{2}\.\d{2}', '', text)
            text = re.sub(r'서울\s*[가-힣]+\s*[가-힣]+\s*딜링룸.*?있다\.', '', text)
            text = re.sub(r'확대\s*축소\s*공유하기.*?(?=\S)', '', text)
            text = re.sub(r'©.*?(?=\S)', '', text)
            text = re.sub(r'무단\s*전재.*?(?=\S)', '', text)
            text = re.sub(r'저작권.*?(?=\S)', '', text)
            text = re.sub(r'\s+', ' ', text).strip()

            # 문장 분리
            sentences = re.split(r'(?<=[.!?])\s+', text)
            sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

            # 3문장, 200자 이내
            result = []
            char_count = 0
            for s in sentences[:5]:
                result.append(s)
                char_count += len(s)
                if len(result) >= 3 or char_count >= 200:
                    break

            # 마침표로 끝나는 문장까지만
            while result and not result[-1].endswith(('.', '!', '?')):
                result.pop()

            if not result:
                return ""

            # 두 단락으로 나누기
            mid = len(result) // 2
            para1 = " ".join(result[:mid]) if mid > 0 else " ".join(result)
            para2 = " ".join(result[mid:]) if mid > 0 else ""
            if para2:
                return para1 + "\n\n" + para2
            return para1

    except:
        pass
    return ""

def fetch_articles(url, domain, href_filter=None):
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
            if href_filter and href_filter not in href:
                continue
            if "ranking" in href or "ntype=RANKING" in href:
                continue
            if href.startswith("/"):
                full_url = domain + href
            elif href.startswith("http"):
                full_url = href
            else:
                continue
            base_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
            if base_domain not in full_url:
                continue
            if full_url in seen:
                continue
            seen.add(full_url)
            articles.append((title, full_url, get_priority(title)))
    except:
        pass
    return articles

def pick_best_article():
    all_articles = []
    all_articles += fetch_articles("https://news.naver.com/breakingnews/section/101/258", "https://news.naver.com", "article")
    all_articles += fetch_articles("https://www.fnnews.com/section/002001000", "https://www.fnnews.com")
    all_articles += fetch_articles("https://www.sedaily.com/market", "https://www.sedaily.com")
    all_articles += fetch_articles("https://www.sedaily.com/economy", "https://www.sedaily.com")
    all_articles += fetch_articles("https://www.businesspost.co.kr/BP?command=sub&sub=2", "https://www.businesspost.co.kr")

    seen_titles = set()
    unique = []
    for title, url, score in all_articles:
        t = re.sub(r'[^\w]', '', title)
        if t not in seen_titles:
            seen_titles.add(t)
            unique.append((title, url, score))

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
