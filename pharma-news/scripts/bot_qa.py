import base64
import io
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from pathlib import Path

import requests as http_requests
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "asss4508/pharma-news-bot")

INDEX_PATH = Path(__file__).parent.parent.parent / "data" / "index.json"

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".docx", ".txt", ".csv", ".md"}

# ── 텍스트 추출 ────────────────────────────────────────────────────────────────

def extract_from_bytes(file_bytes: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    try:
        if ext == ".pdf":
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        elif ext in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
            lines = []
            for sheet in wb.worksheets:
                lines.append(f"[시트: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    row_text = "\t".join(str(v) for v in row if v is not None)
                    if row_text.strip():
                        lines.append(row_text)
            return "\n".join(lines)
        elif ext == ".docx":
            from docx import Document as DocxDoc
            doc = DocxDoc(io.BytesIO(file_bytes))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        else:
            for enc in ("utf-8", "cp949", "euc-kr"):
                try:
                    return file_bytes.decode(enc)
                except UnicodeDecodeError:
                    continue
    except Exception as e:
        print(f"추출 오류 ({filename}): {e}")
    return ""

def split_chunks(text: str, source: str, chunk_size=800, overlap=150):
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    if not text:
        return []
    paragraphs = text.split('\n\n')
    chunks, buffer = [], ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) > chunk_size:
            if buffer:
                chunks.append({"text": buffer.strip(), "source": source})
                buffer = buffer[-overlap:] + " " + para
            else:
                for i in range(0, len(para), chunk_size - overlap):
                    chunk = para[i:i + chunk_size]
                    if chunk.strip():
                        chunks.append({"text": chunk.strip(), "source": source})
                buffer = ""
        else:
            buffer = (buffer + "\n\n" + para).strip() if buffer else para
    if buffer.strip():
        chunks.append({"text": buffer.strip(), "source": source})
    return chunks

# ── BM25 ──────────────────────────────────────────────────────────────────────

def tokenize(text: str):
    return re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())

class BM25:
    def __init__(self, chunks, k1=1.5, b=0.75):
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self.n = len(self.chunks)
        self.avg_dl = 0
        self.df = defaultdict(int)
        self.tf = []
        total = 0
        for chunk in self.chunks:
            tokens = tokenize(chunk["text"])
            total += len(tokens)
            freq = defaultdict(int)
            for t in tokens:
                freq[t] += 1
            self.tf.append(freq)
            for t in freq:
                self.df[t] += 1
        self.avg_dl = total / self.n if self.n else 1

    def add_chunks(self, new_chunks):
        return BM25(self.chunks + new_chunks)

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

# ── GitHub 저장 ────────────────────────────────────────────────────────────────

def save_to_github(filename: str, file_bytes: bytes, new_chunks: list):
    if not GITHUB_TOKEN:
        return False
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

    # 1. 파일 저장
    file_path = f"data/uploads/{filename}"
    file_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"
    existing = http_requests.get(file_url, headers=headers)
    sha = existing.json().get("sha") if existing.status_code == 200 else None
    payload = {
        "message": f"feat: {filename} 업로드 (텔레그램)",
        "content": base64.b64encode(file_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha
    http_requests.put(file_url, json=payload, headers=headers)

    # 2. 인덱스 업데이트
    index_path = "data/index.json"
    index_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{index_path}"
    existing_index = http_requests.get(index_url, headers=headers)
    if existing_index.status_code == 200:
        idx_data = existing_index.json()
        idx_sha = idx_data["sha"]
        current_chunks = json.loads(base64.b64decode(idx_data["content"]).decode("utf-8"))
    else:
        idx_sha = None
        current_chunks = []

    updated_chunks = current_chunks + new_chunks
    updated_content = json.dumps(updated_chunks, ensure_ascii=False, indent=2)
    idx_payload = {
        "message": f"chore: 인덱스 업데이트 ({filename})",
        "content": base64.b64encode(updated_content.encode("utf-8")).decode(),
    }
    if idx_sha:
        idx_payload["sha"] = idx_sha
    http_requests.put(index_url, json=idx_payload, headers=headers)
    return True

# ── Claude 답변 ────────────────────────────────────────────────────────────────

def answer(question: str, bm25: BM25) -> str:
    results = bm25.search(question, top_k=10)
    if not results:
        context = "관련 자료를 찾을 수 없습니다."
    else:
        context = "\n\n---\n\n".join(
            f"[출처: {r['source']}]\n{r['text']}" for r in results
        )
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""다음은 참고 자료입니다:

{context}

---

위 자료를 바탕으로 질문에 답해줘.
- 자료에 근거한 내용만 답해줘. 자료에 없으면 명확히 없다고 말해줘.
- 출처(파일명 또는 채널명)를 함께 표시해줘.
- 한국어로 답해줘.
- **나 __ 같은 마크다운 강조 기호는 절대 사용하지 마. 텍스트만 써.
- ## ### 같은 제목 기호도 쓰지 마.
- 일반 텍스트로만 작성해줘.

질문: {question}"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    text = msg.content[0].text.strip()
    # ** 완전 제거
    text = re.sub(r'\*+', '', text)
    # ## → ◆ 로 변환
    text = re.sub(r'#{1,6}\s*(.+)', r'◆ \1', text)
    # _강조_ 제거
    text = re.sub(r'_{1,2}([^_\n]+)_{1,2}', r'\1', text)
    # > 인용 기호 제거
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # 연속 빈줄 정리
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ── Telegram 핸들러 ────────────────────────────────────────────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or "unknown"
    ext = Path(filename).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        await update.message.reply_text(
            f"❌ 지원하지 않는 형식입니다.\n지원: PDF, Excel, Word, TXT, CSV"
        )
        return

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ 파일 크기가 20MB를 초과합니다.")
        return

    status = await update.message.reply_text(f"📥 {filename} 처리 중...")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = bytes(await tg_file.download_as_bytearray())

        text = extract_from_bytes(file_bytes, filename)
        if not text.strip():
            await status.edit_text(f"❌ {filename}에서 텍스트를 추출할 수 없습니다.")
            return

        new_chunks = split_chunks(text, filename)
        bm25: BM25 = context.bot_data["bm25"]
        context.bot_data["bm25"] = bm25.add_chunks(new_chunks)

        # GitHub에 저장 (백그라운드)
        saved = save_to_github(filename, file_bytes, new_chunks)
        persist_msg = "💾 GitHub 저장 완료" if saved else "⚠️ 이번 세션에만 유효"

        await status.edit_text(
            f"✅ {filename} 처리 완료!\n"
            f"📊 {len(new_chunks)}개 청크 추가\n"
            f"📚 총 {context.bot_data['bm25'].n}개 청크\n"
            f"{persist_msg}\n\n"
            f"이제 이 파일 내용을 질문할 수 있습니다."
        )

    except Exception as e:
        await status.edit_text(f"❌ {type(e).__name__}: {str(e)[:150]}")

async def on_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = (update.message.text or "").strip()
    if not question:
        return

    bm25: BM25 = context.bot_data.get("bm25")
    if bm25 is None or bm25.n == 0:
        await update.message.reply_text(
            "⚠️ 아직 인덱스가 없습니다.\n파일을 업로드하거나 채널 동기화를 먼저 실행해주세요."
        )
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
    await update.message.reply_text(
        f"📚 인덱스: {n}개 청크\n"
        f"📁 파일 업로드: PDF, Excel, Word, TXT 지원\n"
        f"💬 질문: 텍스트 그대로 입력"
    )

async def post_init(application):
    chunks = []
    if INDEX_PATH.exists():
        with open(INDEX_PATH, encoding="utf-8") as f:
            chunks = json.load(f)
    application.bot_data["bm25"] = BM25(chunks) if chunks else BM25([])
    print(f"인덱스 로드 완료: {len(chunks)}개 청크")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("status", on_status))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_question))
    print("QA 봇 실행 중...")
    app.run_polling()

if __name__ == "__main__":
    main()
