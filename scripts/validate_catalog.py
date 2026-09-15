"""배포 전 최종 검증. 하나라도 실패하면 배포를 중단해야 한다.

검사 항목:
  1) 명세 스키마 (check_spec.py와 동일 기준)
  2) 카탈로그와 명세의 일치 (누락·고아 항목)
  3) 서식 파일 3형식 + 미리보기 실재 여부
  4) 파일 크기 상한
  5) 카테고리 키 유효성
  6) 대표 서식 개수와 순위 중복
  7) Cloudflare Pages 한도 (파일 수·파일당 크기)

사용법:
    python scripts/validate_catalog.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_spec import _valid_keys, check_one  # noqa: E402
from form_spec import SpecError, load_spec  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
PUBLIC = ROOT / "public"
FILES = PUBLIC / "files"
CATALOG = ROOT / "catalog" / "catalog.json"

MAX_FILE_BYTES = 1_048_576        # 서식 파일 1개당 1MB
CF_MAX_FILE_BYTES = 25 * 1024**2  # Cloudflare Pages 파일당 25MB
CF_MAX_FILES = 20_000             # Cloudflare Pages 사이트당 20,000개
FEATURED_COUNT = 10


def main() -> int:
    """엔트리포인트. 문제가 없으면 0을 반환한다."""
    errors: list[str] = []
    warns: list[str] = []
    keys = _valid_keys()

    # 1) 명세 스키마
    spec_ids: set[str] = set()
    for path in sorted(SPECS.glob("*.yaml")):
        spec_ids.add(path.stem)
        for p in check_one(path, keys):
            errors.append(f"명세 {path.name}: {p}")

    # 2) 카탈로그 일치
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print("[오류] catalog.json이 없습니다. build_form.py를 먼저 실행하십시오.")
        return 1
    except json.JSONDecodeError as exc:
        print(f"[오류] catalog.json 파싱 실패 — {exc}")
        return 1

    items = {f["id"]: f for f in catalog["forms"]}
    for missing in sorted(spec_ids - set(items)):
        errors.append(f"카탈로그 누락: {missing} — build_form.py {missing} 를 실행하십시오.")
    for orphan in sorted(set(items) - spec_ids):
        errors.append(f"명세 없는 카탈로그 항목(고아): {orphan} — 명세를 복구하거나 항목을 제거하십시오.")

    # 3~5) 파일 실재·크기·분류
    for form_id, item in sorted(items.items()):
        d = FILES / form_id
        for ext in ("pdf", "docx", "hwpx"):
            f = d / f"{form_id}.{ext}"
            if not f.exists():
                errors.append(f"{form_id}: 파일 누락 — {f.name}")
                continue
            size = f.stat().st_size
            if size > CF_MAX_FILE_BYTES:
                errors.append(f"{form_id}: {f.name} 이 Cloudflare 한도(25MB)를 초과했습니다.")
            elif size > MAX_FILE_BYTES:
                warns.append(f"{form_id}: {f.name} 크기 {size // 1024}KB (권장 1MB 이하)")
        previews = item.get("previews") or []
        if not previews:
            errors.append(f"{form_id}: 미리보기 이미지가 없습니다.")
        for p in previews:
            if not (d / p).exists():
                errors.append(f"{form_id}: 미리보기 파일 누락 — {p}")
        if len(previews) != min(item.get("pages", 1), 2):
            warns.append(f"{form_id}: 미리보기 {len(previews)}장 / 페이지 {item.get('pages')}장 "
                         f"— 불일치 여부를 확인하십시오.")
        key = f"{item['category']}/{item['subcategory']}"
        if item["category"] not in keys or item["subcategory"] not in keys.get(item["category"], ()):
            errors.append(f"{form_id}: categories.json에 없는 분류 '{key}'")
        if item.get("warnings"):
            for w in item["warnings"]:
                warns.append(f"{form_id}: 빌드 경고 — {w}")
        try:
            spec = load_spec(SPECS / f"{form_id}.yaml")
        except SpecError:
            continue  # 위에서 이미 보고됨
        # 목표보다 페이지가 늘어난 것은 배포를 막는다. 방문자가 받는 파일이 2장짜리가 되고
        # 미리보기도 함께 달라지므로 경고로 흘려보내면 안 된다.
        # (2026-09-15: 로컬 LibreOffice가 24.2→26.8로 올라가 이력서 4종이 2페이지가 된 채 배포됐다)
        if item.get("pages", 1) > spec.pages_hint:
            errors.append(f"{form_id}: 목표 {spec.pages_hint}페이지인데 {item['pages']}페이지입니다 "
                          f"— fit_one_page.py로 보정하거나 target_pages를 조정하십시오. "
                          f"빌드 환경(LibreOffice 버전)이 바뀌지 않았는지도 확인하십시오.")
        elif item.get("pages", 1) < spec.pages_hint:
            warns.append(f"{form_id}: 목표 {spec.pages_hint}페이지인데 {item['pages']}페이지입니다 "
                         f"— 내용이 줄지 않았는지 확인하십시오.")

    # 6) 대표 서식
    featured = [f for f in items.values() if f.get("featured")]
    if len(featured) != FEATURED_COUNT:
        errors.append(f"메인 노출(featured) 서식이 {len(featured)}종입니다 — {FEATURED_COUNT}종이어야 합니다.")
    ranks = [f.get("featured_rank", 99) for f in featured]
    if len(set(ranks)) != len(ranks):
        errors.append(f"featured_rank가 중복되었습니다: {sorted(ranks)}")

    # 7) Cloudflare 파일 수
    total_files = sum(1 for p in PUBLIC.rglob("*") if p.is_file())
    if total_files > CF_MAX_FILES:
        errors.append(f"public 폴더 파일 수 {total_files}개가 Cloudflare 한도({CF_MAX_FILES})를 넘었습니다.")
    elif total_files > CF_MAX_FILES * 0.8:
        warns.append(f"public 폴더 파일 수 {total_files}개 — Cloudflare 한도의 80%를 넘었습니다. "
                     f"파일을 R2로 이관할 시점입니다.")

    # 8) 정보형 가이드(guides/*.yaml) — 규칙 위반은 배포 중단. 빌드는 해당 가이드만 빼고 지나가므로
    #    여기서 막지 않으면 "글을 썼는데 사이트에 안 나오는" 상태로 조용히 배포된다.
    import guides as guide_mod  # noqa: PLC0415
    try:
        import build_site  # noqa: PLC0415
        tool_paths = {t["path"] for t in build_site.TOOLS} | {"/tools/"}
    except ImportError as exc:
        tool_paths = set()
        warns.append(f"도구 목록을 읽지 못해 가이드의 tools 검사를 건너뜁니다 — {exc}")
    guide_list, guide_errors = guide_mod.load_guides(set(items), tool_paths, strict=True)
    if not tool_paths:
        guide_errors = [e for e in guide_errors if "도구 경로" not in e]
    errors += guide_errors
    for g in guide_list:
        if not (PUBLIC / "guide" / g["slug"] / "index.html").exists():
            errors.append(f"[가이드] {g['slug']}: public/guide/{g['slug']}/ 가 없습니다 — build_site.py 를 먼저 실행하십시오.")

    # 9) 구조화 데이터(JSON-LD) 파싱 — 2026-09-14 이스케이프 사고(전 페이지 JSON-LD 무효) 재발 방지.
    #    사람 눈에는 멀쩡해 보이므로 반드시 파서로 확인한다.
    ld_re = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
    ld_blocks = 0
    for html_path in PUBLIC.rglob("*.html"):
        if "download" in html_path.parts:
            continue
        text = html_path.read_text(encoding="utf-8", errors="replace")
        for m in ld_re.finditer(text):
            body = m.group(1).strip()
            if not body:
                continue
            ld_blocks += 1
            try:
                json.loads(body)
            except json.JSONDecodeError as exc:
                errors.append(f"JSON-LD 파싱 실패: {html_path.relative_to(PUBLIC)} — {exc}")
                break

    # 결과 출력
    for w in warns:
        print(f"[경고] {w}")
    for e in errors:
        print(f"[오류] {e}")
    print(f"\n서식 {len(items)}종 · 가이드 {len(guide_list)}편 · JSON-LD {ld_blocks}블록 · 배포 파일 {total_files}개 · "
          f"경고 {len(warns)}건 · 오류 {len(errors)}건")
    if errors:
        print("→ 오류를 해결해야 배포할 수 있습니다.")
        return 1
    print("→ 검증 통과. 배포 가능합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
