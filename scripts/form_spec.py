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
        version=int(raw.get("version", 1)),
        created_by=str(raw.get("created_by", "manual")),
        status=str(raw.get("status", "published")),
        target_pages=int(raw.get("target_pages", 0)),
    )


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
