"""네이버 블로그 초안용 이미지 생성기 — 대표 썸네일·작성 예시(번호 표시)·체크리스트·비교 카드.

모든 이미지는 원본 제작이다(다른 블로그·사이트 이미지 재사용 금지 — 유사 이미지 판정 방지).
글꼴: 리눅스 Noto Sans CJK KR, 윈도 맑은 고딕 순으로 찾는다.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NAVY: str = "#1b2c40"
ACCENT: str = "#e8590c"      # 번호 표시·강조 (네이버 흰 바탕에서 잘 보이는 주황)
SOFT: str = "#f3f7fc"
INK: str = "#1f2937"
MUTED: str = "#6b7280"

_FONT_CANDIDATES: dict[str, list[tuple[str, int]]] = {
    "bold": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1), ("C:/Windows/Fonts/malgunbd.ttf", 0)],
    "regular": [("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
                ("/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", 1), ("C:/Windows/Fonts/malgun.ttf", 0)],
}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    """한국어 글꼴을 찾아 연다. 없으면 명확한 오류로 멈춘다(네모 글자 이미지를 만들지 않도록)."""
    for path, index in _FONT_CANDIDATES[weight]:
        try:
            return ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
    raise FileNotFoundError(f"한국어 글꼴({weight})을 찾지 못했습니다 — Noto Sans CJK 또는 맑은 고딕 필요")


def _wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """글자 단위 줄바꿈(한국어는 어절 단위가 너무 성기다). 공백에서 끊을 수 있으면 공백에서 끊는다."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=f) <= width:
                cur += ch
                continue
            cut = cur.rfind(" ")
            if cut > len(cur) * 0.6:
                lines.append(cur[:cut])
                cur = cur[cut + 1:] + ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def thumbnail(out: Path, kicker: str, title: str, subtitle: str, preview: Path | None = None) -> None:
    """대표 이미지(첫 번째 사진 = 홈피드·검색 썸네일). 1080×1080, 글자는 크게·짧게."""
    W = H = 1080
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    if preview and preview.exists():
        pv = Image.open(preview).convert("RGB")
        pv = pv.resize((520, int(pv.height * 520 / pv.width)))
        pv = pv.crop((0, 0, 520, 600)).rotate(-6, expand=True, fillcolor=NAVY)
        im.paste(pv, (560, 470))
    d.rounded_rectangle((80, 110, 80 + d.textlength(kicker, font=font(34, "bold")) + 48, 170), 30, fill=ACCENT)
    d.text((104, 116), kicker, font=font(34, "bold"), fill="white")
    y = 220
    for line in _wrap(d, title, font(96, "bold"), 900):
        d.text((80, y), line, font=font(96, "bold"), fill="white")
        y += 122
    y += 16
    for line in _wrap(d, subtitle, font(40), 520 if preview else 900):
        d.text((80, y), line, font=font(40), fill="#c7d5e8")
        y += 58
    im.save(out, optimize=True)


@dataclass
class Marker:
    no: int
    x: int          # 원본 미리보기 이미지 좌표(px)
    y: int
    label: str = ""
    box: tuple[int, int, int, int] | None = None   # 강조 테두리 (x0, y0, x1, y1)


def annotate(out: Path, preview: Path, markers: list[Marker], caption: str) -> None:
    """작성 예시 이미지에 번호 원·강조 테두리를 얹는다. 좌우 여백을 넓혀 번호가 칸을 가리지 않게 한다."""
    pv = Image.open(preview).convert("RGB")
    pad_x, pad_top, pad_bottom = 70, 30, 80
    W, H = pv.width + pad_x * 2, pv.height + pad_top + pad_bottom
    im = Image.new("RGB", (W, H), "white")
    im.paste(pv, (pad_x, pad_top))
    d = ImageDraw.Draw(im)
    d.rectangle((pad_x - 1, pad_top - 1, pad_x + pv.width, pad_top + pv.height), outline="#b3c1d4", width=2)
    fnum = font(24, "bold")
    for m in markers:
        if m.box:
            x0, y0, x1, y1 = m.box
            d.rectangle((pad_x + x0, pad_top + y0, pad_x + x1, pad_top + y1), outline=ACCENT, width=4)
        cx, cy, r = pad_x + m.x, pad_top + m.y, 20
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
        tw = d.textlength(str(m.no), font=fnum)
        d.text((cx - tw / 2, cy - 17), str(m.no), font=fnum, fill="white")
    d.text((pad_x, H - 58), caption, font=font(24), fill=MUTED)
    im.save(out, optimize=True)


def checklist(out: Path, title: str, items: list[str], footer: str = "") -> None:
    """체크리스트 카드. 모바일 폭에서 읽히도록 글자 38px 이상."""
    W = 1080
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f_item, f_title = font(40), font(58, "bold")
    rows = [_wrap(tmp, it, f_item, W - 260) for it in items]
    H = 230 + sum(len(r) * 58 + 44 for r in rows) + (90 if footer else 40)
    im = Image.new("RGB", (W, H), SOFT)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 16), fill=NAVY)
    d.text((80, 80), title, font=f_title, fill=NAVY)
    y = 200
    for lines in rows:
        d.rounded_rectangle((80, y + 6, 124, y + 50), 8, outline=ACCENT, width=5)
        d.line((91, y + 28, 101, y + 39, 116, y + 17), fill=ACCENT, width=6)
        for ln in lines:
            d.text((160, y), ln, font=f_item, fill=INK)
            y += 58
        y += 44
    if footer:
        d.text((80, H - 80), footer, font=font(30), fill=MUTED)
    im.save(out, optimize=True)


def compare(out: Path, title: str, left_head: str, right_head: str,
            rows: list[tuple[str, str]], note: str = "") -> None:
    """두 칸 비교 카드 (틀린 예 / 바른 예, A / B)."""
    W = 1080
    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    f = font(36)
    col = (W - 160 - 30) // 2
    wrapped = [(_wrap(tmp, a, f, col - 50), _wrap(tmp, b, f, col - 50)) for a, b in rows]
    body_h = sum(max(len(a), len(b)) * 52 + 50 for a, b in wrapped)
    H = 300 + body_h + (100 if note else 40)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.text((80, 70), title, font=font(54, "bold"), fill=NAVY)
    xl, xr, y = 80, 80 + col + 30, 180
    d.rounded_rectangle((xl, y, xl + col, y + 76), 12, fill="#fdecea")
    d.rounded_rectangle((xr, y, xr + col, y + 76), 12, fill="#e7f3ec")
    d.text((xl + 25, y + 16), left_head, font=font(36, "bold"), fill="#b42318")
    d.text((xr + 25, y + 16), right_head, font=font(36, "bold"), fill="#146c43")
    y += 106
    for a, b in wrapped:
        h = max(len(a), len(b)) * 52 + 26
        d.rounded_rectangle((xl, y, xl + col, y + h), 12, outline="#f5c2bd", width=3)
        d.rounded_rectangle((xr, y, xr + col, y + h), 12, outline="#b7dcc5", width=3)
        for i, ln in enumerate(a):
            d.text((xl + 25, y + 13 + i * 52), ln, font=f, fill=INK)
        for i, ln in enumerate(b):
            d.text((xr + 25, y + 13 + i * 52), ln, font=f, fill=INK)
        y += h + 24
    if note:
        d.text((80, H - 80), note, font=font(30), fill=MUTED)
    im.save(out, optimize=True)


if __name__ == "__main__":
    print("모듈입니다. 초안 스크립트에서 import 해 쓰십시오.", file=sys.stderr)
