"""정적 사이트 생성기: catalog.json + categories.json → HTML.

생성물은 public/ 아래에 놓이며, 이 폴더가 Cloudflare Pages 배포 대상이다.
서식 파일(public/files/…)은 build_form.py가 이미 만들어 두었으므로 건드리지 않는다.

사용법:
    python scripts/build_site.py
"""

from __future__ import annotations

import json
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
RELATED_COUNT = 5
TICKER_COUNT = 5  # 상단 롤링바에 띄울 최근 추가 서식 수

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
    write(PUBLIC / "index.html", env.get_template("index.html").render(
        page_title=f"{SITE_NAME} — 이력서·사직서·계약서 등 무료 문서 양식",
        page_desc=f"회원가입 없이 업무·법률·공공·생활 서식 {len(forms)}종을 PDF·Word·한글(HWPX) "
                  f"형식으로 무료 다운로드. 양식을 미리 보고 바로 받으세요.",
        canonical="/",
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
                      cat=c, sub=s, forms=grouped[key], dl_map=dl_map, name_map=name_map, **common,
                  ))
            pages += 1

    # 3) 서식 상세
    for f in forms:
        key = f"{f['category']}/{f['subcategory']}"
        related = [r for r in grouped[key] if r["id"] != f["id"]][:RELATED_COUNT]
        kb = {k: max(1, v // 1024) for k, v in f["file_sizes"].items()}
        jsonld = json.dumps({
            "@context": "https://schema.org",
            "@type": "DigitalDocument",
            "name": f["title"],
            "description": f["summary"],
            "inLanguage": "ko",
            "isAccessibleForFree": True,
            "encodingFormat": ["application/pdf",
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              "application/hwp+zip"],
            "url": f"{SITE_URL}/form/{f['id']}/",
            "datePublished": f.get("created_at", "")[:10],
            "dateModified": f.get("updated_at", "")[:10],
            "publisher": {"@type": "Organization", "name": SITE_NAME},
        }, ensure_ascii=False, indent=None)
        # FAQ 구조화 데이터 — 검색결과에 질문이 함께 노출될 수 있다(노출 여부는 구글이 정한다).
        faq_jsonld = ""
        if f.get("faq"):
            faq_jsonld = json.dumps({
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
            }, ensure_ascii=False, indent=None)
        write(PUBLIC / "form" / f["id"] / "index.html",
              env.get_template("form.html").render(
                  page_title=f"{f['title']} 양식 무료 다운로드 (PDF·Word·한글) — {SITE_NAME}",
                  page_desc=f["summary"],
                  canonical=f"/form/{f['id']}/",
                  f=f,
                  cat=cat_obj[f["category"]],
                  sub=next(s for s in cat_obj[f["category"]]["subcategories"]
                           if s["key"] == f["subcategory"]),
                  related=related, kb=kb, jsonld=jsonld, faq_jsonld=faq_jsonld,
                  series_forms=series.get(f.get("series", ""), []),
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
        hub_jsonld = json.dumps({
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
        }, ensure_ascii=False, indent=None)
        others = [h for h in series_hubs if h["key"] != hub["key"]][:8]
        write(PUBLIC / "series" / hub["key"] / "index.html",
              env.get_template("series.html").render(
                  page_title=f"{hub['name']} 양식 {len(members)}종 비교 — 무료 다운로드",
                  page_desc=f"{hub['name']} 양식 {len(members)}종을 상황별로 비교하고 "
                            f"PDF·Word·한글로 무료 다운로드. 어떤 버전을 써야 하는지 표로 정리했습니다.",
                  canonical=f"/series/{hub['key']}/",
                  s_key=hub["key"], s_name=hub["name"], forms=members,
                  other_hubs=others, jsonld=hub_jsonld,
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
    urls = (["/"]
            + [f"/category/{c['key']}/{s['key']}/" for c in categories for s in c["subcategories"]]
            + [f"/series/{h['key']}/" for h in series_hubs]
            + [f"/form/{f['id']}/" for f in forms]
            + ["/privacy/", "/request/"])
    today = now.strftime("%Y-%m-%d")
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        priority = ("1.0" if u == "/"
                    else "0.8" if u.startswith("/form/")
                    else "0.7" if u.startswith("/series/")
                    else "0.6")
        sitemap.append(f"  <url><loc>{SITE_URL}{u}</loc><lastmod>{today}</lastmod>"
                       f"<priority>{priority}</priority></url>")
    sitemap.append("</urlset>")
    write(PUBLIC / "sitemap.xml", "\n".join(sitemap) + "\n")
    write(PUBLIC / "robots.txt",
          f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")

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
