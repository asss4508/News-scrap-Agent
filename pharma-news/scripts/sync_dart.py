import os
import re
import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

DART_API_KEY = os.environ.get("DART_API_KEY", "")
BASE_DIR = Path(__file__).parent.parent.parent
CHANNELS_DIR = BASE_DIR / "data" / "channels"
COMPANIES_FILE = BASE_DIR / "data" / "dart_companies.txt"

IMPORTANT_TYPES = {"사업보고서", "분기보고서", "반기보고서", "주요사항보고서", "투자설명서"}


def load_companies() -> list[str]:
    if not COMPANIES_FILE.exists():
        return []
    result = []
    for line in COMPANIES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            result.append(line)
    return result


def search_disclosures(corp_name: str, days: int = 7) -> list:
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key": DART_API_KEY,
                "corp_name": corp_name,
                "bgn_de": start_date,
                "end_de": end_date,
                "page_count": 20,
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("status") == "000":
            return data.get("list", [])
    except Exception as e:
        print(f"  DART API 오류 ({corp_name}): {e}")
    return []


def fetch_document_text(rcept_no: str) -> str:
    dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
    jina_url = f"https://r.jina.ai/{dart_url}"
    try:
        resp = requests.get(jina_url, timeout=30, headers={"Accept": "text/plain"})
        if resp.status_code == 200:
            text = resp.text.strip()
            # 앞 4000자만 사용 (청크로 나뉨)
            return text[:4000]
    except Exception as e:
        print(f"  문서 추출 오류 ({rcept_no}): {e}")
    return ""


def sync_company(corp_name: str) -> int:
    disclosures = search_disclosures(corp_name)
    if not disclosures:
        print(f"  {corp_name}: 최근 공시 없음")
        return 0

    lines = []
    for d in disclosures:
        title = d.get("report_nm", "").strip()
        date = d.get("rcept_dt", "")
        rcept_no = d.get("rcept_no", "")
        corp = d.get("corp_name", corp_name)

        lines.append(f"[{date}] {corp} 공시: {title}")

        if any(kw in title for kw in IMPORTANT_TYPES):
            doc_text = fetch_document_text(rcept_no)
            if doc_text:
                lines.append(doc_text)

        lines.append("")

    safe_name = re.sub(r"[^a-zA-Z0-9가-힣_]", "_", corp_name)
    out_path = CHANNELS_DIR / f"dart_{safe_name}.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {corp_name}: {len(disclosures)}개 공시 저장 → {out_path.name}")
    return len(disclosures)


def main():
    if not DART_API_KEY:
        print("DART_API_KEY 환경변수가 없습니다.")
        return

    CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
    companies = load_companies()
    if not companies:
        print("dart_companies.txt에 회사 목록이 없습니다.")
        return

    print(f"DART 동기화 시작: {len(companies)}개 회사")
    total = 0
    for company in companies:
        print(f"동기화 중: {company}")
        total += sync_company(company)

    print(f"\nDART 동기화 완료: 총 {total}개 공시")


if __name__ == "__main__":
    main()
