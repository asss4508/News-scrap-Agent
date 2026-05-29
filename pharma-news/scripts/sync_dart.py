import io
import json
import os
import re
import requests
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

DART_API_KEY = os.environ.get("DART_API_KEY", "")
BASE_DIR = Path(__file__).parent.parent.parent
CHANNELS_DIR = BASE_DIR / "data" / "channels"
CORP_CACHE_FILE = BASE_DIR / "data" / "dart_corp_cache.json"

# 이 공시 유형은 전문 텍스트까지 수집
FULL_TEXT_TYPES = {"사업보고서", "분기보고서", "반기보고서"}
FULL_TEXT_LIMIT = 30   # 하루 최대 전문 수집 건수 (Jina API 부하 제한)

# DART 공식 보고서명 → 검색 가능한 한국어 설명 매핑
REPORT_LABELS = {
    "임원ㆍ주요주주특정증권등소유상황보고서": "내부자 주식 매수/매도 공시 (임원·주요주주 지분 변동)",
    "임원·주요주주특정증권등소유상황보고서": "내부자 주식 매수/매도 공시 (임원·주요주주 지분 변동)",
    "주요사항보고서": "주요사항보고서 (유상증자·무상증자·합병·분할·자산양수도 등 중요 이벤트)",
    "사업보고서": "연간 사업보고서 (연간 실적·재무제표·사업현황)",
    "분기보고서": "분기 실적보고서 (분기 실적·재무제표)",
    "반기보고서": "반기 실적보고서 (상반기 실적·재무제표)",
    "증권신고서": "증권신고서 (유상증자·공모·IPO)",
    "공개매수신고서": "공개매수 공시 (M&A·경영권 인수)",
    "합병등종료보고서": "합병 완료 보고서",
    "감사보고서": "외부감사 감사보고서",
    "소액공모공시서류": "소액공모 공시",
    "자기주식취득결과보고서": "자사주 매입 결과 공시",
    "자기주식처분결과보고서": "자사주 처분(매도) 결과 공시",
    "조정공시": "조정 공시",
}


def get_listed_companies() -> dict:
    """코스피/코스닥 상장사 corp_code 목록 반환 (7일 캐시)"""
    if CORP_CACHE_FILE.exists():
        age = datetime.now().timestamp() - CORP_CACHE_FILE.stat().st_mtime
        if age < 7 * 86400:
            with open(CORP_CACHE_FILE, encoding="utf-8") as f:
                companies = json.load(f)
            print(f"캐시 로드: 상장사 {len(companies)}개")
            return companies

    print("DART 전체 법인 코드 다운로드 중...")
    resp = requests.get(
        "https://opendart.fss.or.kr/api/corpCode.xml",
        params={"crtfc_key": DART_API_KEY},
        timeout=60,
    )
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        xml_data = z.read("CORPCODE.xml")

    root = ET.fromstring(xml_data)
    companies = {}
    for item in root.findall("list"):
        stock_code = item.findtext("stock_code", "").strip()
        if stock_code:  # stock_code 있으면 상장사
            corp_code = item.findtext("corp_code", "").strip()
            corp_name = item.findtext("corp_name", "").strip()
            if corp_code:
                companies[corp_code] = corp_name

    CORP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CORP_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False)
    print(f"상장사 {len(companies)}개 코드 다운로드 완료")
    return companies


def fetch_all_disclosures(days: int = 7) -> list:
    """최근 N일간 전체 공시 페이지네이션 수집"""
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    all_items = []
    page = 1
    while True:
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": DART_API_KEY,
                    "bgn_de": start_date,
                    "end_de": end_date,
                    "page_no": page,
                    "page_count": 100,
                },
                timeout=15,
            )
            data = resp.json()
        except Exception as e:
            print(f"  페이지 {page} 오류: {e}")
            break

        if data.get("status") != "000":
            print(f"  API 오류: {data.get('message', '')}")
            break
        items = data.get("list", [])
        if not items:
            break
        all_items.extend(items)
        total = int(data.get("total_count", 0))
        print(f"  공시 수집 중: {len(all_items)}/{total}건")
        if len(all_items) >= total:
            break
        page += 1

    return all_items


def fetch_document_text(rcept_no: str) -> str:
    dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
    jina_url = f"https://r.jina.ai/{dart_url}"
    try:
        resp = requests.get(jina_url, timeout=30, headers={"Accept": "text/plain"})
        if resp.status_code == 200:
            return resp.text.strip()[:4000]
    except Exception as e:
        print(f"  문서 추출 오류 ({rcept_no}): {e}")
    return ""


def main():
    if not DART_API_KEY:
        print("DART_API_KEY 환경변수가 없습니다.")
        return

    CHANNELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 상장사 코드 목록 로드
    listed_companies = get_listed_companies()
    print(f"\n대상: 코스피/코스닥 상장사 {len(listed_companies)}개")

    # 2. 최근 7일 전체 공시 수집
    print("\n최근 7일 공시 수집 중...")
    all_disclosures = fetch_all_disclosures(days=7)

    # 3. 상장사 공시만 필터링
    listed = [d for d in all_disclosures if d.get("corp_code", "") in listed_companies]
    print(f"\n상장사 공시 {len(listed)}건 (전체 {len(all_disclosures)}건 중 필터링)")

    # 4. 회사별 그룹핑
    by_company: dict[str, list] = {}
    for d in listed:
        by_company.setdefault(d.get("corp_name", ""), []).append(d)

    # 5. 텍스트 구성
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"# 코스피/코스닥 전체 상장사 DART 공시 ({today} 기준 최근 7일)\n"]
    full_text_count = 0

    for corp_name, disclosures in sorted(by_company.items()):
        lines.append(f"[{corp_name}]")
        for d in disclosures:
            title = d.get("report_nm", "").strip()
            date = d.get("rcept_dt", "")
            rcept_no = d.get("rcept_no", "")
            # 공식 보고서명에 사람이 검색하는 한국어 설명 추가
            label = ""
            for key, desc in REPORT_LABELS.items():
                if key in title:
                    label = f" → {desc}"
                    break
            lines.append(f"  {date}: {corp_name} {title}{label}")

            # 분기/사업/반기보고서는 전문 수집 (일일 최대 FULL_TEXT_LIMIT건)
            if full_text_count < FULL_TEXT_LIMIT and any(kw in title for kw in FULL_TEXT_TYPES):
                doc_text = fetch_document_text(rcept_no)
                if doc_text:
                    lines.append(f"  [전문 요약]\n{doc_text}\n")
                    full_text_count += 1
        lines.append("")

    out_path = CHANNELS_DIR / "dart_상장사공시.txt"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n저장 완료: {out_path.name} ({len(listed)}건, 전문 {full_text_count}건)")


if __name__ == "__main__":
    main()
