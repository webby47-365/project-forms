"""전체 서식 병렬 빌드 드라이버.

`build_form.py` 는 순차 실행이라 서식이 200종을 넘으면 너무 오래 걸린다. 여기서는
명세를 N조각으로 나눠 프로세스 N개로 동시에 돌리고, 끝난 뒤 카탈로그 조각을 합친다.

주의 (지난 세션에서 실제로 겪은 사고):
  - 조각 카탈로그를 **빈 파일로 시작하면 created_at·downloads 가 초기화**된다.
    그래서 기존 catalog.json 을 각 조각의 출발점으로 복사해 둔다.
  - 합칠 때는 **각 조각이 담당한 id만** 그 조각에서 가져온다. 조각마다 들어 있는
    나머지 항목(출발점으로 복사된 것)은 무시해야 최신 결과가 덮이지 않는다.
  - LibreOffice 는 프로세스별 사용자 프로필이 필요하다. build_form.py 가 PID로
    프로필을 분리하므로 별도 처리는 필요 없다.

사용법:
    python scripts/build_all_parallel.py            # 전체
    python scripts/build_all_parallel.py --jobs 8
    python scripts/build_all_parallel.py --only a b c
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
CATALOG = ROOT / "catalog" / "catalog.json"
FRAG_DIR = ROOT / "catalog" / "_frag"
LOG_DIR = ROOT / "logs"


def chunk(items: list[str], n: int) -> list[list[str]]:
    """리스트를 n조각으로 고르게 나눈다."""
    out: list[list[str]] = [[] for _ in range(n)]
    for i, it in enumerate(items):
        out[i % n].append(it)
    return [c for c in out if c]


def main() -> int:
    """엔트리포인트."""
    ap = argparse.ArgumentParser(description="전체 서식 병렬 빌드")
    ap.add_argument("--jobs", type=int, default=8, help="동시 실행 프로세스 수")
    ap.add_argument("--only", nargs="*", default=None, help="이 id만 빌드")
    args = ap.parse_args()

    ids = args.only or sorted(p.stem for p in SPECS.glob("*.yaml"))
    if not ids:
        print("[오류] 빌드할 명세가 없습니다.")
        return 1

    FRAG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for old in FRAG_DIR.glob("*.json"):
        old.unlink()

    seed = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else '{"forms": []}'
    groups = chunk(ids, args.jobs)

    procs: list[tuple[subprocess.Popen[str], Path, list[str], Path]] = []
    for i, grp in enumerate(groups):
        frag = FRAG_DIR / f"frag_{i}.json"
        frag.write_text(seed, encoding="utf-8")  # created_at·downloads 보존용 출발점
        log = LOG_DIR / f"build_{i}.log"
        cmd = [sys.executable, str(ROOT / "scripts" / "build_form.py"),
               *grp, "--catalog", str(frag)]
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdout=log.open("w", encoding="utf-8"),
            stderr=subprocess.STDOUT, text=True)
        procs.append((proc, frag, grp, log))

    print(f"[병렬빌드] 서식 {len(ids)}종을 프로세스 {len(procs)}개로 나눠 시작")
    started = time.time()
    failed = 0
    for proc, _frag, grp, log in procs:
        rc = proc.wait()
        if rc != 0:
            failed += 1
            print(f"  [실패] {log.name} (종료코드 {rc}, 담당 {len(grp)}종)")

    # 조각 합치기 — 각 조각이 담당한 id만 그 조각에서 가져온다
    merged: dict[str, dict] = {}
    if CATALOG.exists():
        for item in json.loads(CATALOG.read_text(encoding="utf-8")).get("forms", []):
            merged[item["id"]] = item
    for _proc, frag, grp, _log in procs:
        if not frag.exists():
            continue
        data = {f["id"]: f for f in json.loads(frag.read_text(encoding="utf-8")).get("forms", [])}
        for fid in grp:
            if fid in data:
                merged[fid] = data[fid]

    # 명세가 사라진 항목(고아)은 카탈로그에서 제거한다
    alive = {p.stem for p in SPECS.glob("*.yaml")}
    merged = {k: v for k, v in merged.items() if k in alive}

    payload = {
        "generated_at": json.loads(
            (FRAG_DIR / "frag_0.json").read_text(encoding="utf-8")).get("generated_at", ""),
        "count": len(merged),
        "forms": [merged[k] for k in sorted(merged)],
    }
    CATALOG.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    warn = sum(len(v.get("warnings") or []) for v in merged.values())
    sample = sum(1 for v in merged.values() if v.get("sample_preview"))
    mins = (time.time() - started) / 60
    print(f"[병렬빌드] 완료 — 카탈로그 {len(merged)}종 · 예시 미리보기 {sample}종 · "
          f"경고 {warn}건 · 실패 프로세스 {failed}개 · {mins:.1f}분")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
