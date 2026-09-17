"""생성된 서식을 한글 카테고리 폴더로 내보낸다 (사람이 찾아보기 쉽게).

  C:\\New_Business\\01.FreeForms\\기업\\인사·노무\\사직서.pdf / .docx / .hwpx

주의: 이 폴더는 **내보내기 결과**이며 정본이 아니다.
정본은 `specs/*.yaml`(설계)과 `public/files/`(배포본)이다.
서식을 수정할 때는 명세를 고치고 build_form.py를 다시 실행한 뒤 이 도구를 실행한다.

사용법:
    python scripts/export_to_folders.py            # 변경분만 복사
    python scripts/export_to_folders.py --clean    # 고아 파일 정리까지 수행
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "public" / "files"
CATALOG = ROOT / "catalog" / "catalog.json"
CATEGORIES = ROOT / "catalog" / "categories.json"

EXTS = ("pdf", "docx", "hwpx")
# Windows 파일명에 쓸 수 없는 문자
BAD_CHARS = '\\/:*?"<>|'


class ExportError(RuntimeError):
    """내보내기 실패."""


def safe_name(title: str) -> str:
    """서식명을 Windows 파일명으로 쓸 수 있게 정리한다."""
    name = title
    for ch in BAD_CHARS:
        name = name.replace(ch, "_")
    return name.strip().rstrip(".")


def folder_map() -> dict[str, tuple[str, str]]:
    """'대분류키/중분류키' → (대분류 폴더명, 중분류 폴더명) 매핑."""
    data = json.loads(CATEGORIES.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, str]] = {}
    for c in data["categories"]:
        for s in c["subcategories"]:
            out[f"{c['key']}/{s['key']}"] = (c["folder"], s["folder"])
    return out


def export(clean: bool) -> tuple[int, int]:
    """서식을 카테고리 폴더로 복사한다. (복사한 파일 수, 정리한 파일 수)를 반환한다."""
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExportError("catalog.json이 없습니다. build_form.py를 먼저 실행하십시오.") from exc

    fmap = folder_map()
    expected: set[Path] = set()
    copied = 0

    for item in catalog["forms"]:
        if item.get("status", "published") != "published":
            continue
        key = f"{item['category']}/{item['subcategory']}"
        if key not in fmap:
            raise ExportError(f"{item['id']}: categories.json에 없는 분류 '{key}'")
        big, small = fmap[key]
        dest_dir = ROOT / big / small
        dest_dir.mkdir(parents=True, exist_ok=True)
        base = safe_name(item["title"])

        for ext in EXTS:
            src = FILES / item["id"] / f"{item['id']}.{ext}"
            if not src.exists():
                print(f"  [건너뜀] {item['id']}.{ext} 없음 — build_form.py를 실행하십시오.")
                continue
            dest = dest_dir / f"{base}.{ext}"
            expected.add(dest)
            if (not dest.exists()
                    or dest.stat().st_mtime < src.stat().st_mtime
                    or dest.stat().st_size != src.stat().st_size):
                shutil.copy2(src, dest)
                copied += 1

    removed = 0
    if clean:
        for big, small in set(fmap.values()):
            d = ROOT / big / small
            if not d.exists():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix.lstrip(".") in EXTS and f not in expected:
                    f.unlink()
                    removed += 1
                    print(f"  [정리] {big}/{small}/{f.name}")

    return copied, removed


def main() -> int:
    """엔트리포인트."""
    ap = argparse.ArgumentParser(description="서식을 한글 카테고리 폴더로 내보내기")
    ap.add_argument("--clean", action="store_true",
                    help="카탈로그에 없는 서식 파일을 폴더에서 삭제")
    args = ap.parse_args()

    try:
        copied, removed = export(args.clean)
    except ExportError as exc:
        print(f"[오류] {exc}")
        return 1
    print(f"[내보내기] 복사 {copied}개 / 정리 {removed}개 — 카테고리 폴더 갱신 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
