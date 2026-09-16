"""법정서식 재현본 원문 대조 검사: 원문 PDF 글자가 생성 PDF 에 빠짐없이 들어갔는지 본다.

글자 순서는 표 배치에 따라 달라질 수 있으므로 원문 줄마다 2자 조각을 세어 생성본에 들어 있는 비율을 본다.
절반 이상 빠진 원문 줄은 '누락 의심 줄'로 보고한다.

사용법:
    python scripts/qa_gov_compare.py <원문.pdf> <생성.pdf>
    python scripts/qa_gov_compare.py --batch work/public/pdf  public/files   # id 이름이 같은 파일끼리
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_KEEP = re.compile(r"[^0-9A-Za-z가-힣]")
# 원문에만 있는 인쇄 표기·쪽 표기는 비교에서 뺀다
_IGNORE = re.compile(r"\d{3}\s*mm\s*[×x]\s*\d{3}\s*mm|\(\s*\d+\s*쪽\s*중\s*제?\s*\d+\s*쪽\s*\)|\d{3}\s*mm\s*[×x]\s*\d{3}\s*mm\s*\[[^\]]*\]|\((앞|뒤)\s*쪽\)|\d{5}-\d{5}\S*|\d{2}\.\d{1,2}\.\d{1,2}\s*승인|\((신문|인쇄|백상|중질)[^)]*\)")


def text_of(pdf: Path) -> str:
    try:
        out = subprocess.run(["pdftotext", "-q", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"{pdf.name}: pdftotext 실패 — {exc}") from exc
    return out


def _bigrams(line: str) -> list[str]:
    t = _KEEP.sub("", line)
    return [t[k:k + 2] for k in range(len(t) - 1)]


def compare(src: Path, out: Path) -> tuple[float, list[str]]:
    """원문 글자 2자 조각(줄 단위)이 생성본에 몇 % 들어 있는지와, 절반 이상 빠진 원문 줄을 돌려준다.

    표를 옮기면 읽는 순서가 바뀌므로 순서와 무관한 조각 개수로 센다.
    """
    from collections import Counter
    src_lines = [l for l in _IGNORE.sub("", text_of(src)).splitlines() if _KEEP.sub("", l)]
    out_count = Counter(g for l in text_of(out).replace("무료서식 다운로드", "").splitlines() for g in _bigrams(l))
    # 생성본은 칸 폭이 달라 줄이 다른 곳에서 꺾이므로, 줄 경계를 넘는 조각도 함께 센다
    flat = _KEEP.sub("", text_of(out))
    out_count.update(flat[k:k + 2] for k in range(len(flat) - 1))
    total = hit = 0
    lost: list[str] = []
    for line in src_lines:
        grams = _bigrams(line)
        if not grams:
            continue
        need = Counter(grams)
        got = sum(min(n, out_count.get(g, 0)) for g, n in need.items())
        total += len(grams)
        hit += got
        if got < len(grams) * 0.5 and len(grams) >= 4:
            lost.append(" ".join(line.split())[:40])
    return (hit / total if total else 1.0), lost


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--batch", action="store_true")
    ap.add_argument("--min", type=float, default=0.97, help="통과 기준 일치율")
    args = ap.parse_args(argv)
    pairs: list[tuple[str, Path, Path]] = []
    if args.batch:
        for src in sorted(args.a.glob("*.pdf")):
            out = args.b / src.stem / f"{src.stem}.pdf"
            if out.exists():
                pairs.append((src.stem, src, out))
    else:
        pairs.append((args.b.stem, args.a, args.b))
    bad = 0
    for name, src, out in pairs:
        try:
            cov, spans = compare(src, out)
        except RuntimeError as exc:
            print(f"[오류] {exc}")
            bad += 1
            continue
        ok = cov >= args.min
        bad += not ok
        print(f"[{'통과' if ok else '확인'}] {name}: 원문 글자 일치 {cov * 100:.1f}%"
              + ("" if not spans else " · 누락 의심 줄: " + " / ".join(spans[:6])))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
