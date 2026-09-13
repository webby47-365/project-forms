"""서식 제작 파이프라인: 명세(YAML) → DOCX·PDF·HWPX·미리보기(WebP) → 카탈로그 등록.

사용법:
    python scripts/build_form.py                 # specs 전체 빌드
    python scripts/build_form.py resume-basic    # 특정 서식만
    python scripts/build_form.py --force         # 변경 여부 무시하고 재생성
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import re
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from form_spec import MARGIN_MM, FormSpec, SpecError, load_all_specs, load_spec  # noqa: E402
from render_docx import render_docx  # noqa: E402
from render_hwpx import render_hwpx  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
MASTERS = ROOT / "masters"
FILES = ROOT / "public" / "files"
CATALOG = ROOT / "catalog" / "catalog.json"
KST = timezone(timedelta(hours=9))

MAX_FILE_BYTES = 1_048_576  # 서식 파일 1개당 1MB 상한
PREVIEW_WIDTH = 800
# 자동 맞춤 배율 (글자 크기는 유지하고 행 높이·문단 간격만 조절)
SHRINK_STEPS = (0.92, 0.85, 0.78, 0.72, 0.66)
MAX_SCALE = 1.6        # 확대 상한
FILL_TARGET = 0.93     # 목표 지면 채움 비율
MAX_EXPAND_TRIES = 4   # 확대 시도 횟수


class BuildError(RuntimeError):
    """빌드 단계 실패."""


def _now_kst() -> str:
    """KST 기준 ISO 시각 문자열."""
    return datetime.now(KST).replace(microsecond=0).isoformat()


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 180) -> str:
    """외부 명령 실행 후 표준출력을 반환한다."""
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True,
            text=True, timeout=timeout, check=True,
        )
    except FileNotFoundError as exc:
        raise BuildError(f"명령을 찾을 수 없습니다: {cmd[0]} — {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"명령 시간 초과({timeout}s): {' '.join(cmd)}") from exc
    except subprocess.CalledProcessError as exc:
        raise BuildError(f"명령 실패: {' '.join(cmd)}\n{exc.stderr[:800]}") from exc
    return proc.stdout


def _soffice() -> str:
    """LibreOffice 실행 파일 경로를 찾는다."""
    for cand in ("soffice", "libreoffice", r"C:\Program Files\LibreOffice\program\soffice.exe"):
        found = shutil.which(cand) or (cand if Path(cand).exists() else None)
        if found:
            return found
    raise BuildError("LibreOffice(soffice)를 찾을 수 없습니다. PDF 변환에 필요합니다.")


def docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    """DOCX → PDF 변환 (LibreOffice 헤드리스)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = Path(tempfile.gettempdir()) / f"lo_profile_{os.getpid()}"
    _run([_soffice(), f"-env:UserInstallation=file://{profile}",
          "--headless", "--norestore", "--convert-to", "pdf",
          "--outdir", str(out_dir), str(docx_path)], timeout=240)
    pdf = out_dir / f"{docx_path.stem}.pdf"
    if not pdf.exists():
        raise BuildError(f"PDF 생성 실패: {pdf}")
    return pdf


def pdf_page_count(pdf_path: Path) -> int:
    """PDF 페이지 수."""
    out = _run(["pdfinfo", str(pdf_path)])
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise BuildError(f"페이지 수를 읽을 수 없습니다: {pdf_path}")


def make_previews(pdf_path: Path, out_dir: Path, pages: int) -> list[str]:
    """PDF 각 페이지를 WebP 미리보기로 저장한다 (최대 2페이지)."""
    from PIL import Image  # 지연 임포트: Pillow는 미리보기에서만 필요

    limit = min(pages, 2)
    tmp = out_dir / "_tmp_preview"
    tmp.mkdir(parents=True, exist_ok=True)
    _run(["pdftoppm", "-png", "-r", "110", "-f", "1", "-l", str(limit),
          str(pdf_path), str(tmp / "p")])
    names: list[str] = []
    for idx, png in enumerate(sorted(tmp.glob("p-*.png")), start=1):
        with Image.open(png) as im:
            ratio = PREVIEW_WIDTH / im.width
            im = im.convert("RGB").resize(
                (PREVIEW_WIDTH, int(im.height * ratio)), Image.LANCZOS)
            target = out_dir / f"preview-{idx}.webp"
            im.save(target, "WEBP", quality=82, method=5)
        names.append(target.name)
    shutil.rmtree(tmp, ignore_errors=True)
    if not names:
        raise BuildError(f"미리보기 생성 실패: {pdf_path}")
    return names


def page_fill_ratio(pdf_path: Path) -> float:
    """마지막 페이지의 본문 영역 채움 비율(0~1)을 구한다.

    여백이 많이 남는 서식을 자동으로 확대하기 위한 근거값이다.
    """
    out = _run(["pdftotext", "-bbox", str(pdf_path), "-"])
    pages = out.split("<page")
    if len(pages) < 2:
        return 1.0
    last = pages[-1]
    heights = re.findall(r'height="([\d.]+)"', pages[1][:200])
    y_values = [float(v) for v in re.findall(r'yMax="([\d.]+)"', last)]
    if not heights or not y_values:
        return 1.0
    page_h = float(heights[0])
    margin_pt = MARGIN_MM * 72.0 / 25.4
    available = page_h - margin_pt * 2
    # 하단 출처 표기(푸터)는 아래쪽 여백 안에 있으므로 본문 높이 계산에서 제외한다
    body = [v for v in y_values if v <= page_h - margin_pt + 2]
    if not body:
        return 1.0
    used = max(body) - margin_pt
    if available <= 0:
        return 1.0
    return max(0.0, min(1.0, used / available))


def extract_pdf_text(pdf_path: Path) -> str:
    """PDF 텍스트 추출 (검수용).

    -layout은 표를 칸 위치대로 재배열하면서 셀 안에서 줄바꿈된 글자 사이에 옆 칸 글자를
    끼워 넣기 때문에 항목 존재 확인에 쓸 수 없다. 읽기 순서를 보존하는 -raw를 사용한다.
    """
    return _run(["pdftotext", "-raw", str(pdf_path), "-"])


def inspect_form(spec: FormSpec, pdf_path: Path, out_dir: Path) -> list[str]:
    """자동 검수. 경고 목록을 반환한다(빈 목록이면 통과)."""
    warnings: list[str] = []
    text = extract_pdf_text(pdf_path)

    # 1) 명세의 라벨/머리글이 실제 출력물에 존재하는지 확인
    required: list[str] = []
    for blk in spec.blocks:
        if blk["type"] == "grid":
            for row in blk["rows"]:
                required.extend([str(v) for v in row if str(v).strip()])
        elif blk["type"] == "table":
            required.extend([str(h) for h in blk["header"]])
        elif blk["type"] == "doc_title":
            required.append(str(blk["text"]))
    flat = "".join(text.split())
    for token in required:
        norm = "".join(token.split())
        # 빈칸 채우기용 자리표시자(밑줄·긴 공백·괄호 안내)는 줄바꿈으로 조각나므로 검사 제외
        if len(norm) > 24 or "    " in token:
            continue
        if norm and norm not in flat:
            warnings.append(f"출력물에서 '{token.strip()}' 항목을 찾을 수 없습니다.")

    # 2) 개인정보 과다수집 항목 차단
    for banned in ("주민등록번호", "주민번호"):
        if banned in flat:
            warnings.append(f"개인정보 과다수집 항목 '{banned}' 포함 — '생년월일' 등으로 대체 필요.")

    # 3) 파일 크기·존재 확인
    for name in (f"{spec.id}.pdf", f"{spec.id}.docx", f"{spec.id}.hwpx"):
        f = out_dir / name
        if not f.exists():
            warnings.append(f"파일 누락: {name}")
        elif f.stat().st_size > MAX_FILE_BYTES:
            warnings.append(f"파일 크기 초과({f.stat().st_size // 1024}KB): {name}")
    return warnings


def build_one(spec: FormSpec) -> dict[str, Any]:
    """서식 1종을 빌드하고 카탈로그 항목(dict)을 반환한다."""
    master_dir = MASTERS / spec.id
    out_dir = FILES / spec.id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 자동 맞춤: 목표 페이지를 넘치면 간격을 줄이고, 여백이 많이 남으면 넓혀 지면을 채운다.
    # (글자 크기는 건드리지 않으므로 가독성은 그대로 유지된다)
    target = spec.pages_hint

    def attempt(sc: float) -> tuple[Path, Path, int]:
        dm = render_docx(spec, master_dir / f"{spec.id}.docx", scale=sc)
        pf = docx_to_pdf(dm, out_dir)
        return dm, pf, pdf_page_count(pf)

    scale = 1.0
    docx_master, pdf, pages = attempt(scale)

    if pages > target:
        for step in SHRINK_STEPS:
            docx_master, pdf, pages = attempt(step)
            if pages <= target:
                scale = step
                print(f"  [자동맞춤] 간격 {int(step * 100)}%로 축소하여 {pages}페이지 수납")
                break
        else:
            print(f"  [경고] {target}페이지 목표를 달성하지 못했습니다 (현재 {pages}페이지). "
                  f"명세의 empty_rows를 줄이거나 target_pages를 조정하십시오.")
            scale = SHRINK_STEPS[-1]
    else:
        # 여백이 남으면 채움 비율을 보며 단계적으로 확대한다. 행 높이·간격만 커지고
        # 글자 크기는 그대로이므로 확대분은 그대로 '쓸 공간'이 된다.
        fill = page_fill_ratio(pdf)
        start_fill = fill
        for _ in range(MAX_EXPAND_TRIES):
            if fill >= FILL_TARGET:
                break
            cand = min(MAX_SCALE, scale * (FILL_TARGET / max(fill, 0.3)) ** 0.75)
            if cand <= scale * 1.02:
                break
            d2, p2, pg2 = attempt(cand)
            if pg2 > target:
                break
            scale, docx_master, pdf, pages = cand, d2, p2, pg2
            fill = page_fill_ratio(pdf)
        if scale > 1.02:
            print(f"  [자동맞춤] 여백이 남아 간격 {int(scale * 100)}%로 확대 "
                  f"(채움 {int(start_fill * 100)}% → {int(fill * 100)}%)")
        elif pages == target:
            # 확대 시도 후 마지막 렌더가 목표를 넘긴 경우 1.0으로 되돌린다
            docx_master, pdf, pages = attempt(1.0)

    shutil.copy2(docx_master, out_dir / f"{spec.id}.docx")
    render_hwpx(spec, out_dir / f"{spec.id}.hwpx", scale=scale)

    warnings: list[str] = []

    # 미리보기: 명세에 예시값이 있으면 '작성 예시' 판을 한 번 더 렌더링해서 그 화면을 쓴다.
    # 레이아웃은 빈 양식과 동일하고 칸 안의 글자만 채워지므로 페이지 수가 달라지지 않는다.
    # 다운로드되는 PDF·DOCX·HWPX는 위에서 만든 빈 양식 그대로다.
    sample_used = False
    if spec.has_sample:
        sample_dir = out_dir / "_sample"
        try:
            # 예시값이 들어가면 칸 안에서 줄바꿈이 생겨 빈 양식보다 자리를 더 쓴다.
            # 같은 배율로 넘치면 예시판만 한 단계씩 줄여 맞춘다(다운로드 파일은 영향 없음).
            # 미리보기는 앞 2페이지까지만 쓰므로, 2페이지 이상 서식은 예시판이 한 장
            # 더 밀려도 보이는 화면이 달라지지 않는다. 1페이지 서식만 엄격히 맞춘다.
            allowed = pages if pages < 2 else pages + 1
            for sc in (scale, *[s * scale for s in SHRINK_STEPS]):
                sample_docx = render_docx(
                    spec, master_dir / f"{spec.id}-sample.docx", scale=sc, sample=True)
                sample_dir.mkdir(parents=True, exist_ok=True)
                sample_pdf = docx_to_pdf(sample_docx, sample_dir)
                if pdf_page_count(sample_pdf) <= allowed:
                    previews = make_previews(sample_pdf, out_dir, pages)
                    sample_used = True
                    break
            else:
                warnings.append(
                    "예시 미리보기가 목표 페이지를 넘겨 빈 양식 화면을 사용했습니다 "
                    "— sample_text/sample_rows의 글자 수를 줄이십시오.")
        except BuildError as exc:
            warnings.append(f"예시 미리보기 생성 실패 — {exc}")
        finally:
            shutil.rmtree(sample_dir, ignore_errors=True)
    if not sample_used:
        previews = make_previews(pdf, out_dir, pages)

    warnings += inspect_form(spec, pdf, out_dir)
    for w in warnings:
        print(f"  [경고] {spec.id}: {w}")

    sizes = {
        ext: (out_dir / f"{spec.id}.{ext}").stat().st_size
        for ext in ("pdf", "docx", "hwpx")
    }
    return {
        "id": spec.id,
        "title": spec.title,
        "category": spec.category,
        "subcategory": spec.subcategory,
        "tags": spec.tags,
        "summary": spec.summary,
        "usage": spec.usage,
        "formats": ["pdf", "docx", "hwpx"],
        "file_sizes": sizes,
        "pages": pages,
        "previews": previews,
        "sample_preview": sample_used,
        "series": spec.series,
        "series_name": spec.series_name,
        "variant": spec.variant,
        "variant_rank": spec.variant_rank,
        "featured": spec.featured,
        "featured_rank": spec.featured_rank,
        "version": spec.version,
        "source": spec.source,
        "source_note": spec.source_note,
        "created_by": spec.created_by,
        "status": spec.status,
        "warnings": warnings,
    }


def load_catalog() -> dict[str, dict[str, Any]]:
    """기존 카탈로그를 id → 항목 매핑으로 읽는다."""
    if not CATALOG.exists():
        return {}
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BuildError(f"catalog.json 파싱 실패 — {exc}") from exc
    return {item["id"]: item for item in data.get("forms", [])}


def save_catalog(entries: dict[str, dict[str, Any]]) -> None:
    """카탈로그를 id 순으로 저장한다."""
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _now_kst(),
        "count": len(entries),
        "forms": [entries[k] for k in sorted(entries)],
    }
    CATALOG.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    """엔트리포인트."""
    ap = argparse.ArgumentParser(description="서식 빌드 파이프라인")
    ap.add_argument("ids", nargs="*", help="빌드할 서식 ID (생략 시 전체)")
    ap.add_argument("--force", action="store_true", help="변경 여부 무시하고 재생성")
    ap.add_argument("--catalog", default=None,
                    help="카탈로그 파일 경로 재지정 (병렬 빌드 시 조각 파일로 나눠 쓰기 위함)")
    args = ap.parse_args()

    global CATALOG
    if args.catalog:
        CATALOG = Path(args.catalog)

    try:
        specs = (
            [load_spec(SPECS / f"{i}.yaml") for i in args.ids]
            if args.ids else load_all_specs(SPECS)
        )
    except SpecError as exc:
        print(f"[오류] 명세 검증 실패: {exc}")
        return 1

    catalog = load_catalog()
    ok, failed, total_warn = 0, 0, 0
    for spec in specs:
        print(f"[빌드] {spec.id} — {spec.title}")
        try:
            entry = build_one(spec)
        except (BuildError, SpecError, OSError) as exc:
            print(f"  [실패] {spec.id}: {exc}")
            failed += 1
            continue
        prev = catalog.get(spec.id, {})
        entry["created_at"] = prev.get("created_at", _now_kst())
        entry["updated_at"] = _now_kst()
        entry["downloads"] = prev.get("downloads", 0)
        catalog[spec.id] = entry
        save_catalog(catalog)  # 중단되어도 진행분이 남도록 서식마다 저장
        total_warn += len(entry["warnings"])
        ok += 1
        kb = {k: v // 1024 for k, v in entry["file_sizes"].items()}
        print(f"  [완료] {entry['pages']}p / PDF {kb['pdf']}KB "
              f"DOCX {kb['docx']}KB HWPX {kb['hwpx']}KB")

    save_catalog(catalog)
    print(f"\n결과: 성공 {ok} / 실패 {failed} / 경고 {total_warn}건 · 카탈로그 {len(catalog)}종")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
