"""법정서식 원문 PDF → 명세 blocks(gov_table·para·doc_title) 자동 변환.

국가법령정보센터(law.go.kr)에서 받은 서식 PDF는 선이 벡터로 들어 있다. 이 선 격자를 그대로
읽어 표의 열 폭·행 높이·병합·칸 글자·음영을 옮기므로, 사람이 표를 다시 짜면서 생기는
항목 누락·순서 뒤바뀜이 원천적으로 없다(SPEC_GUIDE 3-5절).

사용법:
    python scripts/pdf_to_gov_spec.py <원문.pdf> <출력.yaml>   # blocks 만 담긴 YAML 조각
    python scripts/pdf_to_gov_spec.py <원문.pdf> --print         # 화면 출력

만든 조각은 명세의 blocks 로 붙이고, 메타(title·summary·howto·faq·law_ref 등)는 따로 쓴다.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
import yaml

PT_TO_MM = 25.4 / 72
USABLE_WIDTH_MM = 174.0
# 원문 글꼴(바탕·돋움 계열)은 폭이 좁다. 맑은 고딕/Noto 로 같은 크기를 쓰면 칸 안에서 줄이 넘치므로 줄인다
FONT_RATIO = 0.9

# 원문 가장자리의 인쇄용 표기는 옮기지 않는다
_DROP_LINE = re.compile(r"^\s*(\d{3}\s*mm\s*[×x]\s*\d{3}\s*mm.*|\(앞\s*쪽\)|\(뒤\s*쪽\)|\(\s*\d+\s*쪽\s*중\s*제?\s*\d+\s*쪽\s*\))\s*$")
_DROP_TOKEN = re.compile(r"\((앞|뒤)\s*쪽\)|\(\s*\d+\s*쪽\s*중\s*제?\s*\d+\s*쪽\s*\)|\d{3}\s*mm\s*[×x]\s*\d{3}\s*mm\s*\[[^\]]*\]")

# 옛 서식 하단의 인쇄 관리 표기(서식번호·승인일·용지 규격)
_PRINT_CODE = re.compile(r"^\s*\d{5}-\d{5}|\d{2}\.\s?\d{1,2}\.\s?\d{1,2}\s*승인|\((신문|인쇄|백상|중질)[^)]*\d+\s*g")

TABLE_SETTINGS: dict[str, Any] = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 2.5,
    "join_tolerance": 2.5,
    "intersection_tolerance": 2.5,
    "edge_min_length": 4,
}


class ConvertError(RuntimeError):
    """변환 실패."""


@dataclass
class Element:
    """페이지 위의 한 요소(표 또는 글줄). top 순서로 정렬해 blocks 로 낸다."""

    top: float
    bottom: float
    block: dict[str, Any]
    kind: str = "para"


@dataclass
class Line:
    """같은 높이에 놓인 글자 묶음."""

    top: float
    bottom: float
    chars: list[dict[str, Any]] = field(default_factory=list)


def _cluster(values: list[float], tol: float) -> list[float]:
    """가까운 좌표를 하나로 묶어 대표값(평균) 목록을 만든다."""
    out: list[list[float]] = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(g) / len(g) for g in out]


def _index(edges: list[float], v: float) -> int:
    """v 에 가장 가까운 경계의 번호."""
    return min(range(len(edges)), key=lambda i: abs(edges[i] - v))


def _group_lines(chars: list[dict[str, Any]]) -> list[Line]:
    """글자를 줄 단위로 묶는다 (세로 중심이 글자 크기의 절반 이내면 같은 줄)."""
    lines: list[Line] = []
    for ch in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        if not ch["text"].strip():
            continue
        mid = (ch["top"] + ch["bottom"]) / 2
        size = ch["bottom"] - ch["top"]
        for ln in lines:
            if abs((ln.top + ln.bottom) / 2 - mid) <= max(size, 4) * 0.5:
                ln.chars.append(ch)
                ln.top = min(ln.top, ch["top"])
                ln.bottom = max(ln.bottom, ch["bottom"])
                break
        else:
            lines.append(Line(ch["top"], ch["bottom"], [ch]))
    lines.sort(key=lambda l: l.top)
    return lines


def _line_text(ln: Line) -> tuple[str, float, float, float, bool]:
    """줄의 글자를 이어 붙인다. 넓은 간격은 공백 여러 개로 보존한다.

    Returns: (글자, 왼쪽 x, 오른쪽 x, 글자 크기, 굵게 여부)
    """
    chars = sorted(ln.chars, key=lambda c: c["x0"])
    size = statistics.median(c["size"] for c in chars)
    out = ""
    prev: dict[str, Any] | None = None
    for ch in chars:
        if prev is not None:
            gap = ch["x0"] - prev["x1"]
            if gap > size * 2.2:
                out += " " * min(12, max(2, round(gap / size)))
            elif gap > size * 0.22:
                out += " "
        out += ch["text"]
        prev = ch
    bold = sum(1 for c in chars if re.search(r"bold|heavy|black|견고딕|HY헤드", c.get("fontname", ""), re.I)) > len(chars) / 2
    text = _DROP_TOKEN.sub("", out).rstrip()
    # 기호 글꼴의 사용자 정의 영역 글자(원 안의 '인' 등)는 한글 글꼴에 없으므로 대체한다
    text = text.replace("\uf000", "㊞").replace("\u2024", "·").replace("è", "→").replace("\uf0e8", "→").replace("\u2027", "·").replace("\u223c", "~")
    return text, chars[0]["x0"], chars[-1]["x1"], float(size), bold


def _align(x0: float, x1: float, left: float, right: float) -> str:
    """글줄이 영역 안에서 왼쪽·가운데·오른쪽 중 어디에 붙어 있는지."""
    width = max(right - left, 1)
    lpad, rpad = x0 - left, right - x1
    if (x1 - x0) > width * 0.8:
        return "l"  # 칸을 거의 채운 줄은 줄바꿈된 본문이다
    if abs(lpad - rpad) <= width * 0.12 and lpad > width * 0.06:
        return "c"
    if rpad < lpad and rpad < width * 0.15:
        return "r"
    return "l"


def _merge_wrapped(lines: list[list[str]], spans: list[tuple[float, float]],
                   left: float, right: float) -> list[list[str]]:
    """원문에서 칸 폭 때문에 줄바꿈된 문장을 한 문단으로 다시 잇는다.

    - 한 줄이 칸 폭의 75% 이상을 차지하면 다음 줄은 같은 문장의 이어짐으로 본다.
      (글꼴 폭이 달라 원문 위치에서 끊으면 줄이 이중으로 꺾인다)
    - 세로쓰기(한두 글자씩 여러 줄)는 한 줄로 합쳐 칸 안에서 저절로 줄바꿈되게 한다.
    """
    if len(lines) >= 3 and all(len(t.strip()) <= 2 for _, t in lines):
        return [["c", "".join(t.strip() for _, t in lines)]]
    width = max(right - left, 1)
    out: list[list[str]] = []
    prev_long = False
    for (al, text), (x0, x1) in zip(lines, spans):
        if out and prev_long and not re.match(r"^\s*([0-9]+[.)]|[가-하][.)]|[-※○□▶■●]|\[ ?\])", text):
            out[-1][1] = out[-1][1].rstrip() + " " + text.strip()
            out[-1][0] = "l"
        else:
            out.append([al, text])
        prev_long = (x1 - x0) > width * 0.75
    return out


def _is_filled(rects: list[dict[str, Any]], box: tuple[float, float, float, float]) -> bool:
    """칸 가운데에 흰색이 아닌 채움 사각형이 있으면 음영 칸으로 본다."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for rc in rects:
        if not rc.get("fill"):
            continue
        col = rc.get("non_stroking_color")
        vals = list(col) if isinstance(col, (list, tuple)) else ([col] if col is not None else [])
        if not vals:
            continue
        # 흰색(1 또는 1,1,1 / CMYK 0,0,0,0)은 음영이 아니다
        if len(vals) == 4:
            white = all(v <= 0.02 for v in vals)
        else:
            white = all(v >= 0.97 for v in vals)
        if white:
            continue
        w, h = rc["x1"] - rc["x0"], rc["bottom"] - rc["top"]
        if w < 3 or h < 3:
            continue  # 선을 사각형으로 그린 경우
        if rc["x0"] <= cx <= rc["x1"] and rc["top"] <= cy <= rc["bottom"]:
            return True
    return False


def _leaf_cells(cells: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
    """다른 칸을 품은 바깥 칸(표 안의 작은 표를 둘러싼 칸)을 뺀다.

    바깥 칸을 병합 칸으로 그리면 안쪽 칸과 겹쳐 글자가 사라진다(2026-09-16 인감신고서에서 식별).
    바깥 칸의 글자 중 안쪽 칸에 속하지 않는 것은 표 밖 문단으로 옮겨진다.
    """
    def inside(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
        return a is not b and b[0] >= a[0] - 1 and b[1] >= a[1] - 1 and b[2] <= a[2] + 1 and b[3] <= a[3] + 1 \
            and (b[2] - b[0]) * (b[3] - b[1]) < (a[2] - a[0]) * (a[3] - a[1]) * 0.95
    return [a for a in cells if not any(inside(a, b) for b in cells)]


def _table_block(page: Any, table: Any, content_w_pt: float, x_min: float = 0.0,
                 x_max: float = 0.0) -> dict[str, Any]:
    """pdfplumber 표 1개 → gov_table 블록.

    표가 본문 폭보다 좁으면(오른쪽에 붙은 수수료 칸 등) 좌우에 선 없는 여백 열을 두어 위치를 지킨다.
    """
    cells = _leaf_cells([c for c in table.cells if c is not None])
    xs = _cluster([v for c in cells for v in (c[0], c[2])], 1.6)
    if x_max > x_min:
        if xs[0] - x_min > 4:
            xs = [x_min] + xs
        if x_max - xs[-1] > 4:
            xs = xs + [x_max]
    ys = _cluster([v for c in cells for v in (c[1], c[3])], 1.6)
    if len(xs) < 2 or len(ys) < 2:
        raise ConvertError("표 격자를 읽지 못했습니다.")
    scale = USABLE_WIDTH_MM / (content_w_pt * PT_TO_MM)
    widths_pt = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    total = sum(widths_pt)
    widths = [round(w / total * 100, 3) for w in widths_pt]
    heights = [round((ys[i + 1] - ys[i]) * PT_TO_MM * scale, 2) for i in range(len(ys) - 1)]

    chars = page.chars
    rects = getattr(page, "rects_all", page.rects)
    out_cells: list[dict[str, Any]] = []
    used: set[tuple[int, int]] = set()
    for box in sorted(cells, key=lambda b: (round(b[1], 1), b[0])):
        r, r2 = _index(ys, box[1]), _index(ys, box[3])
        c, c2 = _index(xs, box[0]), _index(xs, box[2])
        if r2 <= r or c2 <= c or (r, c) in used:
            continue
        used.add((r, c))
        inside = [ch for ch in chars
                  if box[0] - 0.5 <= (ch["x0"] + ch["x1"]) / 2 <= box[2] + 0.5
                  and box[1] - 0.5 <= (ch["top"] + ch["bottom"]) / 2 <= box[3] + 0.5]
        lines_out: list[list[str]] = []
        raw_lines: list[tuple[float, float]] = []
        sizes: list[float] = []
        bolds: list[bool] = []
        for ln in _group_lines(inside):
            text, x0, x1, size, bold = _line_text(ln)
            if not text.strip():
                continue
            lines_out.append([_align(x0, x1, box[0], box[2]), text])
            raw_lines.append((x0, x1))
            sizes.append(size)
            bolds.append(bold)
        lines_out = _merge_wrapped(lines_out, raw_lines, box[0], box[2])
        spec: dict[str, Any] = {"at": [r, c, r2 - r, c2 - c]}
        if lines_out:
            spec["lines"] = lines_out
            spec["size"] = round(max(6.5, min(11.0, statistics.median(sizes) * FONT_RATIO)), 1)
            if sum(bolds) > len(bolds) / 2:
                spec["bold"] = True
            # 글줄이 칸 위쪽에 몰려 있으면(칸 이름 + 빈 기입란) 위 정렬
            top_text = min(ch["top"] for ch in inside)
            bottom_text = max(ch["bottom"] for ch in inside)
            if (box[3] - box[1]) > 3 * (bottom_text - top_text + 2) and top_text - box[1] < (box[3] - box[1]) * 0.3:
                spec["valign"] = "t"
        if _is_filled(rects, box):
            spec["fill"] = True
        out_cells.append(spec)
    return {"type": "gov_table", "widths": widths, "heights_mm": heights, "cells": out_cells}


def _is_edge_object(obj: dict[str, Any]) -> bool:
    """선으로 쓰지 않을 객체를 거른다.

    테두리 없이 채우기만 한 사각형(글자 뒤 흰 바탕, 칸 음영)은 표의 선이 아니다.
    두께 1.2pt 미만의 가는 사각형은 선을 사각형으로 그린 경우라 남긴다.
    """
    if obj.get("object_type") != "rect":
        return True
    thin = (obj["x1"] - obj["x0"]) < 1.2 or (obj["bottom"] - obj["top"]) < 1.2
    return bool(obj.get("stroke")) or thin


def _edge_lines(page: Any) -> list[dict[str, Any]]:
    """바깥 세로선이 생략된 표(한국 법정서식의 흔한 모양)를 닫아 줄 가상 세로선을 만든다.

    좌우 끝에 닿는 가로선들 사이 구간마다, 그 구간에 안쪽 세로선이 지나가거나 글자가 있으면
    같은 표로 보고 끝선을 잇는다. 둘 다 없으면 표와 표 사이의 빈 여백이므로 잇지 않는다.
    """
    segs = [l for l in page.lines if abs(l["top"] - l["bottom"]) < 1] + \
           [{"x0": r["x0"], "x1": r["x1"], "top": r["top"], "bottom": r["top"]} for r in page.rects
            if r["bottom"] - r["top"] < 1.2]
    for r in page.rects:  # 사각형 테두리의 위·아래 변도 가로선으로 본다
        if r["bottom"] - r["top"] >= 1.2 and r["x1"] - r["x0"] > 40 and r.get("stroke"):
            segs.append({"x0": r["x0"], "x1": r["x1"], "top": r["top"], "bottom": r["top"]})
            segs.append({"x0": r["x0"], "x1": r["x1"], "top": r["bottom"], "bottom": r["bottom"]})
    if not segs:
        return []
    left = min(l["x0"] for l in segs if l["x1"] - l["x0"] > 60) if any(l["x1"] - l["x0"] > 60 for l in segs) else 0
    right = max(l["x1"] for l in segs if l["x1"] - l["x0"] > 60) if any(l["x1"] - l["x0"] > 60 for l in segs) else 0
    verts = [l for l in page.lines if abs(l["x0"] - l["x1"]) < 1] + \
            [{"x0": r["x0"], "top": r["top"], "bottom": r["bottom"]} for r in page.rects if r["x1"] - r["x0"] < 1.2]
    out: list[dict[str, Any]] = []
    for edge, side in ((left, "x0"), (right, "x1")):
        ys = sorted({round(l["top"], 1) for l in segs if abs(l[side] - edge) <= 3})
        run: list[float] = []
        for y in ys:
            if run:
                a, b = run[-1], y
                has_vert = any(v["top"] < b - 1 and v["bottom"] > a + 1 and abs(v["x0"] - edge) > 3 for v in verts)
                has_text = any(a < (c["top"] + c["bottom"]) / 2 < b for c in page.chars
                               if c["text"].strip() and left - 2 <= c["x0"] <= right + 2)
                if not (has_vert or has_text) or b - a > 400:
                    if len(run) > 1:
                        out.append(_vline(edge, run[0], run[-1]))
                    run = []
            run.append(y)
        if len(run) > 1:
            out.append(_vline(edge, run[0], run[-1]))
    return out


def _vline(x: float, top: float, bottom: float) -> dict[str, Any]:
    """pdfplumber 가 선으로 받아들이는 모양의 세로선 객체."""
    return {"object_type": "line", "x0": x, "x1": x, "top": top, "bottom": bottom,
            "width": 0, "height": bottom - top, "doctop": top, "orientation": "v"}


@dataclass
class TableGroup:
    """나란히 놓인 표 여러 개를 한 격자로 합친 묶음 (pdfplumber Table 과 같은 속성만 쓴다)."""

    cells: list[tuple[float, float, float, float]]
    bbox: tuple[float, float, float, float]


def _join_side_by_side(tables: list[Any]) -> list[Any]:
    """좌우로 나란히 붙은 표(예: 왼쪽 기간표 + 오른쪽 임금표)를 하나로 합친다.

    따로 두면 위아래로 쌓여 원문의 좌우 배치가 깨지고 쪽수가 늘어난다.
    세로 범위가 작은 표 높이의 절반 이상 겹치고 가로로는 겹치지 않으면 같은 줄로 본다.
    """
    groups: list[TableGroup] = [TableGroup([c for c in t.cells if c is not None], tuple(t.bbox)) for t in tables]
    changed = True
    while changed:
        changed = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                a, b = groups[i].bbox, groups[j].bbox
                overlap_y = min(a[3], b[3]) - max(a[1], b[1])
                small_h = min(a[3] - a[1], b[3] - b[1])
                overlap_x = min(a[2], b[2]) - max(a[0], b[0])
                if small_h > 0 and overlap_y >= small_h * 0.5 and overlap_x <= 2:
                    groups[i] = TableGroup(groups[i].cells + groups[j].cells,
                                           (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])))
                    del groups[j]
                    changed = True
                    break
            if changed:
                break
    return groups


def convert(pdf_path: Path) -> list[dict[str, Any]]:
    """원문 PDF 를 blocks 목록으로 바꾼다."""
    try:
        pdf = pdfplumber.open(str(pdf_path))
    except (OSError, ValueError) as exc:
        raise ConvertError(f"PDF 열기 실패 — {exc}") from exc

    pages = []
    x_min, x_max = 10_000.0, 0.0
    for raw_page in pdf.pages:
        page = raw_page.filter(_is_edge_object)
        page.rects_all = raw_page.rects  # 음영 판정은 원래 사각형으로
        settings = dict(TABLE_SETTINGS)
        settings["explicit_vertical_lines"] = _edge_lines(page)
        tables = _join_side_by_side([t for t in page.find_tables(settings)
                                     if (t.bbox[2] - t.bbox[0]) > 40 and (t.bbox[3] - t.bbox[1]) > 6])
        pages.append((page, tables))
        for t in tables:
            x_min, x_max = min(x_min, t.bbox[0]), max(x_max, t.bbox[2])
    if x_max <= x_min:
        raise ConvertError("표를 찾지 못했습니다 (스캔 이미지 PDF 일 수 있음).")
    content_w = x_max - x_min
    pt_scale = USABLE_WIDTH_MM / (content_w * PT_TO_MM)

    blocks: list[dict[str, Any]] = []
    title_done = False
    for pno, (page, tables) in enumerate(pages):
        if pno:
            blocks.append({"type": "page_break"})
        elements: list[Element] = []
        for t in tables:
            elements.append(Element(t.bbox[1], t.bbox[3], _table_block(page, t, content_w, x_min, x_max), "table"))
        # 표 테두리 안이라도 어느 칸에도 속하지 않은 글자(표 옆 서명란 등)는 문단으로 살린다
        boxes = [c for t in tables for c in _leaf_cells([c for c in t.cells if c is not None])]
        free = [ch for ch in page.chars
                if not any(b[0] - 1 <= (ch["x0"] + ch["x1"]) / 2 <= b[2] + 1
                           and b[1] - 1 <= (ch["top"] + ch["bottom"]) / 2 <= b[3] + 1 for b in boxes)]
        for ln in _group_lines(free):
            text, x0, x1, size, bold = _line_text(ln)
            if not text.strip() or _DROP_LINE.match(text) or _PRINT_CODE.search(text):
                continue
            if size >= 13 and not title_done:
                blk: dict[str, Any] = {"type": "doc_title", "text": " ".join(text.split()), "_x0": x0}
                kind = "title"
            else:
                al = {"l": "left", "c": "center", "r": "right"}[_align(x0, x1, x_min, x_max)]
                blk = {"type": "para", "text": text, "align": al,
                       "size": round(max(7.0, min(12.0, size * FONT_RATIO)), 1), "space_after": 0, "line_spacing": 1.0}
                if bold:
                    blk["bold"] = True
                blk["_long"] = (x1 - x0) > (x_max - x_min) * 0.75
                kind = "para"
            elements.append(Element(ln.top, ln.bottom, blk, kind))
        elements.sort(key=lambda e: e.top)
        # 큰 글자 제목 조각(예: "[ ]휴업 / [ ]폐업" + "신고서")은 한 제목으로 합친다
        titles = [e for e in elements if e.kind == "title"]
        merged: list[Element] = []
        if titles:
            first = titles[0]
            band = [t for t in titles if t.top - first.top < 40]
            band.sort(key=lambda e: (round(e.block.get("_x0", 0) / 25), e.top))
            first.block = {"type": "doc_title", "text": " ".join(t.block["text"] for t in band), "spaced": False}
            first.top = min(t.top for t in band)
            first.bottom = max(t.bottom for t in band)
            drop = {id(t) for t in band if t is not first}
            elements = [e for e in elements if id(e) not in drop]
            for t in titles:
                if t not in band:  # 제목 밖의 큰 글자는 굵은 문단으로
                    t.kind = "para"
                    t.block = {"type": "para", "text": t.block["text"], "align": "center",
                               "size": 12.0, "bold": True, "space_after": 0}
            title_done = True
        merged = []
        for el in elements:
            prev = merged[-1] if merged else None
            if (prev is not None and prev.kind == "para" and el.kind == "para"
                    and prev.block.get("_long") and el.top - prev.bottom < prev.block["size"] * 0.9
                    and abs(prev.block["size"] - el.block["size"]) < 0.6
                    and not re.match(r"^\s*([0-9]+[.)]|[가-하][.)]|[-※○□▶■●]|\[ ?\])", el.block["text"])):
                prev.block["text"] = prev.block["text"].rstrip() + " " + el.block["text"].strip()
                prev.block["align"] = "left"
                prev.block["_long"] = el.block.get("_long")
                prev.bottom = el.bottom
                continue
            merged.append(el)
        for el in merged:
            el.block.pop("_long", None)
        prev_bottom: float | None = None
        for el in merged:
            if prev_bottom is not None:
                gap = el.top - prev_bottom
                if gap > 4 and el.kind != "title":
                    blocks.append({"type": "spacer", "exact": True, "height_pt": round(min(gap, 60) * pt_scale, 1)})
            blocks.append(el.block)
            prev_bottom = el.bottom
    return blocks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("out", type=Path, nargs="?")
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args(argv)
    try:
        blocks = convert(args.pdf)
    except ConvertError as exc:
        print(f"[오류] {args.pdf.name}: {exc}", file=sys.stderr)
        return 1
    text = yaml.safe_dump({"blocks": blocks}, allow_unicode=True, sort_keys=False, width=200,
                          default_flow_style=None)
    if args.print or not args.out:
        print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        n_tab = sum(1 for b in blocks if b["type"] == "gov_table")
        print(f"[완료] {args.pdf.name} → {args.out} (표 {n_tab}개, 블록 {len(blocks)}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
