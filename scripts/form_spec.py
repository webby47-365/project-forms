"""서식 명세(YAML) 로더 및 공통 타입 정의.

블록(block) 기반 명세 하나로 DOCX / HWPX 두 형식을 동일 레이아웃으로 생성한다.
DOCX→HWPX 변환이 아니라 '명세 기반 병행 생성'이므로 레이아웃 붕괴가 발생하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

# 지원 블록 타입
BlockType = Literal[
    "doc_title",  # 문서 제목 (예: 이 력 서)
    "subtitle",  # 부제 / 소제목
    "para",      # 일반 문단
    "grid",      # 라벨-값 격자표 (좌측 라벨 음영)
    "table",     # 머리글 + 빈 입력행 표
    "textbox",   # 자유기술란 (안내문 + 테두리 박스)
    "kv_list",   # 번호 없는 항목 나열 (계약서 조항 등)
    "article",   # 계약서 조 단위 (제목 + 본문 여러 줄)
    "date_line", # 20    년    월    일
    "sign_line", # 서명란
    "notice",    # 하단 안내/주의 문구 (작은 글씨)
    "spacer",    # 빈 줄
    "page_break",
]

A4_WIDTH_MM = 210.0
A4_HEIGHT_MM = 297.0
MARGIN_MM = 18.0
USABLE_WIDTH_MM = A4_WIDTH_MM - MARGIN_MM * 2  # 174mm

FONT_SANS = "Malgun Gothic"   # 한글 Windows 기본 (LibreOffice에서는 Noto Sans CJK KR로 대체)
FONT_MONO = "Consolas"


@dataclass
class FormSpec:
    """서식 1종의 명세."""

    id: str
    title: str
    category: str
    subcategory: str
    tags: list[str]
    summary: str
    usage: str
    blocks: list[dict[str, Any]]
    source: str = "original"
    source_note: str = ""
    featured: bool = False
    featured_rank: int = 99  # 메인 노출 순서 (작을수록 먼저)
    # 같은 서식의 실무 변형끼리 묶는 계열 키. 예: resume → 신입/경력/서술형 이력서
    series: str = ""
    series_name: str = ""   # 계열 표시명 (예: "이력서")
    variant: str = ""       # 이 서식의 변형 이름 (예: "신입용", "경력용")
    variant_rank: int = 99  # 계열 안에서의 나열 순서
    variant_use: str = ""   # 계열 비교표의 "이럴 때 쓰세요" 한 줄 (40자 이내)
    # 상세 화면 본문. 화면에서 읽는 글이므로 짧게 끊어 쓴다(SPEC_GUIDE 3-2절).
    howto: list[str] = field(default_factory=list)          # 작성 단계 3~5개, 각 한 문장
    faq: list[dict[str, str]] = field(default_factory=list)  # [{q, a}] 2~4문항, 아코디언으로 표시
    version: int = 1
    created_by: str = "manual"
    status: str = "published"
    target_pages: int = 0  # 0이면 page_break 개수로 자동 산출

    @property
    def pages_hint(self) -> int:
        """목표 페이지 수. 명세에 target_pages가 없으면 page_break 개수 + 1."""
        if self.target_pages > 0:
            return self.target_pages
        return 1 + sum(1 for b in self.blocks if b.get("type") == "page_break")

    @property
    def outline(self) -> list[dict[str, Any]]:
        """상세 화면 '이 서식에 들어 있는 항목' 목차. blocks에서 자동으로 뽑는다."""
        return outline_of(self.blocks)

    @property
    def has_sample(self) -> bool:
        """미리보기용 '작성 예시' 데이터가 하나라도 들어 있는지 여부.

        True면 build_form.py가 빈 양식과 별도로 예시 기입본을 한 번 더 렌더링해
        그 결과로 미리보기 이미지를 만든다(다운로드 파일은 빈 양식 그대로다).
        """
        return any(
            blk.get(k) for blk in self.blocks
            for k in ("sample_rows", "sample_text", "sample_names", "photo_cell")
        )


class SpecError(ValueError):
    """명세 파일이 스키마를 위반한 경우."""


# 목차(outline) 추출 설정. 화면에서 훑어보는 목록이므로 과하게 길면 안 된다.
_OUTLINE_MAX_SECTIONS = 12
_OUTLINE_MAX_ITEMS_PER_SECTION = 14
_OUTLINE_MAX_ITEMS_TOTAL = 48
_OUTLINE_ITEM_MAX_CHARS = 24
# 표의 일련번호 칸처럼 항목으로서 의미가 없는 머리글은 뺀다.
_OUTLINE_SKIP = {"no", "번호", "연번", "순번", "구분", "비고", "계", "합계", "-", "※"}


def outline_of(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """명세의 blocks에서 '이 서식에 들어 있는 항목' 목차를 뽑는다.

    상세 화면에 넣을 목록이다. 서식을 열지 않고도 어떤 칸을 채워야 하는지 미리 보게 해
    체류시간을 늘리고, 항목명이 그대로 본문 텍스트가 되어 검색 유입(롱테일)에도 쓰인다.

    구역 제목(subtitle)을 만나면 새 묶음을 시작하고, 그 아래의 grid 라벨·table 머리글·
    계약서 조 제목을 항목으로 모은다. 값 칸("")과 일련번호 머리글은 제외한다.

    Args:
        blocks: FormSpec.blocks (명세의 블록 목록).

    Returns:
        [{"title": 구역명(없으면 ""), "items": [항목명, ...]}, ...]
    """
    sections: list[dict[str, Any]] = [{"title": "", "items": [], "note": ""}]
    seen: set[str] = set()
    total = 0

    def add(section: dict[str, Any], raw: Any) -> None:
        nonlocal total
        if total >= _OUTLINE_MAX_ITEMS_TOTAL:
            return
        if not isinstance(raw, str):
            return
        text = " ".join(raw.split()).rstrip(":：").strip()
        if not text or text.lower() in _OUTLINE_SKIP:
            return
        if len(text) > _OUTLINE_ITEM_MAX_CHARS or text.isdigit():
            return
        if text in seen or len(section["items"]) >= _OUTLINE_MAX_ITEMS_PER_SECTION:
            return
        seen.add(text)
        section["items"].append(text)
        total += 1

    for blk in blocks:
        kind = blk.get("type")
        if kind == "subtitle":
            if len(sections) >= _OUTLINE_MAX_SECTIONS:
                break
            sections.append(
                {"title": " ".join(str(blk.get("text", "")).split()), "items": [], "note": ""})
            continue

        cur = sections[-1]
        if kind == "grid":
            rows = blk.get("rows") or []
            n = len(rows[0]) if rows and isinstance(rows[0], list) else 0
            cols = blk.get("label_cols")
            if not cols:
                cols = list(range(0, n, 2))  # label_cols 생략 시 짝수 열이 라벨이다
            for row in rows:
                if not isinstance(row, list):
                    continue
                for c in cols:
                    if 0 <= c < len(row):
                        add(cur, row[c])
        elif kind == "table":
            for cell in blk.get("header") or []:
                add(cur, cell)
        elif kind == "article":
            add(cur, blk.get("heading"))
        elif kind == "textbox" and not cur["note"]:
            # 자기소개서처럼 서술형 칸만 있는 구역은 채울 항목이 없다.
            # 대신 칸 위의 안내문을 그대로 보여주면 무엇을 써야 하는지 알 수 있다.
            hint = " ".join(str(blk.get("hint", "")).split())
            if 0 < len(hint) <= 80:
                cur["note"] = hint

    # 항목도 안내문도 없는 묶음은 버린다 (제목만 있는 구역, 앞머리의 빈 묶음)
    return [s for s in sections if s["items"] or s["note"]]


_REQUIRED = ("id", "title", "category", "subcategory", "tags", "summary", "usage", "blocks")
_VALID_TYPES = {
    "doc_title", "subtitle", "para", "grid", "table", "textbox", "kv_list",
    "article", "date_line", "sign_line", "notice", "spacer", "page_break",
}


def load_spec(path: Path) -> FormSpec:
    """YAML 명세 파일을 읽어 FormSpec으로 변환한다.

    Raises:
        SpecError: 필수 필드 누락, 미지원 블록 타입, ID 규칙 위반 시.
    """
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{path.name}: YAML 파싱 실패 — {exc}") from exc
    except OSError as exc:
        raise SpecError(f"{path.name}: 파일 읽기 실패 — {exc}") from exc

    if not isinstance(raw, dict):
        raise SpecError(f"{path.name}: 최상위가 매핑(dict)이 아닙니다.")

    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise SpecError(f"{path.name}: 필수 필드 누락 — {', '.join(missing)}")

    form_id = str(raw["id"])
    if not form_id.replace("-", "").isalnum() or form_id != form_id.lower():
        raise SpecError(f"{path.name}: id는 영문 소문자·숫자·하이픈만 허용 (현재: {form_id})")
    if path.stem != form_id:
        raise SpecError(f"{path.name}: 파일명과 id가 다릅니다 (id={form_id})")

    blocks = raw["blocks"]
    if not isinstance(blocks, list) or not blocks:
        raise SpecError(f"{path.name}: blocks가 비어 있습니다.")
    for idx, blk in enumerate(blocks):
        if not isinstance(blk, dict) or "type" not in blk:
            raise SpecError(f"{path.name}: blocks[{idx}]에 type이 없습니다.")
        if blk["type"] not in _VALID_TYPES:
            raise SpecError(f"{path.name}: blocks[{idx}] 미지원 타입 — {blk['type']}")
        _check_yaml_bool_trap(path.name, idx, blk)

    return FormSpec(
        id=form_id,
        title=str(raw["title"]),
        category=str(raw["category"]),
        subcategory=str(raw["subcategory"]),
        tags=[str(t) for t in raw["tags"]],
        summary=str(raw["summary"]),
        usage=str(raw["usage"]),
        blocks=blocks,
        source=str(raw.get("source", "original")),
        source_note=str(raw.get("source_note", "")),
        featured=bool(raw.get("featured", False)),
        featured_rank=int(raw.get("featured_rank", 99)),
        series=str(raw.get("series", "")),
        series_name=str(raw.get("series_name", "")),
        variant=str(raw.get("variant", "")),
        variant_rank=int(raw.get("variant_rank", 99)),
        variant_use=str(raw.get("variant_use", "")),
        howto=_load_howto(path.name, raw.get("howto")),
        faq=_load_faq(path.name, raw.get("faq")),
        version=int(raw.get("version", 1)),
        created_by=str(raw.get("created_by", "manual")),
        status=str(raw.get("status", "published")),
        target_pages=int(raw.get("target_pages", 0)),
    )


def _load_howto(fname: str, raw: Any) -> list[str]:
    """작성 단계(howto)를 문자열 목록으로 읽는다. 없으면 빈 목록.

    Raises:
        SpecError: 목록이 아니거나 항목이 문자열이 아닌 경우.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SpecError(f"{fname}: howto는 목록이어야 합니다.")
    steps: list[str] = []
    for i, step in enumerate(raw):
        if not isinstance(step, str) or not step.strip():
            raise SpecError(f"{fname}: howto[{i}]가 빈 값이거나 문자열이 아닙니다.")
        steps.append(" ".join(step.split()))
    return steps


def _load_faq(fname: str, raw: Any) -> list[dict[str, str]]:
    """자주 묻는 질문(faq)을 [{q, a}] 목록으로 읽는다. 없으면 빈 목록.

    Raises:
        SpecError: 목록이 아니거나 q·a 키가 빠진 경우.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SpecError(f"{fname}: faq는 목록이어야 합니다.")
    items: list[dict[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or "q" not in item or "a" not in item:
            raise SpecError(f"{fname}: faq[{i}]에 q 또는 a가 없습니다.")
        q, a = str(item["q"]).strip(), str(item["a"]).strip()
        if not q or not a:
            raise SpecError(f"{fname}: faq[{i}]의 q 또는 a가 비어 있습니다.")
        items.append({"q": " ".join(q.split()), "a": " ".join(a.split())})
    return items


def _check_yaml_bool_trap(fname: str, idx: int, blk: dict[str, Any]) -> None:
    """YAML 불리언 함정 검사.

    YAML은 따옴표 없는 No/Yes/On/Off/Y/N을 불리언으로 파싱한다. 표 머리글에 흔히 쓰는
    'No'가 False로 바뀌어 출력물에 잘못 찍히므로 명세 단계에서 차단한다.
    """
    def scan(value: Any, where: str) -> None:
        if isinstance(value, bool):
            raise SpecError(
                f"{fname}: blocks[{idx}] {where}에 불리언({value})이 있습니다. "
                f"YAML이 No/Yes/On/Off를 불리언으로 읽습니다 — 따옴표로 감싸십시오 (예: \"No\")."
            )
        if isinstance(value, list):
            for v in value:
                scan(v, where)

    for key in ("header", "rows", "items", "lines", "labels", "sample_rows", "sample_names"):
        if key in blk:
            scan(blk[key], key)


def load_all_specs(specs_dir: Path) -> list[FormSpec]:
    """specs 폴더의 모든 YAML 명세를 id 순으로 읽는다."""
    specs: list[FormSpec] = []
    for p in sorted(specs_dir.glob("*.yaml")):
        specs.append(load_spec(p))
    seen: set[str] = set()
    for s in specs:
        if s.id in seen:
            raise SpecError(f"서식 ID 중복: {s.id}")
        seen.add(s.id)
    return specs


def pct_to_mm(widths_pct: list[float]) -> list[float]:
    """컬럼 비율(%)을 실제 mm 폭으로 변환한다."""
    total = sum(widths_pct)
    if total <= 0:
        raise SpecError("widths 합계가 0 이하입니다.")
    return [USABLE_WIDTH_MM * w / total for w in widths_pct]
