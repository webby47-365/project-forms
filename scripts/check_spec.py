"""명세 문법·스키마 검사 (렌더링 없이 빠르게 확인).

사용법:
    python scripts/check_spec.py                  # specs 전체 검사
    python scripts/check_spec.py meeting-minutes  # 특정 서식만
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from form_spec import SpecError, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
CATEGORIES = ROOT / "catalog" / "categories.json"


def _valid_keys() -> dict[str, set[str]]:
    """categories.json에서 (대분류 key → 중분류 key 집합)을 읽는다."""
    data = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    return {
        c["key"]: {s["key"] for s in c["subcategories"]}
        for c in data["categories"]
    }


def check_one(path: Path, keys: dict[str, set[str]]) -> list[str]:
    """명세 1개를 검사하고 문제 목록을 반환한다 (빈 목록이면 통과)."""
    problems: list[str] = []
    try:
        spec = load_spec(path)
    except SpecError as exc:
        return [str(exc)]

    if spec.category not in keys:
        problems.append(f"알 수 없는 category: {spec.category} (가능: {', '.join(sorted(keys))})")
    elif spec.subcategory not in keys[spec.category]:
        problems.append(
            f"'{spec.category}'에 없는 subcategory: {spec.subcategory} "
            f"(가능: {', '.join(sorted(keys[spec.category]))})"
        )

    if len(spec.tags) < 3:
        problems.append("tags를 3개 이상 넣으십시오 (검색 유입에 사용됩니다).")
    if len(spec.summary) < 20:
        problems.append("summary가 너무 짧습니다 (20자 이상).")
    if len(spec.usage) < 60:
        problems.append("usage가 너무 짧습니다 (60자 이상, 실제 사용 상황과 주의사항 포함).")

    has_title = any(b["type"] == "doc_title" for b in spec.blocks)
    if not has_title:
        problems.append("doc_title 블록이 없습니다.")

    for idx, blk in enumerate(spec.blocks):
        if blk["type"] == "grid":
            widths = blk.get("widths")
            rows = blk.get("rows")
            if not rows:
                problems.append(f"blocks[{idx}] grid에 rows가 없습니다.")
                continue
            n = len(rows[0])
            if widths and len(widths) != n:
                problems.append(f"blocks[{idx}] grid: widths {len(widths)}개 ≠ 셀 {n}개")
            if widths and abs(sum(widths) - 100) > 0.5:
                problems.append(f"blocks[{idx}] grid: widths 합이 {sum(widths)} (100이어야 함)")
            for r, row in enumerate(rows):
                if len(row) != n:
                    problems.append(f"blocks[{idx}] grid rows[{r}]: 셀 {len(row)}개 ≠ {n}개")
            for m_i, merge in enumerate(blk.get("merges", [])):
                if len(merge) != 4:
                    problems.append(f"blocks[{idx}] merges[{m_i}]는 [행,열,행,열] 4개여야 합니다.")
                    continue
                r1, c1, r2, c2 = merge
                if not (0 <= r1 <= r2 < len(rows)):
                    problems.append(
                        f"blocks[{idx}] merges[{m_i}]: 행 범위 {r1}~{r2}가 표를 벗어났습니다 "
                        f"(행은 0~{len(rows) - 1})."
                    )
                if not (0 <= c1 <= c2 < n):
                    problems.append(
                        f"blocks[{idx}] merges[{m_i}]: 열 범위 {c1}~{c2}가 표를 벗어났습니다 "
                        f"(열은 0~{n - 1})."
                    )
        elif blk["type"] == "table":
            header = blk.get("header")
            if not header:
                problems.append(f"blocks[{idx}] table에 header가 없습니다.")
                continue
            widths = blk.get("widths")
            if widths and len(widths) != len(header):
                problems.append(f"blocks[{idx}] table: widths {len(widths)}개 ≠ header {len(header)}개")
            if widths and abs(sum(widths) - 100) > 0.5:
                problems.append(f"blocks[{idx}] table: widths 합이 {sum(widths)} (100이어야 함)")
            if len(header) == 1:
                problems.append(
                    f"blocks[{idx}] table: 단일 칸 표는 자유기술란으로 보입니다 — textbox를 사용하십시오."
                )
    return problems


def main() -> int:
    """엔트리포인트."""
    keys = _valid_keys()
    targets = (
        [SPECS / f"{a}.yaml" for a in sys.argv[1:]]
        if len(sys.argv) > 1 else sorted(SPECS.glob("*.yaml"))
    )
    bad = 0
    for path in targets:
        if not path.exists():
            print(f"[없음] {path.name}")
            bad += 1
            continue
        problems = check_one(path, keys)
        if problems:
            bad += 1
            print(f"[문제] {path.name}")
            for p in problems:
                print(f"   - {p}")
        else:
            print(f"[통과] {path.name}")
    print(f"\n검사 {len(targets)}건 / 문제 {bad}건")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
