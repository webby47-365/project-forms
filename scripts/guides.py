"""정보형 가이드(/guide/) — 명세 로드·검사·본문 변환. build_site.py 와 validate_catalog.py 가 함께 쓴다.

가이드 1편 = guides/<slug>.yaml 1개. 작성 규칙 정본은 scripts/agent/GUIDE_SPEC.md.

왜 가이드인가: 서식 상세는 "사직서 양식"(다운로드 의도)만 받는다. 그 앞 단계의 정보형 검색
("사직서 제출 후 퇴사 절차", "연차수당 계산법")을 받을 페이지가 없었다. 가이드 1편이 서식 2~4종과
도구로 연결되어 상세 페이지 유입을 같이 끌어올린다.

본문은 새로 쓴다. 서식의 howto·faq 문장을 그대로 옮기면 서식 상세와 중복 콘텐츠가 되므로,
연결 서식의 작성 순서는 템플릿이 '함께 쓰는 서식' 상자 안에 요약으로만 붙인다.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GUIDES_DIR = ROOT / "guides"

# 가이드 묶음. 허브(/guide/)에서 이 순서로 보인다. 새 묶음은 여기에만 추가한다.
GUIDE_GROUPS: list[dict[str, str]] = [
    {"key": "quit", "name": "퇴사·이직"},
    {"key": "pay", "name": "급여·근로"},
    {"key": "contract", "name": "계약·돈거래"},
    {"key": "housing", "name": "부동산·이사"},
    {"key": "life", "name": "생활·민원"},
]
GROUP_KEYS = {g["key"] for g in GUIDE_GROUPS}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 길이 규칙 (GUIDE_SPEC.md 와 같게 유지)
TITLE_MAX = 40
DESC_MIN, DESC_MAX = 70, 160
SUMMARY_MIN, SUMMARY_MAX = 80, 260
SECTIONS_MIN, SECTIONS_MAX = 4, 9
BODY_MIN_TOTAL = 1200          # 섹션 본문(문단+목록+표) 합계 최소 글자 수(공백 제외, A4 약 1.5장) — 얇은 페이지 방지
FORMS_MIN, FORMS_MAX = 2, 4
FAQ_MIN, FAQ_MAX = 2, 5


class GuideError(Exception):
    """가이드 명세 오류."""


def _yaml() -> Any:
    """PyYAML 을 늦게 불러온다. 없으면 None (사이트 빌드는 가이드만 건너뛴다)."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return None
    return yaml


def inline(text: str) -> str:
    """본문 한 문단을 안전한 HTML 로 바꾼다.

    먼저 전부 이스케이프한 뒤 허용한 두 가지만 되살린다:
    **굵게** → <b>, [글자](/사이트내부경로/) → <a>. 외부 링크는 본문에 넣지 않는다(출처 목록에만).
    """
    s = html.escape(text.strip(), quote=True)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((/[A-Za-z0-9_\-/?=&;.#%]*)\)", r'<a href="\2">\1</a>', s)
    return s


def plain(text: str) -> str:
    """구조화 데이터·메타용 평문. 굵게·링크 표시를 벗긴다."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    s = re.sub(r"\[([^\]]+)\]\((/[^)]*)\)", r"\1", s)
    return " ".join(s.split())


def paragraphs(body: str) -> list[str]:
    """빈 줄로 나눈 문단 목록."""
    return [p for p in (x.strip() for x in re.split(r"\n\s*\n", body or "")) if p]


def section_text_len(sec: dict[str, Any]) -> int:
    """섹션 본문 글자 수(공백 제외)."""
    parts: list[str] = [sec.get("body") or ""]
    parts += [str(x) for x in (sec.get("list") or [])]
    tbl = sec.get("table") or {}
    for row in tbl.get("rows") or []:
        parts += [str(c) for c in row]
    return len(re.sub(r"\s", "", plain(" ".join(parts))))


def check_guide(g: dict[str, Any], slug: str, form_ids: set[str], tool_paths: set[str]) -> list[str]:
    """명세 하나를 검사해 오류 문장 목록을 돌려준다(비어 있으면 통과)."""
    errs: list[str] = []

    def need(key: str, typ: type) -> Any:
        v = g.get(key)
        if not isinstance(v, typ) or (isinstance(v, (str, list)) and not v):
            errs.append(f"'{key}' 가 비었거나 형식이 틀립니다")
            return None
        return v

    if g.get("slug") != slug:
        errs.append(f"slug({g.get('slug')}) 가 파일명({slug})과 다릅니다")
    if not SLUG_RE.match(slug):
        errs.append("slug 는 영문 소문자·숫자·하이픈만 씁니다")
    title = need("title", str)
    if title and len(title) > TITLE_MAX:
        errs.append(f"title {len(title)}자 — {TITLE_MAX}자 이내")
    desc = need("description", str)
    if desc and not DESC_MIN <= len(desc) <= DESC_MAX:
        errs.append(f"description {len(desc)}자 — {DESC_MIN}~{DESC_MAX}자")
    summary = need("summary", str)
    if summary and not SUMMARY_MIN <= len(plain(summary)) <= SUMMARY_MAX:
        errs.append(f"summary {len(plain(summary))}자 — {SUMMARY_MIN}~{SUMMARY_MAX}자")
    if g.get("group") not in GROUP_KEYS:
        errs.append(f"group 은 {sorted(GROUP_KEYS)} 중 하나")
    for key in ("created_at", "updated_at"):
        if not DATE_RE.match(str(g.get(key, ""))):
            errs.append(f"{key} 는 YYYY-MM-DD")
    if not isinstance(g.get("keywords"), list) or not 3 <= len(g["keywords"]) <= 10:
        errs.append("keywords 3~10개")

    secs = need("sections", list) or []
    if secs and not SECTIONS_MIN <= len(secs) <= SECTIONS_MAX:
        errs.append(f"sections {len(secs)}개 — {SECTIONS_MIN}~{SECTIONS_MAX}개")
    total = 0
    for i, sec in enumerate(secs, 1):
        if not isinstance(sec, dict) or not sec.get("h"):
            errs.append(f"sections[{i}] 에 h(소제목)가 없습니다")
            continue
        if not (sec.get("body") or sec.get("list") or sec.get("table")):
            errs.append(f"sections[{i}] '{sec['h']}' 본문이 없습니다")
        tbl = sec.get("table")
        if tbl is not None:
            head = tbl.get("head") if isinstance(tbl, dict) else None
            rows = tbl.get("rows") if isinstance(tbl, dict) else None
            if not head or not rows or any(len(r) != len(head) for r in rows):
                errs.append(f"sections[{i}] 표의 head·rows 칸 수가 맞지 않습니다")
        for m in re.finditer(r"\]\((/[^)]*)\)", str(sec.get("body", ""))):
            path = m.group(1).split("?")[0].split("#")[0]
            if path.startswith("/form/"):
                fid = path.strip("/").split("/")[-1]
                if fid not in form_ids:
                    errs.append(f"sections[{i}] 링크의 서식 id '{fid}' 가 카탈로그에 없습니다")
        total += section_text_len(sec)
    if secs and total < BODY_MIN_TOTAL:
        errs.append(f"본문 {total}자 — 최소 {BODY_MIN_TOTAL}자(공백 제외). 얇은 페이지는 색인·광고 심사에 불리합니다")

    forms = g.get("forms") or []
    if not FORMS_MIN <= len(forms) <= FORMS_MAX:
        errs.append(f"forms {len(forms)}개 — {FORMS_MIN}~{FORMS_MAX}개")
    for fid in forms:
        if fid not in form_ids:
            errs.append(f"forms 의 '{fid}' 가 카탈로그에 없습니다")
    for t in g.get("tools") or []:
        if t not in tool_paths:
            errs.append(f"tools 의 '{t}' 는 없는 도구 경로입니다")

    faq = g.get("faq") or []
    if not FAQ_MIN <= len(faq) <= FAQ_MAX:
        errs.append(f"faq {len(faq)}개 — {FAQ_MIN}~{FAQ_MAX}개")
    for i, item in enumerate(faq, 1):
        if not isinstance(item, dict) or not item.get("q") or not item.get("a"):
            errs.append(f"faq[{i}] 에 q·a 가 없습니다")

    sources = g.get("sources") or []
    if not sources:
        errs.append("sources(1차 출처) 최소 1개 — 법령·기관 자료 URL")
    for i, s in enumerate(sources, 1):
        if not isinstance(s, dict) or not s.get("name") or not str(s.get("url", "")).startswith("https://"):
            errs.append(f"sources[{i}] 에 name 과 https URL 이 필요합니다")
    return errs


def load_guides(form_ids: set[str], tool_paths: set[str], strict: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    """guides/*.yaml 을 읽어 (통과한 가이드 목록, 오류 문장 목록)을 돌려준다.

    strict=False(사이트 빌드): 오류가 난 가이드만 빼고 계속 — 무인 배포를 멈추지 않는다.
    strict=True(validate_catalog): 호출자가 오류를 배포 중단으로 처리한다.
    """
    if not GUIDES_DIR.exists():
        return [], []
    yaml = _yaml()
    if yaml is None:
        msg = "PyYAML 이 없어 가이드를 읽지 못했습니다 (pip install pyyaml)"
        return [], [msg]
    out: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(GUIDES_DIR.glob("*.yaml")):
        slug = path.stem
        try:
            g = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            errors.append(f"[가이드] {slug}: YAML 파싱 실패 — {exc}")
            continue
        if not isinstance(g, dict):
            errors.append(f"[가이드] {slug}: 최상위가 매핑이 아닙니다")
            continue
        if g.get("status", "published") != "published":
            continue
        errs = check_guide(g, slug, form_ids, tool_paths)
        if errs:
            errors += [f"[가이드] {slug}: {e}" for e in errs]
            continue
        g["path"] = f"/guide/{slug}/"
        g["group_name"] = next(x["name"] for x in GUIDE_GROUPS if x["key"] == g["group"])
        g["created_at"] = str(g["created_at"])
        g["updated_at"] = str(g["updated_at"])
        # 템플릿용 변환 (본문 HTML은 여기서만 만든다 — 템플릿에서는 |safe 로 출력)
        for sec in g["sections"]:
            sec["id"] = f"s{g['sections'].index(sec) + 1}"
            sec["html_paras"] = [inline(p) for p in paragraphs(sec.get("body", ""))]
            sec["html_list"] = [inline(str(x)) for x in (sec.get("list") or [])]
            sec["html_table"] = None
            if sec.get("table"):
                sec["html_table"] = {"head": [inline(str(h)) for h in sec["table"]["head"]],
                                     "rows": [[inline(str(c)) for c in r] for r in sec["table"]["rows"]]}
        g["html_summary"] = inline(g["summary"])
        g["faq_plain"] = [{"q": plain(x["q"]), "a": plain(x["a"])} for x in g["faq"]]
        g["reading_min"] = max(3, round(sum(section_text_len(s) for s in g["sections"]) / 500))
        out.append(g)
    out.sort(key=lambda x: (x["created_at"], x["slug"]), reverse=True)
    return out, errors
