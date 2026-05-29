import json
import os
import re
import math
from pathlib import Path
from collections import defaultdict

import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

INDEX_PATH = Path(__file__).parent.parent.parent / "data" / "index.json"

# ── BM25 ──────────────────────────────────────────────────────────────────────

def tokenize(text: str):
    return re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())

class BM25:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.n = len(chunks)
        self.avg_dl = 0
        self.df = defaultdict(int)
        self.tf = []

        total = 0
        for chunk in chunks:
            tokens = tokenize(chunk["text"])
            total += len(tokens)
            freq = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            self.tf.append(freq)
            for t in freq:
                self.df[t] += 1

        self.avg_dl = total / self.n if self.n else 1

    def search(self, query: str, top_k=10):
        q_tokens = tokenize(query)
        scores = []

        for i, freq in enumerate(self.tf):
            dl = sum(freq.values())
            score = 0
            for t in q_tokens:
                if t not in freq:
                    continue
                df = self.df[t]
                idf = math.log((self.n - df + 0.5) / (df + 0.5) + 1)
                tf = freq[t]
                norm_tf = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avg_dl))
                score += idf * norm_tf
            if score > 0:
                scores.append((score, i))

        scores.sort(reverse=True)
        return [self.chunks[i] for _, i in scores[:top_k]]

# ── 인덱스 로드 ────────────────────────────────────────────────────────────────

def load_index():
    if not INDEX_PATH.exists():
        return []
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)

# ── Claude 답변 ────────────────────────────────────────────────────────────────

def answer(question: str, bm25: BM25) -> str:
    results = bm25.search(question, top_k=10)

    if not results:
        context = "관련 자료를 찾을 수 없습니다."
    else:
        parts = []
        for r in results:
            parts.append(f"[출처: {r['source']}]\n{r['text']}")
        context = "\n\n---\n\n".join(parts)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""다음은 참고 자료입니다:

{context}

---

위 자료를 바탕으로 질문에 답해줘.
- 자료에 근거한 내용만 답해줘. 자료에 없으면 명확히 없다고 말해줘.
- 출처(파일명 또는 채널명)를 함께 표시해줘.
- 한국어로 답해줘.

질문: {question}"""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text.strip()

# ── Telegram 핸들러 ────────────────────────────────────────────────────────────

async def on_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = (update.message.text or "").strip()
    if not question:
        return

    bm25: BM25 = context.bot_data.get("bm25")
    if bm25 is None or bm25.n == 0:
        await update.message.reply_text("⚠️ 인덱스가 없습니다. 먼저 자료를 업로드하고 인덱스를 빌드해주세요.")
        return

    if not ANTHROPIC_API_KEY:
        await update.message.reply_text("❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return

    status = await update.message.reply_text("🔍 검색 중...")
    try:
        result = answer(question, bm25)
        await status.edit_text(result)
    except Exception as e:
        await status.edit_text(f"❌ {type(e).__name__}: {str(e)[:200]}")

async def on_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bm25: BM25 = context.bot_data.get("bm25")
    n = bm25.n if bm25 else 0
    await update.message.reply_text(f"📚 인덱스 청크: {n}개\n질문을 입력하시면 답변해드립니다.")

async def post_init(application):
    chunks = load_index()
    application.bot_data["bm25"] = BM25(chunks) if chunks else BM25([])
    print(f"인덱스 로드 완료: {len(chunks)}개 청크")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("status", on_status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_question))
    print("QA 봇 실행 중...")
    app.run_polling()

if __name__ == "__main__":
    main()
