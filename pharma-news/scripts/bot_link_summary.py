import os
import re
import requests
from bs4 import BeautifulSoup
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ARTICLE_SELECTORS = [
    "#dic_area", "#articleBodyContents", "#articeBody", "#articleBody",
    ".article_body", ".news_body", "#newsct_article", "article",
    ".article-body", "#article_content", ".article-content",
    "#article-view-content-div", ".article_txt", ".view_text"
]

def fetch_article(url):
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    og_title = soup.find("meta", property="og:title")
    title = og_title["content"].strip() if og_title and og_title.get("content") else ""

    for tag in soup(["script", "style", "header", "footer", "nav", "aside", "iframe"]):
        tag.decompose()

    content_el = None
    for sel in ARTICLE_SELECTORS:
        content_el = soup.select_one(sel)
        if content_el:
            break

    text = content_el.get_text(separator=" ", strip=True) if content_el else soup.get_text(separator=" ", strip=True)
    text = re.sub(r'\S+@\S+\.\S+', '', text)
    text = re.sub(r'\[.*?기자.*?\]', '', text)
    text = re.sub(r'[가-힣]+ 기자', '', text)
    text = re.sub(r'[가-힣]+ 특파원', '', text)
    text = re.sub(r'©.*?(?=\s)', '', text)
    text = re.sub(r'무단\s*전재.*?(?=\s)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return title, text[:3000]

def summarize(title, body, url):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""다음 기사를 읽고 아래 형식으로만 출력해. 다른 설명 없이 형식 그대로만.

제목: {title}
본문: {body}

=== 출력 형식 ===
🔜 {title}

Keyword : 핵심키워드1, 핵심키워드2

[기사 요약]
1. 핵심 내용 한 문장
2. 핵심 내용 한 문장
3. 핵심 내용 한 문장
4. 핵심 내용 한 문장
5. 핵심 내용 한 문장

{url}"""

    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    urls = re.findall(r'https?://[^\s]+', text)
    if not urls:
        return

    if not ANTHROPIC_API_KEY:
        await update.message.reply_text("❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return

    status = await update.message.reply_text("⏳ 요약 중...")
    try:
        title, body = fetch_article(urls[0])
        if not title and not body:
            await status.edit_text("❌ 기사를 불러올 수 없습니다.")
            return
        result = summarize(title, body, urls[0])
        await status.edit_text(result, disable_web_page_preview=True)
    except Exception as e:
        await status.edit_text(f"❌ {type(e).__name__}: {str(e)[:150]}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'https?://'), on_message))
    print("링크 요약 봇 실행 중...")
    app.run_polling()

if __name__ == "__main__":
    main()
