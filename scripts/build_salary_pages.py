"""연봉별 실수령액·퇴직금 정적 페이지 생성기 — build_site.py 가 불러 쓴다.

/tools/salary/<만원>/      연봉 N만원 실수령액 + 공제 내역 + 가족 수별 + 퇴직금 추정 (131개)
/tools/severance/<근속>/   근속 N년 퇴직금 — 월급 구간별 퇴직금·퇴직소득세·실수령 표 (30개)
허브는 따로 두지 않는다. 실수령액 계산기(/tools/salary/) 하단의 전체 표가 131개로 가는 길이다.

왜 정적 페이지인가: "연봉 3000 실수령액" 같은 검색어는 금액마다 따로 검색된다. 계산기 한 페이지로는
이 검색어들을 받을 수 없고, 검색엔진·AI 검색은 자바스크립트 계산 결과를 읽지 않는다.
그래서 빌드할 때 계산해 **숫자가 박힌 HTML** 로 낸다.

숫자는 scripts/pay_calc.py 가 계산한다(assets/calc.js 와 원 단위 일치 — check_pay_calc.py 로 대조).
요율·간이세액표가 바뀌면 다음 빌드에서 전 페이지가 자동으로 새 값으로 바뀐다. 손댈 곳이 없다.

얇은 페이지 방지: 금액만 바꾼 복제 페이지가 되지 않도록 페이지마다 계산으로만 나오는 고유 정보
(가족 수별 표·주변 연봉 대비 증가분·국민연금 상한 도달 여부·세율 구간·근속 6개 구간 퇴직금)를 넣는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pay_calc

# 페이지를 만들 연봉(만원). 2,000만~1억 5,000만원을 100만원 간격으로 (검색어가 100만원 단위로 갈린다)
SALARY_STEPS_MAN: list[int] = list(range(2000, 15001, 100))

# 페이지 기본 가정 — 사람인·잡코리아 계산기 기본값과 같게 두어 비교할 때 혼란이 없게 한다
DEFAULT_TAX_FREE = 200_000
DEFAULT_FAMILY = 1
SEVERANCE_YEARS: list[int] = [1, 3, 5, 10, 20, 30]   # 연봉 페이지의 퇴직금 표
SEVERANCE_PAGE_YEARS: list[int] = list(range(1, 31))  # 근속연수별 퇴직금 페이지
# 근속연수 페이지의 월급 구간(세전 월급, 원)
SEVERANCE_WAGES: list[int] = list(range(2_000_000, 10_000_001, 500_000)) + [12_000_000, 15_000_000]
RELATED_IDS: list[str] = ["payslip", "labor-contract-standard", "employment-certificate",
                          "career-certificate", "resignation-letter"]


def won(n: float) -> str:
    """1234567 → '1,234,567'"""
    return f"{int(round(n)):,}"


def man(n: float) -> str:
    """원 → 읽기 쉬운 한국식 표기. 2,457,630 → '245만 7,630원', 30,000,000 → '3,000만원'."""
    v = int(round(n))
    if abs(v) < 10_000:
        return f"{v:,}원"
    m, r = divmod(abs(v), 10_000)
    sign = "-" if v < 0 else ""
    return f"{sign}{m:,}만 {r:,}원" if r else f"{sign}{m:,}만원"


def man_label(man_value: int) -> str:
    """연봉(만원 단위 정수) → '3,000만원', '1억 500만원'."""
    eok, rest = divmod(man_value, 10_000)
    if not eok:
        return f"{rest:,}만원"
    return f"{eok}억 {rest:,}만원" if rest else f"{eok}억원"


def marginal_rate(annual: int) -> str:
    """연봉 수준에서 대략 걸리는 소득세 세율 구간(설명용). 과표 = 총급여 − 근로소득공제 − 인적공제 1명."""
    g = annual - DEFAULT_TAX_FREE * 12
    if g <= 5_000_000:
        ded = g * 0.7
    elif g <= 15_000_000:
        ded = 3_500_000 + (g - 5_000_000) * 0.4
    elif g <= 45_000_000:
        ded = 7_500_000 + (g - 15_000_000) * 0.15
    elif g <= 100_000_000:
        ded = 12_000_000 + (g - 45_000_000) * 0.05
    else:
        ded = 14_750_000 + (g - 100_000_000) * 0.02
    base = g - min(ded, 20_000_000) - 1_500_000
    for limit, rate, _ in pay_calc.TAX_BRACKETS:
        if base <= limit:
            return f"{int(rate * 100)}%"
    return "45%"


def salary_rows(rates: dict[str, Any], table: dict[str, Any]) -> list[dict[str, Any]]:
    """131개 연봉의 요약 행. 계산기 페이지 하단 전체 표와 각 페이지의 '주변 연봉'이 함께 쓴다."""
    rows: list[dict[str, Any]] = []
    for mv in SALARY_STEPS_MAN:
        r = pay_calc.salary(mv * 10_000, DEFAULT_TAX_FREE, DEFAULT_FAMILY, 0, table, rates)
        rows.append({"man": mv, "label": man_label(mv), "path": f"/tools/salary/{mv}/",
                     "band": mv // 1000 * 1000 if mv < 10000 else (10000 if mv < 12500 else 12500),
                     "net": r["net"], "net_year": r["net_year"], "deduct": r["deduct"],
                     "rate": r["deduct"] / r["gross"] * 100 if r["gross"] else 0.0})
    return rows


def load_table(rates: dict[str, Any], table_path: Path) -> dict[str, Any] | None:
    """간이세액표를 읽는다. 요율·표 중 하나라도 없으면 None (그 경우 페이지를 만들지 않는다)."""
    if not rates or not table_path.exists():
        return None
    try:
        return json.loads(table_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[사이트] 알림: 간이세액표를 읽지 못해 연봉별·근속별 페이지를 건너뜁니다 — {exc}")
        return None


def build_salary_pages(
    *,
    public: Path,
    env: Any,
    common: dict[str, Any],
    rates: dict[str, Any],
    table: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    dl_map: dict[str, Any],
    name_map: dict[str, Any],
    write: Callable[[Path, str], None],
    jd: Callable[[Any], str],
    breadcrumb_ld: Callable[[list[tuple[str, str]]], str],
    site_name: str,
) -> tuple[int, list[tuple[str, str, str]]]:
    """연봉별 131개 + 근속별 30개 페이지를 쓰고 (페이지 수, 사이트맵 항목)을 돌려준다."""
    year = rates.get("year", 2026)
    lastmod = str(rates.get("updated", ""))[:10] or common["updated"]
    tpl = env.get_template("salary.html")
    related = [by_id[i] for i in RELATED_IDS if i in by_id]
    np_max = rates["national_pension"]["base_max"]

    def calc(annual: int, family: int = DEFAULT_FAMILY, kids: int = 0,
             free: int = DEFAULT_TAX_FREE) -> dict[str, Any]:
        return pay_calc.salary(annual, free, family, kids, table, rates)

    rows = salary_rows(rates, table)
    row_by_man = {x["man"]: x for x in rows}
    pages = 0
    urls: list[tuple[str, str, str]] = []

    for idx, mv in enumerate(SALARY_STEPS_MAN):
        annual = mv * 10_000
        label = man_label(mv)
        r = calc(annual)
        no_free = calc(annual, free=0)
        rate = r["deduct"] / r["gross"] * 100 if r["gross"] else 0.0

        family_rows = []
        for fam, kids in [(1, 0), (2, 0), (3, 0), (3, 1), (4, 0), (4, 2)]:
            fr = calc(annual, family=fam, kids=kids)
            family_rows.append({"label": f"{fam}명" + (f" (자녀 {kids}명)" if kids else ""),
                                "tax": fr["tax"] + fr["local"], "net": fr["net"],
                                "diff": fr["net"] - r["net"]})

        # 주변 연봉 — 앞뒤 3칸. 100만원 오를 때 실수령이 얼마 느는지가 페이지마다 다른 정보다.
        neighbors = []
        for j in range(max(0, idx - 3), min(len(SALARY_STEPS_MAN), idx + 4)):
            nm = SALARY_STEPS_MAN[j]
            nr = row_by_man[nm]
            neighbors.append({**nr, "cur": nm == mv, "diff": nr["net"] - r["net"]})
        step_up = next((x for x in neighbors if x["man"] > mv), None)
        raise_note = ""
        if step_up:
            gain_gross = (step_up["man"] - mv) * 10_000 / 12
            gain_net = step_up["net"] - r["net"]
            raise_note = (f"연봉이 {man_label(step_up['man'] - mv)} 오르면 월급(세전)은 {man(gain_gross)} 늘지만 "
                          f"실수령액은 {man(gain_net)} 늘어납니다. 늘어난 금액의 약 "
                          f"{(1 - gain_net / gain_gross) * 100:.0f}%가 보험료·세금으로 빠집니다.")

        sev_rows = []
        for y in SEVERANCE_YEARS:
            pay = pay_calc.severance_estimate(annual, y)
            rt = pay_calc.retirement_tax(pay, y, rates)
            sev_rows.append({"years": y, "pay": pay, "tax": rt["total"], "net": rt["net"],
                             "rate": rt["rate"], "link": f"/tools/severance/{y}/"})

        notes: list[str] = []
        if r["pension_capped"]:
            notes.append(f"월 과세 급여 {man(r['taxable'])}이 국민연금 기준소득월액 상한({man(np_max)})을 넘어, "
                         f"국민연금은 상한액 기준 {man(r['pension'])}으로 고정됩니다. 이 구간부터는 연봉이 올라도 "
                         f"국민연금이 더 늘지 않습니다.")
        else:
            left = (np_max + DEFAULT_TAX_FREE) * 12 - annual
            if 0 < left <= 30_000_000:
                notes.append(f"연봉이 {man((np_max + DEFAULT_TAX_FREE) * 12)}을 넘으면 국민연금이 기준소득월액 "
                             f"상한({man(np_max)})에 걸려 더 늘지 않습니다.")
        notes.append(f"이 연봉대의 소득세는 대체로 {marginal_rate(annual)} 세율 구간에 걸립니다(부양가족 1명·"
                     f"다른 공제 없음 기준). 실제 세금은 연말정산에서 카드·보험·의료비 공제를 반영해 확정됩니다.")

        summary = (f"{year}년 기준 연봉 {label}의 월 실수령액은 {man(r['net'])}입니다"
                   f"(비과세 식대 월 20만원·부양가족 1명). 월급 {man(r['gross'])}에서 4대보험 "
                   f"{man(r['pension'] + r['health'] + r['care'] + r['employment'])}과 소득세·지방소득세 "
                   f"{man(r['tax'] + r['local'])}, 합계 {man(r['deduct'])}({rate:.1f}%)이 빠지고, "
                   f"1년 실수령액은 {man(r['net_year'])}입니다.")

        faq = [
            {"q": f"연봉 {label} 월급 실수령액은 얼마인가요?", "a": summary},
            {"q": f"연봉 {label}에서 식대 비과세가 없으면요?",
             "a": (f"비과세가 없으면 월 실수령액은 {man(no_free['net'])}으로, 식대 20만원을 비과세로 받을 때보다 "
                   f"{man(r['net'] - no_free['net'])} 적습니다. 같은 연봉이라도 비과세 항목을 얼마나 두느냐에 "
                   f"따라 실수령액이 달라집니다.")},
            {"q": f"연봉 {label}로 10년 일하면 퇴직금은 얼마인가요?",
             "a": (lambda s10: f"연봉을 12개월 고르게 받고 상여가 없다고 보면 법정 퇴직금은 약 {man(s10['pay'])}이고, "
                   f"퇴직소득세·지방소득세 {man(s10['tax'])}을 빼면 약 {man(s10['net'])}을 받습니다. "
                   f"정확한 금액은 퇴직 전 3개월 임금으로 계산해야 합니다.")(
                       next(x for x in sev_rows if x["years"] == 10))},
        ]

        prev_row = row_by_man[SALARY_STEPS_MAN[idx - 1]] if idx > 0 else None
        next_row = row_by_man[SALARY_STEPS_MAN[idx + 1]] if idx + 1 < len(SALARY_STEPS_MAN) else None
        path = f"/tools/salary/{mv}/"
        calc_link = f"/tools/salary/?amount={annual}&free={DEFAULT_TAX_FREE}&family={DEFAULT_FAMILY}"

        write(public / "tools" / "salary" / str(mv) / "index.html", tpl.render(
            mode="detail",
            page_title=f"연봉 {label} 실수령액 월 {man(r['net'])} — 4대보험·세금·퇴직금 ({year}년) | {site_name}",
            page_desc=(f"연봉 {label} 월 실수령액 {man(r['net'])}, 연 {man(r['net_year'])}. 국민연금·건강보험·"
                       f"고용보험·소득세 공제 내역과 부양가족 수별 실수령액, 근속연수별 퇴직금까지 {year}년 "
                       f"요율과 국세청 간이세액표로 계산했습니다."),
            canonical=path,
            breadcrumb_jsonld=breadcrumb_ld([("홈", "/"), ("직장인 도구", "/tools/"),
                                             ("실수령액 계산기", "/tools/salary/"), (f"연봉 {label}", path)]),
            faq_jsonld=jd({
                "@context": "https://schema.org", "@type": "FAQPage",
                "mainEntity": [{"@type": "Question", "name": x["q"],
                                "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq],
            }),
            year=year, label=label, annual=annual, r=r, rate=rate, no_free=no_free,
            summary=summary, family_rows=family_rows, neighbors=neighbors, raise_note=raise_note,
            sev_rows=sev_rows, notes=notes, faq=faq, prev_row=prev_row, next_row=next_row,
            calc_link=calc_link, related=related, won=won, man=man, rates=rates,
            dl_map=dl_map, name_map=name_map, **common,
        ))
        pages += 1
        urls.append((path, lastmod, "0.6"))

    # ── 근속연수별 퇴직금 페이지 /tools/severance/<y>/ ──
    for y in SEVERANCE_PAGE_YEARS:
        svc = pay_calc.service_deduction(y)
        wage_rows = []
        for w in SEVERANCE_WAGES:
            pay = w * y
            rt = pay_calc.retirement_tax(pay, y, rates)
            wage_rows.append({"wage": w, "annual_man": w * 12 // 10_000, "pay": pay, "tax": rt["tax"],
                              "local": rt["local"], "net": rt["net"], "rate": rt["rate"],
                              "salary_path": (f"/tools/salary/{w * 12 // 10_000}/"
                                              if (w * 12 // 10_000) in row_by_man else "")})
        ex = next(x for x in wage_rows if x["wage"] == 3_000_000)
        ex_rt = pay_calc.retirement_tax(ex["pay"], y, rates)
        summary = (f"월급 300만원(연봉 3,600만원)을 받으며 {y}년 일하고 퇴사하면 법정 퇴직금은 약 {man(ex['pay'])}이고, "
                   f"퇴직소득세 {man(ex['tax'])}과 지방소득세 {man(ex['local'])}을 빼면 {man(ex['net'])}을 받습니다"
                   f"(실효세율 {ex['rate']:.2f}%). 근속 {y}년의 근속연수공제는 {man(svc)}입니다.")
        steps = [
            ("퇴직금(세전)", ex["pay"]),
            (f"근속연수공제 ({y}년)", -svc),
            ("환산급여 (공제 후 ÷ 근속연수 × 12)", ex_rt["converted"]),
            ("환산급여공제", -ex_rt["conv_deduct"]),
            ("과세표준", ex_rt["base"]),
            ("퇴직소득세 (환산산출세액 ÷ 12 × 근속연수)", ex_rt["tax"]),
            ("지방소득세 (10%)", ex_rt["local"]),
        ]
        prev_y = y - 1 if y > 1 else None
        next_y = y + 1 if y < SEVERANCE_PAGE_YEARS[-1] else None
        faq = [
            {"q": f"{y}년 일하면 퇴직금은 얼마인가요?",
             "a": (f"법정 퇴직금은 30일분 평균임금 × 근속연수이므로 대략 '월급 × {y}'입니다. "
                   f"월급 250만원이면 약 {man(2_500_000 * y)}, 400만원이면 약 {man(4_000_000 * y)}입니다. "
                   f"상여금·연장수당이 있으면 평균임금이 올라가 더 많아집니다.")},
            {"q": f"근속 {y}년 퇴직금에 붙는 세금은?",
             "a": (f"근속연수공제 {man(svc)}을 먼저 빼고 연분연승법으로 계산합니다. 월급 300만원 기준 "
                   f"퇴직소득세와 지방소득세를 합쳐 {man(ex['tax'] + ex['local'])}으로, 퇴직금의 "
                   f"{ex['rate']:.2f}%입니다. IRP 계좌로 받으면 이 세금을 연금 수령 때까지 미룰 수 있습니다.")},
        ]
        path = f"/tools/severance/{y}/"
        write(public / "tools" / "severance" / str(y) / "index.html", tpl.render(
            mode="severance",
            page_title=f"근속 {y}년 퇴직금 계산 — 월급별 퇴직금·퇴직소득세·실수령액 표 ({year}년) | {site_name}",
            page_desc=(f"{y}년 일하고 퇴사할 때 받는 퇴직금을 월급 200만~1,500만원 구간별로 정리했습니다. "
                       f"근속연수공제 {man(svc)}을 반영한 퇴직소득세·지방소득세와 실수령 퇴직금까지 {year}년 "
                       f"세법 기준으로 계산했습니다."),
            canonical=path,
            breadcrumb_jsonld=breadcrumb_ld([("홈", "/"), ("직장인 도구", "/tools/"),
                                             ("퇴직금 계산기", "/tools/severance/"), (f"근속 {y}년 퇴직금", path)]),
            faq_jsonld=jd({
                "@context": "https://schema.org", "@type": "FAQPage",
                "mainEntity": [{"@type": "Question", "name": x["q"],
                                "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in faq],
            }),
            year=year, y=y, svc=svc, summary=summary, wage_rows=wage_rows, steps=steps, faq=faq,
            prev_y=prev_y, next_y=next_y, years_all=SEVERANCE_PAGE_YEARS,
            related=[by_id[i] for i in ["resignation-letter", "handover-report", "career-certificate",
                                         "certified-notice-wage", "asset-handover"] if i in by_id],
            won=won, man=man, rates=rates, dl_map=dl_map, name_map=name_map, **common,
        ))
        pages += 1
        urls.append((path, lastmod, "0.6"))

    return pages, urls
