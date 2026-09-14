"""명세(FormSpec) → HWPX 생성 (python-hwpx, 한컴오피스 불필요).

DOCX를 변환하는 것이 아니라 동일 명세에서 병행 생성하므로 레이아웃이 무너지지 않는다.
HWPX는 개방형 표준(OWPML, KS X 6101)으로 한글 2010 이상에서 열린다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hwpx import HwpxDocument

from form_spec import FormSpec

FONT_HWP = "맑은 고딕"  # 한글(HWPX)에서 쓰는 글꼴명. DOCX의 "Malgun Gothic"과 같은 글꼴

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"  # hp 네임스페이스

MM = 283.465  # 1mm → HWPUNIT (1/7200 inch)
PAGE_W = int(210 * MM)
PAGE_H = int(297 * MM)
MARGIN = int(18 * MM)
USABLE_W = int(174 * MM)

HEADER_FILL = "#24384F"
LABEL_FILL = "#F4F6F9"
BORDER_COLOR = "#C9D2DD"
ACCENT = "#24384F"
HEADER_TEXT = "#FFFFFF"
LABEL_TEXT = "#2B3A4A"
MUTED = "#6B7280"

_SCALE = 1.0  # 자동 맞춤 배율 (DOCX와 동일 규칙)


class _Styles:
    """문단 정렬 스타일 id 모음. 임시 문단에 서식을 적용해 id를 확보한 뒤 재사용한다."""

    def __init__(self, doc: HwpxDocument) -> None:
        self.doc = doc
        self._cache: dict[tuple[str, int], str] = {}
        self.pending_first: Any | None = None  # 아직 사용되지 않은 선두 문단

    def para_pr(self, alignment: str, line_spacing: int = 140) -> str:
        """정렬·줄간격 조합에 해당하는 paraPr id를 반환한다."""
        key = (alignment, line_spacing)
        if key in self._cache:
            return self._cache[key]
        tmp = self.doc.add_paragraph("")
        self.doc.set_paragraph_format(
            paragraph_index=len(self.doc.paragraphs) - 1,
            alignment=alignment,
            line_spacing_percent=line_spacing,
        )
        pid = tmp.para_pr_id_ref
        tmp.remove()
        self._cache[key] = pid
        return pid


_ALIGN = {"left": "LEFT", "center": "CENTER", "right": "RIGHT", "both": "JUSTIFY"}


def _register_fonts(doc: HwpxDocument) -> None:
    """문서 글꼴 목록에 사용 글꼴을 등록한다.

    등록하지 않으면 add_run(font=...)이 조용히 무시되고 기본 글꼴(함초롬바탕)로 표시된다.
    """
    try:
        header = doc.parts.headers[0]
    except (AttributeError, IndexError):
        return
    for lang in ("HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"):
        try:
            header.ensure_font(FONT_HWP, lang=lang, subst_face="함초롬돋움")
        except (TypeError, ValueError, KeyError):
            # 특정 언어 슬롯 등록에 실패해도 나머지는 계속 시도한다
            continue


def render_hwpx(spec: FormSpec, out_path: Path, *, scale: float = 1.0) -> Path:
    """명세를 HWPX로 렌더링한다."""
    global _SCALE
    _SCALE = scale
    doc = HwpxDocument.new()
    # orientation은 넘기지 않는다. 기본 템플릿이 이미 세로 A4이며,
    # 값을 넣으면 landscape 속성이 NARROWLY로 바뀌어 한글에서 가로 용지로 열린다.
    doc.set_page_size(width=PAGE_W, height=PAGE_H)
    doc.set_page_margins(left=MARGIN, right=MARGIN, top=MARGIN, bottom=MARGIN,
                         header=0, footer=0)

    _register_fonts(doc)

    st = _Styles(doc)
    # 첫 문단의 run에 secPr(용지 설정)가 들어 있어 삭제하면 용지 설정이 사라진다.
    # 따라서 삭제하지 않고 첫 블록이 이 문단을 재사용한다.
    st.pending_first = doc.paragraphs[0] if doc.paragraphs else None

    for blk in spec.blocks:
        _render_block(doc, st, blk)

    # 첫 블록이 표였다면 선두 빈 문단이 남으므로 1pt로 축소해 여백 낭비를 막는다
    if st.pending_first is not None:
        st.pending_first.add_run("", size=1, font=FONT_HWP)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(str(out_path))
    return out_path


def _add(
    doc: HwpxDocument,
    st: _Styles,
    text: str,
    *,
    size: float = 10.5,
    bold: bool = False,
    align: str = "left",
    color: str | None = None,
    line_spacing: int = 140,
) -> Any:
    """서식이 적용된 문단을 추가한다 (선두 빈 문단이 남아 있으면 재사용)."""
    para_pr = st.para_pr(_ALIGN[align], line_spacing)
    if st.pending_first is not None:
        p = st.pending_first
        st.pending_first = None
        p.para_pr_id_ref = para_pr
    else:
        p = doc.add_paragraph("", para_pr_id_ref=para_pr, include_run=False)
    p.add_run(text, bold=bold, size=size, font=FONT_HWP, color=color)
    return p


def _fill_cell(
    table: Any,
    st: _Styles,
    r: int,
    c: int,
    text: str,
    *,
    size: float = 10.0,
    bold: bool = False,
    align: str = "left",
    fill: str | None = None,
    color: str | None = None,
) -> None:
    """표 셀에 서식이 적용된 텍스트를 넣는다."""
    cell = table.cell(r, c)
    cell.set_text("")
    para = cell.paragraphs[0]
    para.clear_text()
    para.para_pr_id_ref = st.para_pr(_ALIGN[align], 130)
    lines = text.split("\n") if text else [""]
    para.add_run(lines[0], bold=bold, size=size, font=FONT_HWP, color=color)
    for extra in lines[1:]:
        nxt = cell.add_paragraph("", include_run=False)
        nxt.para_pr_id_ref = para.para_pr_id_ref
        nxt.add_run(extra, bold=bold, size=size, font=FONT_HWP, color=color)
    table.set_cell_borders(r, c, color=BORDER_COLOR)
    if fill:
        table.set_cell_shading(r, c, fill)


def _row_height(table: Any, row_idx: int, height_mm: float) -> None:
    """행의 모든 셀에 높이를 지정하고 표 전체 높이를 다시 합산한다.

    HWPX는 행이 아니라 셀이 높이를 가지며, 표의 hp:sz height가 셀 합계와 어긋나면
    한글에서 레이아웃이 틀어질 수 있어 함께 갱신한다.
    """
    h = int(height_mm * MM * _SCALE)
    for cell in table.rows[row_idx].cells:
        try:
            cell.set_size(height=h)
        except (ValueError, TypeError):
            return
    _sync_table_height(table)


def _sync_table_height(table: Any) -> None:
    """표의 hp:sz height를 각 행 첫 셀 높이의 합으로 맞춘다."""
    total = 0
    for row in table.rows:
        cells = row.cells
        if not cells:
            continue
        cell_sz = cells[0].element.find(f"{{{_HP_NS}}}cellSz")
        if cell_sz is None:
            return
        total += int(cell_sz.get("height", "0"))
    sz = table.element.find(f"{{{_HP_NS}}}sz")
    if sz is not None and total > 0:
        sz.set("height", str(total))


def _render_block(doc: HwpxDocument, st: _Styles, blk: dict[str, Any]) -> None:
    """블록 1개를 렌더링한다 (render_docx._render_block과 동일 규칙)."""
    btype = blk["type"]

    if btype == "doc_title":
        text = str(blk["text"])
        spaced = blk.get("spaced", True)
        shown = "  ".join(text) if spaced and len(text) <= 8 else text
        _add(doc, st, shown, size=18, bold=True, align="center", color=ACCENT)
        rule = _add(doc, st, "", size=2)
        doc.set_paragraph_format(paragraph_index=len(doc.paragraphs) - 1,
                                 bottom_border=True, border_color=ACCENT,
                                 border_width="0.4 mm")

    elif btype == "subtitle":
        _add(doc, st, f"▌ {blk['text']}", size=10.5, bold=True,
             align=blk.get("align", "left"), color=LABEL_TEXT)

    elif btype == "para":
        _add(doc, st, str(blk.get("text", "")), size=blk.get("size", 10.5),
             align=blk.get("align", "left"), bold=blk.get("bold", False))

    elif btype == "grid":
        rows: list[list[str]] = blk["rows"]
        n_cols = len(rows[0])
        widths = blk.get("widths") or [100 / n_cols] * n_cols
        label_cols = set(blk.get("label_cols", [i for i in range(n_cols) if i % 2 == 0]))
        table = doc.add_table(len(rows), n_cols, width=USABLE_W)
        table.set_column_widths(widths)
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                is_label = c in label_cols and str(val).strip() != ""
                _fill_cell(table, st, r, c, str(val), size=10.0, bold=is_label,
                           align="center" if is_label else "left",
                           fill=LABEL_FILL if is_label else None,
                           color=LABEL_TEXT if is_label else None)
            _row_height(table, r, blk.get("row_height_mm", 7.5))
        for merge in blk.get("merges", []):
            r1, c1, r2, c2 = merge
            try:
                table.merge_cells(r1, c1, r2, c2)
            except (ValueError, KeyError, TypeError):
                pass  # 병합 실패 시 개별 셀로 유지 (레이아웃만 소폭 달라짐)
        _add(doc, st, "", size=5)

    elif btype == "table":
        header: list[str] = blk["header"]
        n_cols = len(header)
        widths = blk.get("widths") or [100 / n_cols] * n_cols
        n_empty = int(blk.get("empty_rows", 3))
        body: list[list[str]] = blk.get("rows", [])
        table = doc.add_table(1 + len(body) + n_empty, n_cols, width=USABLE_W)
        table.set_column_widths(widths)
        for c, h in enumerate(header):
            _fill_cell(table, st, 0, c, h, size=9.5, bold=True, align="center",
                       fill=HEADER_FILL, color=HEADER_TEXT)
        _row_height(table, 0, blk.get("row_height_mm", 7.5))
        for r, row in enumerate(body, start=1):
            for c, val in enumerate(row):
                _fill_cell(table, st, r, c, str(val), size=10.0,
                           align=blk.get("body_align", "center"))
            _row_height(table, r, blk.get("row_height_mm", 7.5))
        for r in range(1 + len(body), 1 + len(body) + n_empty):
            for c in range(n_cols):
                _fill_cell(table, st, r, c, "", size=10.0)
            _row_height(table, r, blk.get("row_height_mm", 7.5))
        _add(doc, st, "", size=5)

    elif btype == "textbox":
        hint = str(blk.get("hint", "")).strip()
        if hint:
            _add(doc, st, hint, size=8.5, color=MUTED)
        table = doc.add_table(1, 1, width=USABLE_W,
                              height=int(blk.get("height_mm", 30) * MM * _SCALE))
        _fill_cell(table, st, 0, 0, "", size=10.0)
        _row_height(table, 0, blk.get("height_mm", 30))
        _add(doc, st, "", size=5)

    elif btype == "kv_list":
        for item in blk["items"]:
            _add(doc, st, f"· {item}", size=10.0)

    elif btype == "article":
        _add(doc, st, str(blk["heading"]), size=10.5, bold=True)
        for line in blk.get("lines", []):
            _add(doc, st, str(line), size=10.0, align="both")

    elif btype == "date_line":
        _add(doc, st, "", size=8)
        _add(doc, st, blk.get("text", "20        년        월        일"),
             size=11, align="center")
        _add(doc, st, "", size=6)

    elif btype == "sign_line":
        for label in blk.get("labels", [blk.get("label", "작성자")]):
            _add(doc, st, f"{label} :                                        (서명 또는 인)",
                 size=11, align="right")

    elif btype == "notice":
        _add(doc, st, "", size=6)
        _add(doc, st, "※ " + str(blk["text"]), size=8.5, color=MUTED)

    elif btype == "spacer":
        _add(doc, st, "", size=blk.get("size", 10))

    elif btype == "page_break":
        p = doc.add_paragraph("", include_run=False)
        doc.set_paragraph_format(paragraph_index=len(doc.paragraphs) - 1,
                                 page_break_before=True)
