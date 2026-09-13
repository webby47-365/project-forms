"""목표 페이지 수를 넘긴 서식의 입력행 수를 줄여 자동으로 맞추는 보정 도구.

build_form.py의 자동 맞춤(간격 조절)만으로 해결되지 않을 때 사용한다.
명세의 empty_rows를 단계적으로 줄이며 다시 빌드하고, 목표 페이지에 들어가면 멈춘다.

사용법:
    python scripts/fit_one_page.py payslip work-journal
    python scripts/fit_one_page.py --all        # 카탈로그에서 초과분을 찾아 전부 보정
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_form  # noqa: E402
from build_form import BuildError, build_one, load_catalog, save_catalog  # noqa: E402
from form_spec import SpecError, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
CATALOG = ROOT / "catalog" / "catalog.json"

MIN_EMPTY_ROWS = 2      # 이 아래로는 줄이지 않는다 (표의 쓸모가 없어짐)
MIN_TEXTBOX_MM = 14     # 자유기술란 최소 높이
MAX_ROUNDS = 10


def _reduce_largest_empty_rows(text: str) -> tuple[str, int, int] | None:
    """가장 큰 empty_rows 값을 2 줄인 명세 텍스트를 반환한다.

    Returns:
        (수정된 텍스트, 이전 값, 새 값) 또는 더 줄일 수 없으면 None.
    """
    matches = list(re.finditer(r"(empty_rows:\s*)(\d+)", text))
    if not matches:
        return None
    target = max(matches, key=lambda m: int(m.group(2)))
    old = int(target.group(2))
    new = old - 2
    if new < MIN_EMPTY_ROWS:
        return None
    updated = text[:target.start(2)] + str(new) + text[target.end(2):]
    return updated, old, new


def _reduce_largest_textbox(text: str) -> tuple[str, int, int] | None:
    """가장 큰 textbox height_mm 값을 4 줄인 명세 텍스트를 반환한다."""
    matches = list(re.finditer(r"(height_mm:\s*)(\d+)", text))
    if not matches:
        return None
    target = max(matches, key=lambda m: int(m.group(2)))
    old = int(target.group(2))
    new = old - 4
    if new < MIN_TEXTBOX_MM:
        return None
    updated = text[:target.start(2)] + str(new) + text[target.end(2):]
    return updated, old, new


def _shrink(text: str) -> tuple[str, str] | None:
    """입력행 → 자유기술란 순서로 줄일 수 있는 것을 찾아 줄인다."""
    reduced = _reduce_largest_empty_rows(text)
    if reduced is not None:
        t, old, new = reduced
        return t, f"empty_rows {old} → {new}"
    reduced = _reduce_largest_textbox(text)
    if reduced is not None:
        t, old, new = reduced
        return t, f"height_mm {old} → {new}"
    return None


def fit(form_id: str) -> bool:
    """서식 1종을 목표 페이지에 맞춘다. 성공 여부를 반환한다."""
    path = SPECS / f"{form_id}.yaml"
    if not path.exists():
        print(f"[없음] {form_id}.yaml")
        return False

    catalog = load_catalog()
    for round_no in range(1, MAX_ROUNDS + 1):
        try:
            spec = load_spec(path)
            entry = build_one(spec)
        except (SpecError, BuildError, OSError) as exc:
            print(f"[실패] {form_id}: {exc}")
            return False

        prev = catalog.get(form_id, {})
        entry["created_at"] = prev.get("created_at", entry.get("updated_at", ""))
        entry["downloads"] = prev.get("downloads", 0)
        catalog[form_id] = entry
        save_catalog(catalog)

        if entry["pages"] <= spec.pages_hint:
            print(f"[완료] {form_id} — {entry['pages']}페이지 (보정 {round_no - 1}회)")
            return True

        reduced = _shrink(path.read_text(encoding="utf-8"))
        if reduced is None:
            print(f"[한계] {form_id} — 더 줄일 여지가 없습니다 "
                  f"(현재 {entry['pages']}페이지). target_pages를 {entry['pages']}로 "
                  f"올리거나 명세 구성을 손봐야 합니다.")
            return False
        text, what = reduced
        path.write_text(text, encoding="utf-8")
        print(f"  [보정 {round_no}] {form_id}: {what}")
    print(f"[한계] {form_id} — {MAX_ROUNDS}회 보정 후에도 초과")
    return False


def main() -> int:
    """엔트리포인트."""
    ap = argparse.ArgumentParser(description="페이지 수 초과 서식 자동 보정")
    ap.add_argument("ids", nargs="*", help="보정할 서식 ID")
    ap.add_argument("--all", action="store_true",
                    help="카탈로그에서 목표 페이지를 넘긴 서식을 모두 찾아 보정")
    ap.add_argument("--catalog", default=None,
                    help="카탈로그 파일 경로 재지정 (병렬 보정 시 조각 파일로 나눠 쓰기 위함)")
    args = ap.parse_args()

    global CATALOG
    if args.catalog:
        CATALOG = Path(args.catalog)
        build_form.CATALOG = CATALOG

    ids = list(args.ids)
    if args.all:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for item in data["forms"]:
            spec = load_spec(SPECS / f"{item['id']}.yaml")
            if item["pages"] > spec.pages_hint and item["id"] not in ids:
                ids.append(item["id"])
    if not ids:
        print("보정할 서식이 없습니다.")
        return 0

    ok = sum(1 for i in ids if fit(i))
    print(f"\n보정 대상 {len(ids)}건 / 성공 {ok}건")
    return 0 if ok == len(ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
