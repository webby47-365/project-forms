"""명세의 '글' 부분만 카탈로그에 반영한다 (파일 재생성 없음).

작성 순서(howto)·자주 묻는 질문(faq)·요약처럼 화면에 나가는 글만 고쳤을 때
PDF·DOCX·HWPX를 다시 만들 이유가 없다. 이 스크립트는 specs/*.yaml을 다시 읽어
catalog.json의 해당 항목만 갱신하므로 235종 기준 1초면 끝난다.

레이아웃(blocks)을 고쳤다면 이 스크립트로는 반영되지 않는다 — build_form.py를 쓴다.

사용법:
    python scripts/sync_meta.py            # 전체
    python scripts/sync_meta.py resume-basic
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from form_spec import SpecError, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
CATALOG = ROOT / "catalog" / "catalog.json"

# 렌더링과 무관한 '글·분류' 필드만 동기화한다.
# 파일 크기·페이지 수·미리보기 목록은 렌더링 결과이므로 건드리지 않는다.
# outline은 blocks에서 뽑은 항목 목차다. blocks를 고친 뒤 이 스크립트만 돌리면
# 목차는 새 내용, 실제 파일은 옛 내용이 되므로 그때는 build_form.py를 써야 한다.
META_FIELDS = (
    "title", "category", "subcategory", "tags", "summary", "usage",
    "series", "series_name", "variant", "variant_rank", "variant_use",
    "howto", "faq", "outline", "seal", "related", "from_request", "featured", "featured_rank", "source", "source_note", "law_ref", "status",
)


class SyncError(RuntimeError):
    """동기화 실패."""


def sync(form_ids: list[str]) -> tuple[int, int]:
    """카탈로그의 글 필드를 명세와 맞춘다. (갱신 건수, 변경된 건수)를 반환한다."""
    try:
        catalog: dict[str, Any] = json.loads(CATALOG.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SyncError(f"catalog.json이 없습니다: {CATALOG}") from exc
    except json.JSONDecodeError as exc:
        raise SyncError(f"catalog.json 파싱 실패 — {exc}") from exc

    entries = {f["id"]: f for f in catalog.get("forms", [])}
    paths = ([SPECS / f"{i}.yaml" for i in form_ids] if form_ids
             else sorted(SPECS.glob("*.yaml")))

    done = changed = 0
    missing: list[str] = []
    for path in paths:
        if not path.exists():
            raise SyncError(f"명세가 없습니다: {path.name}")
        try:
            spec = load_spec(path)
        except SpecError as exc:
            raise SyncError(str(exc)) from exc

        entry = entries.get(spec.id)
        if entry is None:
            # 아직 한 번도 빌드하지 않은 서식. 파일이 없으므로 여기서 만들 수 없다.
            missing.append(spec.id)
            continue

        before = {k: entry.get(k) for k in META_FIELDS}
        for key in META_FIELDS:
            entry[key] = getattr(spec, key)
        done += 1
        if any(before[k] != entry[k] for k in META_FIELDS):
            changed += 1

    CATALOG.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    if missing:
        print(f"[건너뜀] 카탈로그에 없는 서식 {len(missing)}종 — build_form.py로 먼저 생성: "
              f"{', '.join(missing[:5])}{' 외' if len(missing) > 5 else ''}")
    return done, changed


def main() -> int:
    """엔트리포인트."""
    try:
        done, changed = sync(sys.argv[1:])
    except SyncError as exc:
        print(f"[오류] {exc}")
        return 1
    print(f"[동기화] {done}종 확인 · {changed}종 갱신 — 이어서 python scripts/build_site.py 를 실행하십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
