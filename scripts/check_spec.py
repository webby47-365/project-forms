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


# 상세 화면 본문의 가독성 상한. 화면에서 훑어 읽는 글이므로 길어지면 아무도 안 읽는다.
HOWTO_MIN_STEPS, HOWTO_MAX_STEPS = 3, 5
HOWTO_MAX_CHARS = 60      # 한 단계 = 한 문장
FAQ_MIN, FAQ_MAX = 2, 4
FAQ_Q_MAX, FAQ_A_MAX = 34, 140
VARIANT_USE_MAX = 40


def _check_readable(spec) -> list[str]:  # noqa: ANN001 (FormSpec)
    """howto·faq·variant_use의 분량 규칙 검사.

    값이 없으면 검사하지 않는다(아직 안 채운 명세는 문제로 잡지 않는다).
    값이 있으면 화면에서 읽기 좋은 길이인지 확인한다 — SPEC_GUIDE 3-2절 규칙.
    """
    out: list[str] = []
    if spec.howto:
        if not HOWTO_MIN_STEPS <= len(spec.howto) <= HOWTO_MAX_STEPS:
            out.append(
                f"howto는 {HOWTO_MIN_STEPS}~{HOWTO_MAX_STEPS}단계로 (현재 {len(spec.howto)}단계).")
        for i, step in enumerate(spec.howto):
            if len(step) > HOWTO_MAX_CHARS:
                out.append(f"howto[{i}]가 {len(step)}자입니다 — {HOWTO_MAX_CHARS}자 이내 한 문장으로.")
            # 마침표 개수로만 문장 수를 센다. '~마다', '~한다 '처럼 문장 중간에 오는 '다 '를
            # 문장 경계로 보면 멀쩡한 우리말을 억지로 고치게 되므로 세지 않는다.
            if step.count(".") > 1:
                out.append(f"howto[{i}]에 문장이 둘 이상으로 보입니다 — 단계를 나누십시오.")
    if spec.faq:
        if not FAQ_MIN <= len(spec.faq) <= FAQ_MAX:
            out.append(f"faq는 {FAQ_MIN}~{FAQ_MAX}문항으로 (현재 {len(spec.faq)}문항).")
        for i, item in enumerate(spec.faq):
            if len(item["q"]) > FAQ_Q_MAX:
                out.append(f"faq[{i}].q가 {len(item['q'])}자입니다 — {FAQ_Q_MAX}자 이내로.")
            if not item["q"].endswith("?"):
                out.append(f"faq[{i}].q는 물음표로 끝나야 합니다.")
            if len(item["a"]) > FAQ_A_MAX:
                out.append(f"faq[{i}].a가 {len(item['a'])}자입니다 — {FAQ_A_MAX}자 이내로.")
    if spec.variant_use and len(spec.variant_use) > VARIANT_USE_MAX:
        out.append(
            f"variant_use가 {len(spec.variant_use)}자입니다 — {VARIANT_USE_MAX}자 이내 한 줄로.")
    return out


def content_todo(spec) -> list[str]:  # noqa: ANN001 (FormSpec)
    """아직 채우지 않은 본문 항목을 권고로 알린다 (문제 아님, 종료코드에 반영하지 않음)."""
    todo: list[str] = []
    if not spec.howto:
        todo.append("howto 미작성 — 상세 화면 '작성 순서'가 비어 있습니다.")
    if not spec.faq:
        todo.append("faq 미작성 — 상세 화면 '자주 묻는 질문'이 비어 있습니다.")
    if spec.series and not spec.variant_use:
        todo.append("variant_use 미작성 — 계열 비교표의 '이럴 때 쓰세요'가 비어 있습니다.")
    return todo


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

    problems.extend(_check_readable(spec))

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
            # 미리보기 예시값 검사 — 모양이 rows와 같아야 예시가 엉뚱한 칸에 들어가지 않는다
            srows = blk.get("sample_rows")
            if srows is not None:
                if not isinstance(srows, list):
                    problems.append(f"blocks[{idx}] grid: sample_rows는 목록이어야 합니다.")
                else:
                    if len(srows) > len(rows):
                        problems.append(
                            f"blocks[{idx}] grid: sample_rows {len(srows)}행 > rows {len(rows)}행")
                    for r, srow in enumerate(srows):
                        if not isinstance(srow, list) or len(srow) != n:
                            problems.append(
                                f"blocks[{idx}] grid sample_rows[{r}]: 셀 개수가 {n}개가 아닙니다.")
            pc = blk.get("photo_cell")
            if pc is not None:
                if not (isinstance(pc, list) and len(pc) == 2):
                    problems.append(f"blocks[{idx}] grid: photo_cell은 [행, 열] 2개여야 합니다.")
                elif not (0 <= pc[0] < len(rows) and 0 <= pc[1] < n):
                    problems.append(
                        f"blocks[{idx}] grid: photo_cell {pc}이 표({len(rows)}x{n}) 범위를 벗어났습니다.")
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
            srows = blk.get("sample_rows")
            if srows is not None:
                n_empty = int(blk.get("empty_rows", 3))
                if not isinstance(srows, list):
                    problems.append(f"blocks[{idx}] table: sample_rows는 목록이어야 합니다.")
                else:
                    if len(srows) > n_empty:
                        problems.append(
                            f"blocks[{idx}] table: sample_rows {len(srows)}행 > empty_rows {n_empty}행 "
                            f"— 초과분은 버려집니다.")
                    for r, srow in enumerate(srows):
                        if not isinstance(srow, list) or len(srow) != len(header):
                            problems.append(
                                f"blocks[{idx}] table sample_rows[{r}]: "
                                f"셀 개수가 header {len(header)}개와 다릅니다.")
        elif blk["type"] == "textbox":
            stext = str(blk.get("sample_text", ""))
            if stext:
                # 박스 높이 대비 글자가 많으면 예시가 넘쳐 페이지 수가 늘어난다
                budget = int(float(blk.get("height_mm", 30)) * 8)
                if len(stext) > budget:
                    problems.append(
                        f"blocks[{idx}] textbox: sample_text가 {len(stext)}자로 박스 높이"
                        f"({blk.get('height_mm', 30)}mm)에 비해 깁니다 — {budget}자 이하로 줄이십시오.")
    return problems


def main() -> int:
    """엔트리포인트."""
    keys = _valid_keys()
    targets = (
        [SPECS / f"{a}.yaml" for a in sys.argv[1:]]
        if len(sys.argv) > 1 else sorted(SPECS.glob("*.yaml"))
    )
    bad = 0
    todo_count = 0
    show_todo = len(targets) <= 20  # 전체 검사에서는 권고를 건별로 찍지 않고 건수만 센다
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
        try:
            todo = content_todo(load_spec(path))
        except SpecError:
            todo = []
        if todo:
            todo_count += 1
            if show_todo:
                for t in todo:
                    print(f"   · (권고) {t}")
    tail = f" / 본문 미작성 {todo_count}건" if todo_count else ""
    print(f"\n검사 {len(targets)}건 / 문제 {bad}건{tail}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
