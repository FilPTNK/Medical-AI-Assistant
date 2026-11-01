"""
Tìm thêm trên web cho tab Tra y văn — bản tự dựng của bộ "Healthcare Public
Data" mà ChatGPT for Healthcare kết nối (PubMed, ClinicalTrials.gov, nhãn
thuốc FDA/DailyMed), cộng một ô tìm web chung giới hạn trong các tên miền y
khoa tin cậy.

Không dùng MCP server: DeepSeek chỉ có function calling kiểu OpenAI, và bốn
công cụ ở đây chỉ là bốn lệnh REST — gọi thẳng bằng httpx thì không phải nuôi
thêm tiến trình nào, và trần thời gian / bộ nhớ đệm / hạn mức nằm trong tay mình.

Luồng (`gather`):
  1. Hỏi DeepSeek nên gọi công cụ nào với tham số gì. Bước này cần thiết chứ
     không phải trang trí: PubMed, openFDA, ClinicalTrials.gov chỉ hiểu tiếng
     Anh, câu hỏi của bác sĩ thì bằng tiếng Việt — mô hình dịch và chọn từ khoá.
  2. Chạy song song các lệnh gọi được chọn, mỗi lệnh có trần riêng.
  3. Trả về danh sách "nguồn web" cùng dạng với nguồn sách để chung một dãy
     số trích dẫn [n].

Mô hình hỏng / hết giờ ở bước 1 thì rơi về một kế hoạch cố định thay vì bỏ
cả phần web.

Mọi chữ lấy từ web là DỮ LIỆU không đáng tin: nó chỉ đi vào phần Context của
prompt trả lời, nơi quy tắc đã nói rõ Context không phải chỉ dẫn.
"""

import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from openai import OpenAI

import config

# Trần thời gian. Mỗi lệnh gọi dịch vụ ngoài 8s; bước lập kế hoạch 12s. Cả
# phần web vẫn bị main.py kẹp thêm một trần tổng — xem WEB_PHASE_TIMEOUT_S.
HTTP_TIMEOUT = httpx.Timeout(connect=4.0, read=8.0, write=8.0, pool=4.0)
PLANNER_TIMEOUT = httpx.Timeout(connect=4.0, read=12.0, write=8.0, pool=4.0)
TOOL_WAIT_S = 10.0

MAX_RESULTS_PER_TOOL = 3
MAX_TOOL_CALLS = 3
MAX_WEB_SOURCES = 6
# Mỗi nguồn web đưa cho mô hình tối đa ngần này ký tự. Một tóm tắt PubMed dài
# khoảng 1.500–2.500 ký tự; cắt ở đây để sáu nguồn web không đẩy năm trang
# sách ra khỏi cửa sổ ngữ cảnh.
MAX_TEXT_CHARS = 1800

USER_AGENT = "AntigravityMedicalAssistant/1.0 (clinic decision support)"

DEFAULT_DOMAINS = [
    # Việt Nam
    "moh.gov.vn", "kcb.vn", "dav.gov.vn", "vncdc.gov.vn", "msdmanuals.com",
    # Quốc tế — cơ quan y tế và cơ sở dữ liệu
    "who.int", "cdc.gov", "nih.gov", "ncbi.nlm.nih.gov", "medlineplus.gov",
    "fda.gov", "ema.europa.eu", "nice.org.uk", "cochranelibrary.com",
    # Tạp chí
    "nejm.org", "thelancet.com", "bmj.com", "jamanetwork.com",
]

# ---------------------------------------------------------------------------
# Bộ nhớ đệm: cùng một câu hỏi trong một buổi khám thường được hỏi lại vài lần;
# giữ 1 giờ để khỏi tốn hạn mức Tavily/NCBI.
# ---------------------------------------------------------------------------
_CACHE_TTL_S = 3600
_CACHE_MAX = 256
_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
_cache_lock = threading.Lock()


def _cached(key: str, fn: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL_S:
            return hit[1]
    value = fn()
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
        _cache[key] = (now, value)
    return value


def _client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT},
                        follow_redirects=True)


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _hit(provider: str, title: str, url: str, text: str, published: str = "") -> Dict[str, Any]:
    domain = urlparse(url).netloc.removeprefix("www.") if url else provider
    return {
        "kind": "web",
        "provider": provider,
        "title": _clip(title, 220) or domain,
        "url": url,
        "domain": domain,
        "published": published or "",
        "text": _clip(text),
    }


# ---------------------------------------------------------------------------
# Bốn công cụ
# ---------------------------------------------------------------------------

def tim_web(query: str) -> List[Dict[str, Any]]:
    """Tavily, chỉ trong các tên miền y khoa tin cậy."""
    domains = config.WEB_SEARCH_DOMAINS or DEFAULT_DOMAINS
    with _client() as c:
        r = c.post("https://api.tavily.com/search",
                   headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"},
                   json={"query": query, "search_depth": "basic",
                         "max_results": MAX_RESULTS_PER_TOOL,
                         "include_domains": domains, "include_answer": False})
        r.raise_for_status()
        results = r.json().get("results") or []
    return [_hit("Web", x.get("title", ""), x.get("url", ""), x.get("content", ""),
                 x.get("published_date") or "")
            for x in results if x.get("url")]


def tim_pubmed(query_en: str) -> List[Dict[str, Any]]:
    """PubMed qua NCBI E-utilities: esearch lấy PMID, efetch lấy tiêu đề + tóm tắt."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    common = {"db": "pubmed", "tool": "antigravity-medical-assistant"}
    if config.NCBI_API_KEY:
        common["api_key"] = config.NCBI_API_KEY
    with _client() as c:
        r = c.get(f"{base}/esearch.fcgi", params={**common, "term": query_en, "retmode": "json",
                                                  "retmax": MAX_RESULTS_PER_TOOL, "sort": "relevance"})
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist") or []
        if not ids:
            return []
        r = c.get(f"{base}/efetch.fcgi", params={**common, "id": ",".join(ids), "retmode": "xml"})
        r.raise_for_status()
    hits = []
    for art in ET.fromstring(r.content).iter("PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID") or ""
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        abstract = " ".join("".join(t.itertext()) for t in art.iter("AbstractText"))
        journal = art.findtext(".//Journal/Title") or ""
        year = art.findtext(".//JournalIssue/PubDate/Year") or art.findtext(".//JournalIssue/PubDate/MedlineDate") or ""
        hit = _hit("PubMed", title, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                   f"{journal}. {abstract or '(Không có tóm tắt.)'}", year)
        hits.append(hit)
    return hits


_FDA_FIELDS = [
    ("boxed_warning", "Cảnh báo đóng khung"),
    ("indications_and_usage", "Chỉ định"),
    ("dosage_and_administration", "Liều dùng"),
    ("contraindications", "Chống chỉ định"),
    ("warnings_and_cautions", "Cảnh báo"),
    ("drug_interactions", "Tương tác"),
]


def tra_nhan_thuoc_fda(ten_hoat_chat_en: str) -> List[Dict[str, Any]]:
    """Nhãn thuốc FDA (cùng dữ liệu SPL với DailyMed) theo tên hoạt chất."""
    name = re.sub(r'["\\]', "", ten_hoat_chat_en).strip()
    if not name:
        return []
    # Tìm theo cụm từ nên "amoxicillin" khớp cả nhãn amoxicillin + clavulanate;
    # lấy vài nhãn rồi ưu tiên nhãn đơn chất trùng tên.
    params = {"search": f'openfda.generic_name:"{name}"', "limit": 5}
    if config.OPENFDA_API_KEY:
        params["api_key"] = config.OPENFDA_API_KEY
    with _client() as c:
        r = c.get("https://api.fda.gov/drug/label.json", params=params)
        if r.status_code == 404:   # openFDA trả 404 khi không có kết quả
            return []
        r.raise_for_status()
        results = r.json().get("results") or []
    exact = [lab for lab in results
             if name.casefold() in [g.casefold() for g in (lab.get("openfda") or {}).get("generic_name") or []]]
    hits = []
    for lab in (exact or results)[:1]:
        parts = []
        for key, label in _FDA_FIELDS:
            if lab.get(key):
                parts.append(f"{label}: {_clip(' '.join(lab[key]), 500)}")
        brand = ", ".join((lab.get("openfda") or {}).get("brand_name") or [])
        set_id = lab.get("set_id", "")
        url = f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}" if set_id else "https://open.fda.gov/"
        eff = lab.get("effective_time", "")
        hits.append(_hit("Nhãn thuốc FDA", f"Nhãn FDA — {name}" + (f" ({brand})" if brand else ""),
                         url, " ".join(parts), eff[:4]))
    return hits


def tim_thu_nghiem_lam_sang(query_en: str) -> List[Dict[str, Any]]:
    """ClinicalTrials.gov API v2."""
    with _client() as c:
        r = c.get("https://clinicaltrials.gov/api/v2/studies", params={
            "query.term": query_en, "pageSize": MAX_RESULTS_PER_TOOL,
            "fields": "NCTId,BriefTitle,OverallStatus,Phase,BriefSummary,StartDate,Condition",
        })
        r.raise_for_status()
        studies = r.json().get("studies") or []
    hits = []
    for s in studies:
        p = s.get("protocolSection", {})
        nct = p.get("identificationModule", {}).get("nctId", "")
        title = p.get("identificationModule", {}).get("briefTitle", "")
        status = p.get("statusModule", {}).get("overallStatus", "")
        start = p.get("statusModule", {}).get("startDateStruct", {}).get("date", "")
        phases = ", ".join(x for x in (p.get("designModule", {}).get("phases") or []) if x != "NA")
        summary = p.get("descriptionModule", {}).get("briefSummary", "")
        hits.append(_hit("ClinicalTrials.gov", f"{nct}: {title}", f"https://clinicaltrials.gov/study/{nct}",
                         f"Trạng thái: {status}. {('Pha: ' + phases + '. ') if phases else ''}{summary}",
                         start[:4]))
    return hits


# Khai báo cho DeepSeek (function calling kiểu OpenAI).
_TOOL_SPECS: Dict[str, Dict[str, Any]] = {
    "tim_web": {
        "fn": tim_web, "arg": "query",
        "needs": lambda: bool(config.TAVILY_API_KEY),
        "description": ("Tìm web trong các trang y khoa tin cậy (Bộ Y tế, Cục Quản lý Dược, WHO, CDC, "
                        "NICE, MSD Manuals, tạp chí lớn). Dùng cho hướng dẫn điều trị, khuyến cáo, "
                        "thông tin cập nhật, đặc biệt nguồn tiếng Việt."),
        "param": "Câu tìm kiếm, tiếng Việt hoặc tiếng Anh tuỳ nguồn muốn tìm.",
    },
    "tim_pubmed": {
        "fn": tim_pubmed, "arg": "query_en", "needs": lambda: True,
        "description": "Tìm bài báo y khoa trên PubMed (tiêu đề + tóm tắt). Dùng cho bằng chứng nghiên cứu.",
        "param": "Truy vấn PubMed bằng TIẾNG ANH, ngắn gọn, có thể dùng MeSH/AND/OR.",
    },
    "tra_nhan_thuoc_fda": {
        "fn": tra_nhan_thuoc_fda, "arg": "ten_hoat_chat_en", "needs": lambda: True,
        "description": ("Tra nhãn thuốc chính thức của FDA Mỹ (chỉ định, liều, chống chỉ định, cảnh báo, "
                        "tương tác) theo tên hoạt chất. Chỉ dùng khi câu hỏi về MỘT thuốc cụ thể."),
        "param": "Tên hoạt chất (generic name) bằng TIẾNG ANH, vd. 'amoxicillin'.",
    },
    "tim_thu_nghiem_lam_sang": {
        "fn": tim_thu_nghiem_lam_sang, "arg": "query_en", "needs": lambda: True,
        "description": "Tìm thử nghiệm lâm sàng trên ClinicalTrials.gov. Chỉ dùng khi hỏi về thử nghiệm/nghiên cứu đang diễn ra.",
        "param": "Bệnh hoặc can thiệp bằng TIẾNG ANH.",
    },
}


def available_tools() -> List[str]:
    if not config.WEB_SEARCH_ENABLED:
        return []
    return [name for name, spec in _TOOL_SPECS.items() if spec["needs"]()]


def _openai_tools(names: List[str]) -> List[Dict[str, Any]]:
    return [{
        "type": "function",
        "function": {
            "name": n,
            "description": _TOOL_SPECS[n]["description"],
            "parameters": {
                "type": "object",
                "properties": {_TOOL_SPECS[n]["arg"]: {"type": "string", "description": _TOOL_SPECS[n]["param"]}},
                "required": [_TOOL_SPECS[n]["arg"]],
            },
        },
    } for n in names]


_PLANNER_PROMPT = (
    "Bạn chọn công cụ tìm kiếm để bổ sung bằng chứng cho câu hỏi y khoa của bác sĩ. "
    "Gọi từ 1 đến 3 công cụ phù hợp nhất, có thể gọi song song. Với PubMed, nhãn FDA và "
    "ClinicalTrials.gov phải viết tham số bằng tiếng Anh. "
    "TUYỆT ĐỐI không đưa tên, tuổi, ngày sinh, số điện thoại, địa chỉ hay mã hồ sơ của bệnh "
    "nhân vào tham số — chỉ giữ thuật ngữ y khoa. Không trả lời câu hỏi, chỉ gọi công cụ."
)


def plan(query: str, api_key: str, names: List[str]) -> List[Tuple[str, str]]:
    """[(tên công cụ, tham số)] do mô hình chọn. Hỏng thì ném lỗi — bên gọi tự rơi về kế hoạch cố định."""
    client = OpenAI(api_key=api_key, base_url=config.DEEPSEEK_API_URL,
                    timeout=PLANNER_TIMEOUT, max_retries=0)
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[{"role": "system", "content": _PLANNER_PROMPT},
                  {"role": "user", "content": query}],
        tools=_openai_tools(names),
        tool_choice="auto",
        temperature=0,
        max_tokens=300,
    )
    calls: List[Tuple[str, str]] = []
    for tc in (resp.choices[0].message.tool_calls or []):
        name = tc.function.name
        if name not in names:
            continue
        try:
            args = json.loads(tc.function.arguments or "{}")
        except ValueError:
            continue
        value = str(args.get(_TOOL_SPECS[name]["arg"]) or "").strip()
        if value and (name, value) not in calls:
            calls.append((name, value[:300]))
    return calls[:MAX_TOOL_CALLS]


def fallback_plan(query: str, names: List[str]) -> List[Tuple[str, str]]:
    """Khi không có mô hình để lập kế hoạch: tìm web chung bằng chính câu hỏi.

    Không gọi PubMed bằng câu tiếng Việt — gần như luôn ra 0 kết quả, chỉ tốn
    một lượt gọi và làm bác sĩ tưởng PubMed không có gì.
    """
    return [("tim_web", query[:300])] if "tim_web" in names else []


def run_tool(name: str, arg: str) -> List[Dict[str, Any]]:
    fn = _TOOL_SPECS[name]["fn"]
    return _cached(f"{name}\x00{arg.casefold()}", lambda: fn(arg))


def gather(query: str, api_key: str) -> Dict[str, Any]:
    """Chạy cả phần web. Không bao giờ ném lỗi: hỏng chỗ nào thì ghi vào `errors`.

    Trả về {"sources": [...], "calls": [{"tool", "arg", "count"|"error"}], "errors": [...]}.
    """
    names = available_tools()
    out: Dict[str, Any] = {"sources": [], "calls": [], "errors": []}
    if not names:
        out["errors"].append("Chưa bật công cụ tìm web nào.")
        return out

    calls: List[Tuple[str, str]] = []
    if api_key:
        try:
            calls = plan(query, api_key, names)
        except Exception as e:
            out["errors"].append(f"Lập kế hoạch tìm kiếm lỗi: {type(e).__name__}")
    if not calls:
        calls = fallback_plan(query, names)
    if not calls:
        out["errors"].append("Không chọn được công cụ tìm kiếm phù hợp.")
        return out

    pool = ThreadPoolExecutor(max_workers=len(calls))
    try:
        futures = {pool.submit(run_tool, n, a): (n, a) for n, a in calls}
        done, _ = wait(futures, timeout=TOOL_WAIT_S)
        seen_urls = set()
        for fut, (name, arg) in futures.items():
            entry: Dict[str, Any] = {"tool": name, "arg": arg}
            if fut not in done:
                entry["error"] = "hết thời gian"
            elif fut.exception() is not None:
                entry["error"] = type(fut.exception()).__name__
            else:
                hits = [h for h in fut.result() if h["url"] not in seen_urls]
                seen_urls.update(h["url"] for h in hits)
                entry["count"] = len(hits)
                out["sources"].extend(hits)
            out["calls"].append(entry)
    finally:
        # Không chờ lệnh treo: httpx tự cắt nó theo HTTP_TIMEOUT.
        pool.shutdown(wait=False, cancel_futures=True)

    out["sources"] = out["sources"][:MAX_WEB_SOURCES]
    return out
