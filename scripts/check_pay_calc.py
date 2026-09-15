"""pay_calc.py(빌드용 파이썬 판)와 assets/calc.js(브라우저 계산기)의 결과를 대조한다.

정적 페이지의 숫자와 계산기의 숫자가 다르면 신뢰가 무너진다. calc.js 또는 pay_calc.py 를
고친 뒤에는 반드시 돌린다. Node 가 없으면 건너뛰고 0으로 끝난다(일일 배포를 막지 않는다).

    python scripts/check_pay_calc.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pay_calc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

NODE_SCRIPT = r"""
const C = require(process.argv[2]);
const R = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
const T = JSON.parse(require('fs').readFileSync(process.argv[4], 'utf8'));
const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = { salary: [], rtax: [] };
for (const s of cases.salary) {
  const r = C.salary({ mode: 'year', amount: s[0], taxFree: s[1], family: s[2], children: s[3] }, T, R);
  out.salary.push([r.net, r.deduct, r.pension, r.health, r.care, r.employment, r.tax, r.local]);
}
for (const c of cases.rtax) {
  const r = C.retirementTax({ payout: c[0], years: c[1] }, R);
  out.rtax.push([r.tax, r.local, r.net]);
}
process.stdout.write(JSON.stringify(out));
"""


def main() -> int:
    """대조 실행. 불일치가 있으면 1."""
    node = shutil.which("node")
    if not node:
        print("[대조] Node 가 없어 건너뜁니다 (calc.js 와의 대조는 Node 가 있는 환경에서 돌리십시오).")
        return 0
    rates = json.loads((ROOT / "catalog" / "rates_2026.json").read_text(encoding="utf-8"))
    table_path = ROOT / "catalog" / "tax_table_2026.json"
    table = json.loads(table_path.read_text(encoding="utf-8"))

    # 연봉 1,000만~3억(10만원 간격 일부 포함) × 비과세 × 가족 × 자녀
    amounts = list(range(10_000_000, 150_000_001, 1_000_000)) + \
        [33_330_000, 41_999_999, 80_000_000 + 7, 200_000_000, 300_000_000]
    salary_cases = [[a, f, fam, kid] for a in amounts for f in (0, 200_000)
                    for fam in (1, 2, 3, 4) for kid in (0, 1, 2)]
    rtax_cases = [[p, y] for p in (3_000_000, 12_345_678, 50_000_000, 100_000_000, 350_000_000)
                  for y in range(1, 36)]

    with (Path(__file__).resolve().parent / "_check_pay_calc.js").open("w", encoding="utf-8") as fh:
        fh.write(NODE_SCRIPT)
    js = Path(__file__).resolve().parent / "_check_pay_calc.js"
    try:
        proc = subprocess.run(
            [node, str(js), str(ROOT / "assets" / "calc.js"),
             str(ROOT / "catalog" / "rates_2026.json"), str(table_path)],
            input=json.dumps({"salary": salary_cases, "rtax": rtax_cases}),
            capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    finally:
        js.unlink(missing_ok=True)
    if proc.returncode != 0:
        print(f"[대조] Node 실행 실패: {proc.stderr.strip()[:500]}")
        return 1
    js_out = json.loads(proc.stdout)

    bad = 0
    for case, jr in zip(salary_cases, js_out["salary"]):
        r = pay_calc.salary(case[0], case[1], case[2], case[3], table, rates)
        pr = [r["net"], r["deduct"], r["pension"], r["health"], r["care"],
              r["employment"], r["tax"], r["local"]]
        if pr != jr:
            bad += 1
            if bad <= 10:
                print(f"[불일치] 실수령액 {case}: py={pr} js={jr}")
    for case, jr in zip(rtax_cases, js_out["rtax"]):
        r = pay_calc.retirement_tax(case[0], case[1], rates)
        pr = [r["tax"], r["local"], r["net"]]
        if pr != jr:
            bad += 1
            if bad <= 10:
                print(f"[불일치] 퇴직소득세 {case}: py={pr} js={jr}")
    total = len(salary_cases) + len(rtax_cases)
    if bad:
        print(f"[대조] 실패 — {total}건 중 {bad}건 불일치")
        return 1
    print(f"[대조] 통과 — {total}건 모두 calc.js 와 원 단위까지 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
