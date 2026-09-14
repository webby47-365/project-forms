"""정적 사이트 생성기: catalog.json + categories.json → HTML.

생성물은 public/ 아래에 놓이며, 이 폴더가 Cloudflare Pages 배포 대상이다.
서식 파일(public/files/…)은 build_form.py가 이미 만들어 두었으므로 건드리지 않는다.

사용법:
    python scripts/build_site.py
"""

from __future__ import annotations

import json
import math
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
PUBLIC = ROOT / "public"
CATALOG = ROOT / "catalog" / "catalog.json"
CATEGORIES = ROOT / "catalog" / "categories.json"
ADS = ROOT / "catalog" / "ads.json"
REQUESTS = ROOT / "catalog" / "requests.json"
COLLECTIONS = ROOT / "catalog" / "collections.json"

SITE_NAME = "무료서식 다운로드"
SITE_URL = "https://freeforms.kr"  # canonical·sitemap·JSON-LD에 사용

# 운영자 표기와 문의처. 개인정보처리방침·푸터에 그대로 나간다.
BIZ_NAME = "(주)프라임리츠"
BIZ_NUMBER = "576-81-02412"
CONTACT_EMAIL = "sherlockreturns365@gmail.com"
PRIVACY_EFFECTIVE = "2026년 9월 14일"  # 처리방침 시행일. 내용을 고칠 때 함께 갱신한다
# Google Analytics 4 측정 ID. 빈 문자열이면 추적 스크립트를 아예 내보내지 않는다.
GA4_ID = "G-912YLRDN2B"
KST = timezone(timedelta(hours=9))

RECENT_COUNT = 10
RELATED_COUNT = 10       # 상세 화면 '함께 찾는 서식' 개수
TAG_MIN_FORMS = 3        # 태그 허브를 만들 최소 서식 수 (이보다 적으면 얇은 페이지가 된다)
TICKER_COUNT = 5  # 상단 롤링바에 띄울 최근 추가 서식 수
RSS_COUNT = 30    # RSS 피드에 담을 최근 서식 수 (네이버 서치어드바이저 RSS 제출용)

# robots.txt에 이름을 적어 둘 크롤러. 기본값이 이미 전체 허용이지만, AI 검색 크롤러는
# 자기 이름이 적힌 규칙을 우선해서 보는 경우가 있어 명시해 둔다.
# Google-Extended / Applebot-Extended 는 '검색 노출'이 아니라 '학습 사용' 동의 스위치다.
AI_CRAWLERS = [
    ("GPTBot", "OpenAI 학습"),
    ("OAI-SearchBot", "ChatGPT 검색"),
    ("ChatGPT-User", "ChatGPT 사용자 열람"),
    ("ClaudeBot", "Anthropic 학습"),
    ("Claude-SearchBot", "Claude 검색"),
    ("Claude-User", "Claude 사용자 열람"),
    ("PerplexityBot", "Perplexity 색인"),
    ("Perplexity-User", "Perplexity 사용자 열람"),
    ("Google-Extended", "Gemini·AI 개요"),
    ("Applebot-Extended", "Apple Intelligence"),
    ("Amazonbot", "Alexa"),
    ("meta-externalagent", "Meta AI"),
    ("CCBot", "Common Crawl"),
]
# 국내 검색엔진 크롤러. 네이버 Yeti / 다음 Daumoa
KR_CRAWLERS = [("Yeti", "네이버"), ("Daumoa", "다음")]

FMT_LABEL = {"pdf": "PDF", "docx": "Word (DOCX)", "hwpx": "한글 (HWPX)"}

# 파일명에 쓸 수 없는 문자 (Windows 기준)
_BAD_FILENAME_CHARS = '\\/:*?"<>|'


def download_name(title: str, ext: str) -> str:
    """브라우저가 저장할 한글 파일명을 만든다.

    URL은 영문 ID를 유지하고(공유·검색에 유리), 저장되는 이름만 한글로 바꾼다.
    HTML의 download 속성에 넣으며, 같은 출처의 파일에만 적용된다.
    """
    name = title
    for ch in _BAD_FILENAME_CHARS:
        name = name.replace(ch, "_")
    return f"{name.strip().rstrip('.')}.{ext}"

# 광고 설정 기본값. catalog/ads.json이 없거나 항목이 빠져 있어도 안전하게 동작한다.
ADS_DEFAULT: dict[str, Any] = {
    "enabled": False,
    "client": "",
    "auto_ads": True,
    "download_interstitial": False,
    "download_delay_sec": 2,
    "slots": {},
}


def load_ads() -> dict[str, Any]:
    """광고 설정을 읽는다. 파일이 없으면 '광고 없음' 상태로 동작한다."""
    cfg = dict(ADS_DEFAULT)
    if ADS.exists():
        try:
            raw = json.loads(ADS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SiteBuildError(f"ads.json 파싱 실패 — {exc}") from exc
        for key in ADS_DEFAULT:
            if key in raw:
                cfg[key] = raw[key]
    cfg["slots"] = {k: v for k, v in (cfg.get("slots") or {}).items() if v}
    # 광고를 켜지 않았거나 클라이언트 ID가 없으면 중간 페이지도 만들지 않는다
    if not (cfg["enabled"] and cfg["client"]):
        cfg["enabled"] = False
        cfg["download_interstitial"] = False
    return cfg


# 방문자 서식 요청 접수 설정 기본값. 파일이 없거나 항목이 빠져도 '꺼짐'으로 동작한다.
REQUESTS_DEFAULT: dict[str, Any] = {
    "enabled": False,
    "endpoint": "",
    "max_title": 40,
    "max_purpose": 120,
}


def load_requests() -> dict[str, Any]:
    """요청 접수 설정을 읽는다. 접수 주소가 없으면 폼을 전혀 내보내지 않는다."""
    cfg = dict(REQUESTS_DEFAULT)
    if REQUESTS.exists():
        try:
            raw = json.loads(REQUESTS.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SiteBuildError(f"requests.json 파싱 실패 — {exc}") from exc
        for key in REQUESTS_DEFAULT:
            if key in raw:
                cfg[key] = raw[key]
    # 광고와 같은 2단계 게이트: 켜짐 + 주소가 모두 있어야 화면에 나온다
    if not (cfg["enabled"] and cfg["endpoint"]):
        cfg["enabled"] = False
    return cfg


def download_urls(form_id: str, interstitial: bool) -> dict[str, str]:
    """형식별 다운로드 링크. 중간 페이지 사용 여부에 따라 경로가 달라진다."""
    if interstitial:
        return {ext: f"/download/{form_id}/{ext}/" for ext in ("pdf", "docx", "hwpx")}
    return {ext: f"/files/{form_id}/{form_id}.{ext}" for ext in ("pdf", "docx", "hwpx")}


def tag_slug(tag: str) -> str:
    """태그를 URL·폴더에 쓸 수 있는 이름으로 바꾼다.

    한글·영문·숫자만 남기고 나머지는 하이픈으로 바꾼다. 슬래시·콜론이 든 태그가
    폴더 경로를 깨뜨리는 것을 막는다.
    """
    out = []
    for ch in tag.strip():
        if ch.isalnum() or "\uac00" <= ch <= "\ud7a3":
            out.append(ch.lower())
        else:
            out.append("-")
    return "-".join(x for x in "".join(out).split("-") if x)


# 분량·문체를 설명하는 말. 용도와 무관한데 서식 몇 종에만 나와 가중치가 커지므로 뺀다.
_STOP = {
    "간편", "간편형", "기본", "기본형", "간단히", "간단한", "빠르게", "한눈에",
    "페이지", "분량", "양식", "서식", "서식입니다", "문서", "작성", "사용",
    "표준", "무료", "다운로드", "한장", "반",
}


def _tokens(f: dict[str, Any]) -> set[str]:
    """유사도 계산용 토큰. 제목·태그·요약·작성요령에서 뽑는다.

    한국어는 어미가 붙어 어절이 그대로 겹치는 일이 드물다. 그래서 어절과 함께
    두 글자 조각도 넣어 '사직'·'퇴직' 같은 부분 일치를 잡는다.
    """
    # 제목의 괄호 안(간편형·기본형 등 변형 이름)은 뺀다. 견적서(간편형)과
    # 사직서(간편형)처럼 용도가 전혀 다른 서식이 '간편형' 때문에 묶이기 때문이다.
    # 작성요령(usage)은 '빠르게·간단히' 같은 문체가 섞여 오히려 잡음이 되므로 쓰지 않는다.
    title = re.sub(r"\([^)]*\)", " ", f.get("title", ""))
    txt = " ".join([title, " ".join(f.get("tags", [])), f.get("summary", "")])
    txt = re.sub(r"[^가-힣A-Za-z0-9 ]", " ", txt).lower()
    out: set[str] = set()
    for word in txt.split():
        if word in _STOP:
            continue
        if len(word) >= 2:
            out.add(word)
        if len(word) >= 3:
            for i in range(len(word) - 1):
                out.add(word[i:i + 2])
    return out


def related_forms(
    target: dict[str, Any],
    forms: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    tokens: dict[str, set[str]],
    idf: dict[str, float],
    limit: int,
) -> list[dict[str, Any]]:
    """'함께 찾는 서식'을 고른다.

    1) 명세의 related에 사람이 적어 둔 서식을 앞에 놓는다 (사직서 → 인수인계서처럼
       글자는 안 겹치지만 실제로 함께 쓰는 관계는 기계가 알 수 없다).
    2) 남는 자리는 본문 유사도 + 같은 분류 가점으로 채운다.
    계열 서식은 상세 화면 위쪽 목록에 이미 나오므로 제외한다.
    """
    my_series = target.get("series") or ""
    picked: list[dict[str, Any]] = []
    seen = {target["id"]}

    for rid in target.get("related", []):
        f = by_id.get(rid)
        if f and f["id"] not in seen:
            picked.append(f)
            seen.add(f["id"])

    if len(picked) >= limit:
        return picked[:limit]

    mine = tokens[target["id"]]
    mine_norm = sum(idf.get(w, 0.0) for w in mine) or 1.0
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for f in forms:
        if f["id"] in seen:
            continue
        if my_series and f.get("series") == my_series:
            continue
        other = tokens[f["id"]]
        shared = mine & other
        if not shared:
            continue
        num = sum(idf.get(w, 0.0) for w in shared)
        den = (mine_norm * (sum(idf.get(w, 0.0) for w in other) or 1.0)) ** 0.5
        score = num / den
        if f["category"] == target["category"]:
            score += 0.04
            if f["subcategory"] == target["subcategory"]:
                score += 0.06
        scored.append((-score, f["title"], f))
    scored.sort(key=lambda x: (x[0], x[1]))
    picked.extend(f for _, _, f in scored[:limit - len(picked)])
    return picked


class SiteBuildError(RuntimeError):
    """사이트 빌드 실패."""


def load_json(path: Path) -> dict[str, Any]:
    """JSON 파일을 읽는다."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SiteBuildError(f"파일이 없습니다: {path} — 먼저 build_form.py를 실행하십시오.") from exc
    except json.JSONDecodeError as exc:
        raise SiteBuildError(f"{path.name} 파싱 실패 — {exc}") from exc


def write(path: Path, html: str) -> None:
    """HTML을 UTF-8·LF로 저장한다.

    newline="\\n"을 지정하지 않으면 Windows에서 줄바꿈이 CRLF로 바뀌어 저장되고,
    저장소는 LF로 보관하므로(.gitattributes) 커밋할 때마다 변환 경고가 쏟아진다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8", newline="\n")



def jd(obj: Any) -> str:
    """구조화 데이터를 한 줄 JSON 문자열로 만든다.

    템플릿에서는 반드시 `| safe` 로 출력해야 한다. 자동 이스케이프가 걸리면
    큰따옴표가 `&#34;` 로 바뀌는데, <script> 안에서는 문자참조가 되돌아가지 않아
    검색엔진이 JSON을 아예 파싱하지 못한다(실제로 그 상태로 배포돼 있었다).
    """
    return json.dumps(obj, ensure_ascii=False, indent=None)


def breadcrumb_ld(trail: list[tuple[str, str]]) -> str:
    """빵부스러기 구조화 데이터. trail은 (이름, 경로) 순서쌍이며 마지막이 현재 위치다.

    검색결과에 `홈 > 기업 > 인사·노무 > 사직서` 형태의 경로가 표시된다.
    화면에는 이미 있었지만 구조화 데이터가 없어 검색엔진이 읽지 못했다.
    """
    return jd({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name,
             "item": f"{SITE_URL}{path}"}
            for i, (name, path) in enumerate(trail, start=1)
        ],
    })


def form_date(f: dict[str, Any], field: str = "updated_at") -> str:
    """서식의 날짜를 YYYY-MM-DD로 돌려준다. 비어 있으면 등록일, 그것도 없으면 빈 문자열."""
    return (f.get(field) or f.get("created_at") or "")[:10]


def rfc822(day: str) -> str:
    """YYYY-MM-DD → RSS가 요구하는 RFC822 날짜 문자열(KST 기준)."""
    if not day:
        day = datetime.now(KST).strftime("%Y-%m-%d")
    try:
        dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST)
    except ValueError:
        dt = datetime.now(KST)
    return dt.strftime("%a, %d %b %Y 00:00:00 +0900")


def xml_text(s: str) -> str:
    """XML 본문에 안전하게 넣을 수 있게 &, <, > 를 바꾼다."""
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def make_og_default(dest: Path) -> bool:
    """공유 카드 기본 이미지를 assets/에서 public/으로 복사한다.

    파일이 없어도 빌드를 멈추지 않는다(그 경우 공유 카드에 이미지가 빠질 뿐이다).
    """
    src = ROOT / "assets" / "og-default.png"
    if not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    return True


def build() -> int:
    """사이트 전체를 생성하고 만들어진 페이지 수를 반환한다."""
    catalog = load_json(CATALOG)
    cats_data = load_json(CATEGORIES)
    ads = load_ads()
    reqs = load_requests()
    categories: list[dict[str, Any]] = sorted(
        cats_data["categories"], key=lambda c: c.get("order", 99))

    forms = [f for f in catalog["forms"] if f.get("status", "published") == "published"]
    if not forms:
        raise SiteBuildError("게시 상태(published) 서식이 없습니다.")

    by_id = {f["id"]: f for f in forms}

    # '함께 찾는 서식' 유사도 계산용 표. 한 번만 만들어 전 서식이 돌려 쓴다.
    # idf: 여러 서식에 흔히 나오는 말('서식', '작성')의 가중치를 낮춘다.
    tokens = {f["id"]: _tokens(f) for f in forms}
    df: dict[str, int] = {}
    for toks in tokens.values():
        for w in toks:
            df[w] = df.get(w, 0) + 1
    total_docs = len(forms)
    idf = {w: math.log(total_docs / (1 + n)) + 1.0 for w, n in df.items()}

    sub_name = {
        f"{c['key']}/{s['key']}": (c["name"], s["name"])
        for c in categories for s in c["subcategories"]
    }
    cat_obj = {c["key"]: c for c in categories}

    # 분류별 집계와 표시용 라벨
    counts: dict[str, int] = {k: 0 for k in sub_name}
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in sub_name}
    cat_label: dict[str, str] = {}
    for f in forms:
        key = f"{f['category']}/{f['subcategory']}"
        if key not in sub_name:
            raise SiteBuildError(
                f"{f['id']}: categories.json에 없는 분류 '{key}' — 명세를 수정하십시오.")
        counts[key] += 1
        grouped[key].append(f)
        cat_label[f["id"]] = " · ".join(sub_name[key])

    for key in grouped:
        grouped[key].sort(key=lambda f: (-f.get("downloads", 0), f["title"]))

    # 계열(series): 같은 서식의 실무 변형을 상세 화면에서 함께 보여주기 위한 묶음.
    # 예) 이력서 → 기본형·신입용·경력용·서술형·간편형·아르바이트용·영문
    series: dict[str, list[dict[str, Any]]] = {}
    for f in forms:
        if f.get("series"):
            series.setdefault(f["series"], []).append(f)
    for key in series:
        series[key].sort(key=lambda f: (f.get("variant_rank", 99), f["title"]))
    # 변형이 하나뿐인 계열은 보여줄 것이 없으므로 묶음에서 뺀다
    series = {k: v for k, v in series.items() if len(v) > 1}

    # 주제 모음(collection): 분류가 달라도 한 가지 일에 연달아 쓰는 서식 묶음.
    # 파일이 없으면 기능을 끄고 넘어간다(빌드는 멈추지 않는다).
    collections: list[dict[str, Any]] = []
    if COLLECTIONS.exists():
        for c in load_json(COLLECTIONS).get("collections", []):
            members = []
            for fid in c["ids"]:
                f = by_id.get(fid)
                if f is None:
                    raise SiteBuildError(
                        f"collections.json '{c['key']}': 없는 서식 id '{fid}' — "
                        f"명세를 먼저 등록하거나 목록에서 빼십시오.")
                if f not in members:
                    members.append(f)
            if len(members) < 4:
                raise SiteBuildError(
                    f"collections.json '{c['key']}': 서식이 {len(members)}종뿐입니다(최소 4종).")
            collections.append({**c, "forms": members, "count": len(members)})
    collection_hubs = [
        {"key": c["key"], "name": c["name"], "count": c["count"]} for c in collections
    ]
    # 상세 화면에서 '이 서식이 들어 있는 모음'을 보여주기 위한 역참조표
    in_collections: dict[str, list[dict[str, str]]] = {}
    for c in collections:
        for f in c["forms"]:
            in_collections.setdefault(f["id"], []).append(
                {"key": c["key"], "name": c["name"]})

    # 계열 허브 목록 (메인·허브 상호 링크용). 종수가 많은 계열을 앞에 둔다.
    series_hubs = sorted(
        ({"key": k, "name": v[0].get("series_name") or k, "count": len(v)}
         for k, v in series.items()),
        key=lambda h: (-h["count"], h["name"]),
    )

    # 메인 노출 순서: 명세의 featured_rank → 다운로드 수 → 제목
    featured = sorted(
        (f for f in forms if f.get("featured")),
        key=lambda f: (f.get("featured_rank", 99), -f.get("downloads", 0), f["title"]),
    )[:10]
    recent = sorted(forms, key=lambda f: f.get("created_at", ""), reverse=True)[:RECENT_COUNT]

    # 상단 롤링바: 최근 추가 서식 5종. 빌드할 때마다 카탈로그에서 다시 뽑으므로
    # 일일 에이전트가 서식을 등록하면 별도 작업 없이 이 띠도 함께 갱신된다.
    ticker = [
        {
            "id": f["id"],
            "title": f["title"],
            "date": f.get("created_at", "")[:10].replace("-", "/"),
        }
        for f in recent[:TICKER_COUNT]
    ]

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    now = datetime.now(KST)
    common = {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "ga4_id": GA4_ID,
        "categories": categories,
        "counts": counts,
        "cat_label": cat_label,
        "total_forms": len(forms),
        "updated": now.strftime("%Y-%m-%d"),
        "ticker": ticker,
        "series_hubs": series_hubs,
        "collection_hubs": collection_hubs,
        "ads": ads,
        "reqs": reqs,
        "biz_name": BIZ_NAME,
        "biz_number": BIZ_NUMBER,
        "contact_email": CONTACT_EMAIL,
        "privacy_effective": PRIVACY_EFFECTIVE,
    }
    interstitial = bool(ads["download_interstitial"])
    dl_map = {f["id"]: download_urls(f["id"], interstitial) for f in forms}
    name_map = {
        f["id"]: {ext: download_name(f["title"], ext) for ext in ("pdf", "docx", "hwpx")}
        for f in forms
    }

    pages = 0

    # 1) 메인
    # 사이트 자체를 설명하는 구조화 데이터. 검색엔진이 '이 사이트가 무엇인지'를
    # 판단하는 근거이자, 사이트링크 검색창(Sitelinks Searchbox)의 전제 조건이다.
    site_jsonld = jd({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{SITE_URL}/#website",
                "url": f"{SITE_URL}/",
                "name": SITE_NAME,
                "alternateName": ["무료서식", "freeforms.kr"],
                "description": f"회원가입 없이 업무·법률·공공·생활 문서 양식 {len(forms)}종을 "
                               f"PDF·Word·한글(HWPX) 형식으로 무료 제공하는 서식 다운로드 사이트",
                "inLanguage": "ko",
                "publisher": {"@id": f"{SITE_URL}/#org"},
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {
                        "@type": "EntryPoint",
                        "urlTemplate": f"{SITE_URL}/search/?q={{search_term_string}}",
                    },
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@type": "Organization",
                "@id": f"{SITE_URL}/#org",
                "name": SITE_NAME,
                "legalName": BIZ_NAME,
                "url": f"{SITE_URL}/",
                "email": CONTACT_EMAIL,
                "logo": f"{SITE_URL}/og-default.png",
                "taxID": BIZ_NUMBER,
            },
        ],
    })

    write(PUBLIC / "index.html", env.get_template("index.html").render(
        page_title=f"{SITE_NAME} — 이력서·사직서·계약서 등 무료 문서 양식 {len(forms)}종",
        page_desc=f"회원가입 없이 업무·법률·공공·생활 서식 {len(forms)}종을 PDF·Word·한글(HWPX) "
                  f"형식으로 무료 다운로드. 양식을 미리 보고 바로 받으세요.",
        canonical="/",
        site_jsonld=site_jsonld,
        featured=featured,
        recent=recent,
        dl_map=dl_map,
        name_map=name_map,
        **common,
    ))
    pages += 1

    # 2) 카테고리
    for c in categories:
        for s in c["subcategories"]:
            key = f"{c['key']}/{s['key']}"
            write(PUBLIC / "category" / c["key"] / s["key"] / "index.html",
                  env.get_template("category.html").render(
                      page_title=f"{c['name']} {s['name']} 서식 {counts[key]}종 — {SITE_NAME}",
                      page_desc=f"{c['name']} {s['name']} 분야 무료 서식 {counts[key]}종. "
                                f"양식 미리보기 후 PDF·Word·한글로 다운로드하세요.",
                      canonical=f"/category/{c['key']}/{s['key']}/",
                      breadcrumb_jsonld=breadcrumb_ld([
                          ("홈", "/"),
                          (f"{c['name']} · {s['name']}", f"/category/{c['key']}/{s['key']}/"),
                      ]),
                      site_jsonld=jd({
                          "@context": "https://schema.org",
                          "@type": "ItemList",
                          "name": f"{c['name']} {s['name']} 서식 {counts[key]}종",
                          "numberOfItems": counts[key],
                          "itemListElement": [
                              {"@type": "ListItem", "position": i, "name": m["title"],
                               "url": f"{SITE_URL}/form/{m['id']}/"}
                              for i, m in enumerate(grouped[key], start=1)
                          ],
                      }),
                      cat=c, sub=s, forms=grouped[key], dl_map=dl_map, name_map=name_map, **common,
                  ))
            pages += 1

    # 3) 서식 상세
    for f in forms:
        key = f"{f['category']}/{f['subcategory']}"
        related = related_forms(f, forms, by_id, tokens, idf, RELATED_COUNT)
        kb = {k: max(1, v // 1024) for k, v in f["file_sizes"].items()}
        cat_o = cat_obj[f["category"]]
        sub_o = next(s for s in cat_o["subcategories"] if s["key"] == f["subcategory"])
        preview = (f.get("previews") or [None])[0]
        og_image = f"/files/{f['id']}/{preview}" if preview else "/og-default.png"
        # 실제 내려받는 파일 3종을 MediaObject로 적어 둔다. 파일 크기·형식이 명시되면
        # 검색엔진과 AI가 "PDF·Word·한글 세 형식 제공"을 사실로 인용할 수 있다.
        media = [
            {
                "@type": "MediaObject",
                "contentUrl": f"{SITE_URL}/files/{f['id']}/{f['id']}.{ext}",
                "encodingFormat": mime,
                "contentSize": f"{max(1, f['file_sizes'][ext] // 1024)}KB",
                "name": f"{f['title']} ({FMT_LABEL[ext]})",
            }
            for ext, mime in (
                ("pdf", "application/pdf"),
                ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                ("hwpx", "application/hwp+zip"),
            )
            if ext in f.get("file_sizes", {})
        ]
        jsonld = jd({
            "@context": "https://schema.org",
            "@type": "DigitalDocument",
            "@id": f"{SITE_URL}/form/{f['id']}/#doc",
            "name": f["title"],
            "headline": f"{f['title']} 양식 무료 다운로드",
            "description": f["summary"],
            "inLanguage": "ko",
            "isAccessibleForFree": True,
            "isFamilyFriendly": True,
            "genre": f"{cat_o['name']} · {sub_o['name']}",
            "keywords": ", ".join(f.get("tags", [])),
            "about": {"@type": "Thing", "name": f"{cat_o['name']} {sub_o['name']} 서식"},
            "encodingFormat": ["application/pdf",
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              "application/hwp+zip"],
            "associatedMedia": media,
            "thumbnailUrl": f"{SITE_URL}{og_image}",
            "url": f"{SITE_URL}/form/{f['id']}/",
            "mainEntityOfPage": f"{SITE_URL}/form/{f['id']}/",
            "datePublished": form_date(f, "created_at"),
            "dateModified": form_date(f, "updated_at"),
            "isPartOf": {"@type": "WebSite", "@id": f"{SITE_URL}/#website", "name": SITE_NAME},
            "publisher": {"@type": "Organization", "@id": f"{SITE_URL}/#org", "name": SITE_NAME},
        })
        # FAQ 구조화 데이터 — 검색결과에 질문이 함께 노출될 수 있다(노출 여부는 구글이 정한다).
        faq_jsonld = ""
        if f.get("faq"):
            faq_jsonld = jd({
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["q"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["a"]},
                    }
                    for item in f["faq"]
                ],
            })
        write(PUBLIC / "form" / f["id"] / "index.html",
              env.get_template("form.html").render(
                  page_title=f"{f['title']} 양식 무료 다운로드 (PDF·Word·한글) — {SITE_NAME}",
                  page_desc=f["summary"],
                  canonical=f"/form/{f['id']}/",
                  og_type="article",
                  og_image=og_image, og_w=800, og_h=1131,
                  breadcrumb_jsonld=breadcrumb_ld([
                      ("홈", "/"),
                      (f"{cat_o['name']} · {sub_o['name']}",
                       f"/category/{f['category']}/{f['subcategory']}/"),
                      (f["title"], f"/form/{f['id']}/"),
                  ]),
                  f=f,
                  cat=cat_obj[f["category"]],
                  sub=next(s for s in cat_obj[f["category"]]["subcategories"]
                           if s["key"] == f["subcategory"]),
                  related=related, kb=kb, jsonld=jsonld, faq_jsonld=faq_jsonld,
                  series_forms=series.get(f.get("series", ""), []),
                  my_collections=in_collections.get(f["id"], []),
                  dl=dl_map[f["id"]], dl_map=dl_map, names=name_map[f["id"]], name_map=name_map, **common,
              ))
        pages += 1

    # 3-1) 다운로드 중간 페이지 (광고 노출용). 광고를 켜지 않으면 만들지 않는다.
    if interstitial:
        delay_ms = max(0, int(float(ads["download_delay_sec"]) * 1000))
        for f in forms:
            key = f"{f['category']}/{f['subcategory']}"
            related = [r for r in grouped[key] if r["id"] != f["id"]][:4]
            for ext in ("pdf", "docx", "hwpx"):
                write(PUBLIC / "download" / f["id"] / ext / "index.html",
                      env.get_template("download.html").render(
                          page_title=f"{f['title']} {FMT_LABEL[ext]} 다운로드 — {SITE_NAME}",
                          page_desc=f["summary"],
                          canonical=f"/download/{f['id']}/{ext}/",
                          f=f,
                          cat=cat_obj[f["category"]],
                          sub=next(s for s in cat_obj[f["category"]]["subcategories"]
                                   if s["key"] == f["subcategory"]),
                          fmt_label=FMT_LABEL[ext],
                          file_url=f"/files/{f['id']}/{f['id']}.{ext}",
                          size_kb=max(1, f["file_sizes"][ext] // 1024),
                          delay_ms=delay_ms,
                          file_name=name_map[f["id"]][ext], related=related, dl_map=dl_map, name_map=name_map, **common,
                      ))
                pages += 1

    # 3-3) 계열 허브 — 같은 서식의 변형을 비교표로 모아 한 화면에서 고르게 한다.
    #      상세 화면을 여러 번 오가지 않아도 되고 '이력서 종류' 류의 검색어 착지 페이지가 된다.
    for hub in series_hubs:
        members = series[hub["key"]]
        hub_jsonld = jd({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"{hub['name']} 양식 {len(members)}종",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": m.get("variant") or m["title"],
                    "url": f"{SITE_URL}/form/{m['id']}/",
                }
                for i, m in enumerate(members, start=1)
            ],
        })
        others = [h for h in series_hubs if h["key"] != hub["key"]][:8]
        write(PUBLIC / "series" / hub["key"] / "index.html",
              env.get_template("series.html").render(
                  page_title=f"{hub['name']} 양식 {len(members)}종 비교 — 무료 다운로드",
                  page_desc=f"{hub['name']} 양식 {len(members)}종을 상황별로 비교하고 "
                            f"PDF·Word·한글로 무료 다운로드. 어떤 버전을 써야 하는지 표로 정리했습니다.",
                  canonical=f"/series/{hub['key']}/",
                  breadcrumb_jsonld=breadcrumb_ld([
                      ("홈", "/"),
                      (f"{hub['name']} {len(members)}종", f"/series/{hub['key']}/"),
                  ]),
                  s_key=hub["key"], s_name=hub["name"], forms=members,
                  other_hubs=others, jsonld=hub_jsonld,
                  dl_map=dl_map, name_map=name_map, **common,
              ))
        pages += 1

    # 3-3-1) 주제 모음 허브 — '퇴사할 때', '이사할 때'처럼 일 단위로 서식을 묶는다.
    #        계열 허브가 세로(같은 서식의 변형)라면 이쪽은 가로(일의 흐름)다.
    for c in collections:
        c_jsonld = jd({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"{c['name']} {c['count']}종",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "name": m["title"],
                    "url": f"{SITE_URL}/form/{m['id']}/",
                }
                for i, m in enumerate(c["forms"], start=1)
            ],
        })
        others = [h for h in collection_hubs if h["key"] != c["key"]][:8]
        write(PUBLIC / "collection" / c["key"] / "index.html",
              env.get_template("collection.html").render(
                  page_title=f"{c['name']} {c['count']}종 — 무료 다운로드",
                  page_desc=f"{c['lead'][:90]} PDF·Word·한글 무료 다운로드.",
                  canonical=f"/collection/{c['key']}/",
                  breadcrumb_jsonld=breadcrumb_ld([
                      ("홈", "/"),
                      (f"{c['name']} {c['count']}종", f"/collection/{c['key']}/"),
                  ]),
                  c=c, forms=c["forms"], others=others, jsonld=c_jsonld,
                  dl_map=dl_map, name_map=name_map, **common,
              ))
        pages += 1

    # 3-4) 검색 결과 페이지 — 검색어는 ?q=로 받아 브라우저에서 추린다(정적 호스팅이라 서버 검색이 없다).
    #      결과 목록은 매번 달라지므로 색인에서 제외하고, 대신 내부 이동 통로로만 쓴다.
    write(PUBLIC / "search" / "index.html", env.get_template("search.html").render(
        page_title=f"서식 검색 — {SITE_NAME}",
        page_desc=f"무료 서식 {len(forms)}종에서 원하는 양식을 찾아보세요.",
        canonical="/search/",
        page_robots="noindex, follow",
        featured=featured, dl_map=dl_map, name_map=name_map, **common,
    ))
    pages += 1

    # 3-5) 서식 요청 페이지 — 방문자가 필요한 서식을 남기면 일일 에이전트가 우선 제작한다.
    #      접수 주소(requests.json)가 없으면 폼 없이 안내만 나가므로 항상 만들어 둔다.
    from_request = sorted(
        (f for f in forms if f.get("from_request")),
        key=lambda f: f.get("created_at", ""), reverse=True,
    )[:8]
    write(PUBLIC / "request" / "index.html", env.get_template("request.html").render(
        page_title=f"서식 요청 — {SITE_NAME}",
        page_desc="찾으시는 서식이 없으면 알려주세요. 매일 아침 검토해 무료로 만들어 올립니다.",
        canonical="/request/",
        from_request=from_request,
        dl_map=dl_map, name_map=name_map, **common,
    ))
    pages += 1

    # 3-6) 사이트 소개 — '이 사이트가 무엇인가'를 한 문장으로 정의해 두는 페이지.
    #      AI 검색(챗GPT·퍼플렉시티 등)이 사이트를 인용할 때 근거로 삼는 착지점이고,
    #      검색엔진에는 신뢰도(E-E-A-T) 신호가 된다.
    write(PUBLIC / "about" / "index.html", env.get_template("about.html").render(
        page_title=f"사이트 소개 — {SITE_NAME}",
        page_desc=f"{SITE_NAME}는 회원가입 없이 문서 양식 {len(forms)}종을 PDF·Word·한글(HWPX) "
                  f"세 형식으로 무료 제공하는 한국어 서식 사이트입니다.",
        canonical="/about/",
        breadcrumb_jsonld=breadcrumb_ld([("홈", "/"), ("사이트 소개", "/about/")]),
        site_jsonld=jd({
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "name": f"사이트 소개 — {SITE_NAME}",
            "url": f"{SITE_URL}/about/",
            "inLanguage": "ko",
            "mainEntity": {"@type": "Organization", "@id": f"{SITE_URL}/#org", "name": SITE_NAME},
        }),
        **common,
    ))
    pages += 1

    # 3-2) 정책 페이지 — 애드센스 심사는 쿠키 사용 고지를 요구한다
    write(PUBLIC / "privacy" / "index.html", env.get_template("privacy.html").render(
        page_title=f"개인정보처리방침 — {SITE_NAME}",
        page_desc=f"{SITE_NAME}의 개인정보처리방침입니다. 회원가입 없이 이용할 수 있으며, "
                  f"방문 통계 분석과 광고를 위해 쿠키를 사용합니다.",
        canonical="/privacy/",
        **common,
    ))
    pages += 1

    # 4) 검색 인덱스 (브라우저에서 내려받아 클라이언트 검색에 사용)
    index = {
        "generated_at": now.replace(microsecond=0).isoformat(),
        "forms": [
            {
                "id": f["id"],
                "title": f["title"],
                "cat": cat_label[f["id"]],
                "tags": " ".join(f.get("tags", [])),
                "summary": f["summary"],
                "pages": f.get("pages", 1),
            }
            for f in sorted(forms, key=lambda x: x["title"])
        ],
    }
    write(PUBLIC / "search-index.json", json.dumps(index, ensure_ascii=False))

    # 5) sitemap.xml / robots.txt
    # /search/는 결과가 검색어마다 달라 색인 대상이 아니므로 사이트맵에 넣지 않는다.
    today = now.strftime("%Y-%m-%d")

    def newest(items: list[dict[str, Any]]) -> str:
        """묶음 안에서 가장 최근에 고친 서식의 날짜. 목록 페이지의 lastmod로 쓴다."""
        days = [d for d in (form_date(m) for m in items) if d]
        return max(days) if days else today

    # lastmod는 '그 페이지가 실제로 바뀐 날'이어야 한다. 전 URL에 오늘 날짜를 찍으면
    # 크롤러가 값을 신뢰하지 않게 되어(매일 274페이지가 전부 바뀐 것으로 보인다)
    # 새 서식이 늘어도 우선 수집되지 않는다.
    site_newest = newest(forms)
    urls: list[tuple[str, str, str]] = [("/", site_newest, "1.0")]
    for c in categories:
        for s in c["subcategories"]:
            k = f"{c['key']}/{s['key']}"
            urls.append((f"/category/{k}/", newest(grouped[k]), "0.6"))
    for h in collection_hubs:
        members = next(x["forms"] for x in collections if x["key"] == h["key"])
        urls.append((f"/collection/{h['key']}/", newest(members), "0.7"))
    for h in series_hubs:
        urls.append((f"/series/{h['key']}/", newest(series[h["key"]]), "0.7"))
    for f in forms:
        urls.append((f"/form/{f['id']}/", form_date(f) or today, "0.8"))
    urls += [("/about/", site_newest, "0.6"),
             ("/privacy/", today, "0.3"),
             ("/request/", today, "0.5")]

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, mod, priority in urls:
        sitemap.append(f"  <url><loc>{SITE_URL}{u}</loc><lastmod>{mod}</lastmod>"
                       f"<priority>{priority}</priority></url>")
    sitemap.append("</urlset>")
    write(PUBLIC / "sitemap.xml", "\n".join(sitemap) + "\n")

    # robots.txt — 기본은 전체 허용이고, AI 검색·국내 검색 크롤러는 이름을 적어 둔다.
    # /search/ 는 Disallow 하지 않는다. 크롤링을 막으면 그 안의 noindex 태그도 못 읽는다.
    lines = ["# 무료서식 다운로드 — 전체 공개. 모든 서식은 무료이며 로그인이 필요 없습니다.",
             "User-agent: *", "Allow: /", ""]
    for bot, why in KR_CRAWLERS + AI_CRAWLERS:
        lines += [f"# {why}", f"User-agent: {bot}", "Allow: /", ""]
    lines += [f"Sitemap: {SITE_URL}/sitemap.xml", f"Sitemap: {SITE_URL}/rss.xml", ""]
    write(PUBLIC / "robots.txt", "\n".join(lines))

    # 5-2) rss.xml — 네이버 서치어드바이저는 사이트맵과 **별도로** RSS를 받는다.
    #      새 서식이 올라온 것을 국내 검색에 빨리 알리는 통로다.
    feed = sorted(forms, key=lambda x: x.get("created_at", ""), reverse=True)[:RSS_COUNT]
    rss = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">', "<channel>",
           f"<title>{xml_text(SITE_NAME)} — 최근 추가 서식</title>",
           f"<link>{SITE_URL}/</link>",
           f"<description>{xml_text(f'회원가입 없이 내려받는 무료 문서 양식 {len(forms)}종. 새로 추가된 서식을 알려드립니다.')}</description>",
           "<language>ko</language>",
           f'<atom:link href="{SITE_URL}/rss.xml" rel="self" type="application/rss+xml" />',
           f"<lastBuildDate>{rfc822(site_newest)}</lastBuildDate>"]
    for f in feed:
        url = f"{SITE_URL}/form/{f['id']}/"
        rss += ["<item>",
                f"<title>{xml_text(f['title'])}</title>",
                f"<link>{url}</link>",
                f'<guid isPermaLink="true">{url}</guid>',
                f"<category>{xml_text(cat_label[f['id']])}</category>",
                f"<pubDate>{rfc822(form_date(f, 'created_at'))}</pubDate>",
                f"<description>{xml_text(f['summary'])}</description>",
                "</item>"]
    rss += ["</channel>", "</rss>", ""]
    write(PUBLIC / "rss.xml", "\n".join(rss))

    # 5-3) llms.txt / llms-full.txt — 생성형 AI(챗GPT·퍼플렉시티·클로드 등)가
    #      274페이지 HTML을 헤매지 않고 사이트 구조와 서식 목록을 바로 읽도록 둔 요약본이다.
    #      llms.txt 는 지도, llms-full.txt 는 전 서식 목록이다.
    top = sorted(forms, key=lambda x: (x.get("featured_rank", 99), x["title"]))[:20]
    lt = [f"# {SITE_NAME} (freeforms.kr)", "",
          f"> 회원가입·로그인 없이 업무·법률·공공·부동산·교육·의료복지·생활 분야의 한국어 문서 양식 "
          f"{len(forms)}종을 PDF·Word(DOCX)·한글(HWPX) 세 가지 형식으로 무료 제공하는 서식 "
          f"다운로드 사이트입니다. ({today} 기준, 매일 새 서식 추가)", "",
          "## 이 사이트의 특징", "",
          "- 서식 1종마다 PDF·Word·한글(HWPX) 세 형식을 모두 제공합니다.",
          "- 모든 서식에 예시가 기입된 미리보기 이미지, 작성 순서, 포함 항목, 자주 묻는 질문이 있습니다.",
          "- 내려받는 파일은 예시가 없는 빈 양식입니다.",
          "- 수집한 오래된 파일이 아니라 현재 실무 기준으로 새로 제작한 양식입니다.",
          "- 무료이며 회원가입·결제가 없고 이름·연락처를 입력받지 않습니다.",
          "- 법정 신고서식(정해진 원본을 써야 효력이 있는 문서)은 제공하지 않습니다.", "",
          "## 주요 문서", "",
          f"- [사이트 소개]({SITE_URL}/about/): 사이트 정의·이용 조건·제작 방식",
          f"- [서식 요청]({SITE_URL}/request/): 필요한 서식을 요청하면 무료로 제작",
          f"- [개인정보처리방침]({SITE_URL}/privacy/)", "",
          "## 분야별 서식", ""]
    for c in categories:
        for s in c["subcategories"]:
            k = f"{c['key']}/{s['key']}"
            lt.append(f"- [{c['name']} · {s['name']}]({SITE_URL}/category/{k}/): {counts[k]}종")
    lt += ["", "## 버전별 비교 (같은 서식의 상황별 변형)", ""]
    for h in series_hubs:
        lt.append(f"- [{h['name']} {h['count']}종]({SITE_URL}/series/{h['key']}/)")
    if collection_hubs:
        lt += ["", "## 주제 모음 (한 가지 일에 연달아 쓰는 서식)", ""]
        for h in collection_hubs:
            lt.append(f"- [{h['name']} {h['count']}종]({SITE_URL}/collection/{h['key']}/)")
    lt += ["", "## 많이 찾는 서식", ""]
    for f in top:
        lt.append(f"- [{f['title']}]({SITE_URL}/form/{f['id']}/): {f['summary']}")
    lt += ["", "## Optional", "",
           f"- [전체 서식 목록 {len(forms)}종]({SITE_URL}/llms-full.txt)",
           f"- [사이트맵]({SITE_URL}/sitemap.xml)",
           f"- [RSS]({SITE_URL}/rss.xml)", ""]
    write(PUBLIC / "llms.txt", "\n".join(lt))

    lf = [f"# {SITE_NAME} — 전체 서식 목록 {len(forms)}종", "",
          f"{today} 기준. 모든 서식은 무료이며 PDF·Word(DOCX)·한글(HWPX) 세 형식으로 제공됩니다.",
          f"출처: {SITE_URL}/", ""]
    for c in categories:
        for s in c["subcategories"]:
            k = f"{c['key']}/{s['key']}"
            if not grouped[k]:
                continue
            lf += [f"## {c['name']} · {s['name']} ({counts[k]}종)", ""]
            for f in sorted(grouped[k], key=lambda x: x["title"]):
                lf.append(f"### {f['title']}")
                lf.append(f"- URL: {SITE_URL}/form/{f['id']}/")
                lf.append(f"- 설명: {f['summary']}")
                if f.get("tags"):
                    lf.append(f"- 검색어: {', '.join(f['tags'])}")
                lf.append(f"- 분량: {f.get('pages', 1)}페이지(A4) · 형식: PDF·Word·한글 · 수정일: {form_date(f)}")
                if f.get("howto"):
                    lf.append(f"- 작성 순서: {' / '.join(f['howto'])}")
                for item in (f.get("faq") or []):
                    lf.append(f"- Q. {item['q']} A. {item['a']}")
                lf.append("")
    write(PUBLIC / "llms-full.txt", "\n".join(lf))

    # 5-4) 공유 카드 기본 이미지
    if not make_og_default(PUBLIC / "og-default.png"):
        print("[사이트] 알림: assets/og-default.png 가 없어 공유 카드 기본 이미지를 넣지 않았습니다.")

    # 5-1) ads.txt — 애드센스 게시자 확인용. 클라이언트 ID가 있을 때만 생성한다.
    if ads["client"]:
        pub = ads["client"].replace("ca-", "", 1)
        write(PUBLIC / "ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")

    # 6) 파비콘 (외부 파일 없이 SVG로 생성)
    write(PUBLIC / "favicon.svg",
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
          '<rect width="64" height="64" rx="12" fill="#24384f"/>'
          '<path d="M20 16h18l10 10v22a2 2 0 0 1-2 2H20a2 2 0 0 1-2-2V18a2 2 0 0 1 2-2z" fill="#fff"/>'
          '<path d="M38 16v10h10" fill="#c9d6e8"/>'
          '<path d="M26 34h14M26 40h14M26 28h8" stroke="#24384f" stroke-width="2.6" '
          'stroke-linecap="round"/></svg>\n')

    # 7) 404
    write(PUBLIC / "404.html", env.get_template("category.html").render(
        page_title=f"페이지를 찾을 수 없습니다 — {SITE_NAME}",
        page_desc="요청한 페이지가 없습니다. 상단 카테고리나 검색으로 서식을 찾아보세요.",
        canonical="/404.html",
        cat={"key": categories[0]["key"], "name": "전체"},
        sub={"key": categories[0]["subcategories"][0]["key"], "name": "페이지를 찾을 수 없습니다"},
        forms=[], dl_map=dl_map, name_map=name_map, **common,
    ))
    pages += 1

    ad_state = ("광고 ON" if ads["enabled"] else "광고 OFF") + \
               (" · 다운로드 중간페이지 ON" if interstitial else "")
    print(f"[사이트] 페이지 {pages}개 · 서식 {len(forms)}종 · 검색 인덱스·사이트맵 생성 완료 ({ad_state})")
    print(f"[사이트] 배포 대상 폴더: {PUBLIC}")
    return pages


def main() -> int:
    """엔트리포인트."""
    try:
        build()
    except SiteBuildError as exc:
        print(f"[오류] {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
