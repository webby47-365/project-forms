"""직장인 계산 엔진의 파이썬 판 — 정적 페이지(연봉별 실수령액·퇴직금)를 빌드할 때 쓴다.

정본은 브라우저 계산기 assets/calc.js 다. 이 파일은 그 계산을 **한 줄씩 그대로 옮긴 것**이며,
정적 페이지 숫자와 계산기 숫자가 1원이라도 다르면 방문자가 바로 알아본다.
그래서 scripts/check_pay_calc.py 가 Node 로 calc.js 를 돌려 두 결과를 대조한다.
calc.js 의 산식을 고치면 이 파일도 같이 고치고 대조 검사를 돌릴 것.

요율은 catalog/rates_2026.json, 간이세액표는 catalog/tax_table_2026.json 을 그대로 받는다.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from typing import Any

# 기본세율 (과세표준 상한, 세율, 누진공제) — calc.js TAX_BRACKETS 와 같다
TAX_BRACKETS: list[tuple[float, float, int]] = [
    (14_000_000, 0.06, 0), (50_000_000, 0.15, 1_260_000), (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000), (300_000_000, 0.38, 19_940_000), (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000), (math.inf, 0.45, 65_940_000),
]


def floor_unit(n: float, unit: int = 10) -> int:
    """10원 미만 절사. 부동소수점 오차(29,699.999…) 보정은 calc.js 와 같이 +1e-6."""
    return int(math.floor((n + 1e-6) / unit) * unit)


def insurance(taxable: float, rates: dict[str, Any]) -> dict[str, Any]:
    """근로자 부담 4대보험료 (산재는 사업주 전액 부담이라 제외)."""
    t = max(0.0, taxable)
    if t <= 0:
        return {"pension": 0, "health": 0, "care": 0, "employment": 0, "total": 0, "pension_capped": False}
    np_ = rates["national_pension"]
    base = min(max(t, np_["base_min"]), np_["base_max"])
    pension = floor_unit(base * np_["rate_employee"])
    health = floor_unit(t * rates["health"]["rate_employee"])
    care = floor_unit(health * rates["long_term_care"]["rate_of_health"])
    employment = floor_unit(t * rates["employment"]["rate_employee"])
    return {"pension": pension, "health": health, "care": care, "employment": employment,
            "pension_capped": t > np_["base_max"],
            "total": pension + health + care + employment}


def progressive_tax(base: float) -> float:
    """기본세율로 산출세액을 구한다."""
    if base <= 0:
        return 0.0
    for limit, rate, minus in TAX_BRACKETS:
        if base <= limit:
            return base * rate - minus
    return 0.0


def child_credit_monthly(children: int, rates: dict[str, Any]) -> int:
    """8~20세 자녀 세액공제 — 간이세액표에서 빼는 월 금액."""
    c = rates["income_tax"]["child_credit_monthly"]
    if children <= 0:
        return 0
    if children == 1:
        return int(c["1"])
    if children == 2:
        return int(c["2"])
    return int(c["2"] + (children - 2) * c["3plus_add"])


def lookup_table(t: float, fam: int, table: dict[str, Any]) -> float:
    """간이세액표 조회. 월 1,000만원 초과는 별표2 고액급여 산식."""
    col = min(fam, table.get("family_max", 11)) - 1
    rows: list[list[int]] = table["rows"]
    if t < table["min"]:
        return 0.0
    if t <= table["max"]:
        bounds: list[int] | None = table.get("bounds")
        if bounds and len(bounds) == len(rows):
            i = max(0, bisect_right(bounds, t) - 1)
        else:
            i = min(int((t - table["min"]) // table["step"]), len(rows) - 1)
        return float(rows[i][col] or 0)
    top = float(rows[-1][col] or 0)
    x = t
    if x <= 14_000_000:
        return top + (x - 10_000_000) * 0.98 * 0.35 + 25_000
    if x <= 28_000_000:
        return top + 1_397_000 + (x - 14_000_000) * 0.98 * 0.38
    if x <= 30_000_000:
        return top + 6_610_600 + (x - 28_000_000) * 0.98 * 0.40
    if x <= 45_000_000:
        return top + 7_394_600 + (x - 30_000_000) * 0.40
    if x <= 87_000_000:
        return top + 13_394_600 + (x - 45_000_000) * 0.42
    return top + 31_034_600 + (x - 87_000_000) * 0.45


def income_tax(taxable: float, family: int, children: int,
               table: dict[str, Any], rates: dict[str, Any]) -> dict[str, int]:
    """간이세액표 기준 월 소득세·지방소득세. 정적 페이지는 표가 있을 때만 만든다(근사 산식 없음)."""
    t = max(0.0, taxable)
    fam = min(max(round(family) or 1, 1), 11)
    kid = max(0, round(children) or 0)
    if t <= 0:
        return {"tax": 0, "local": 0}
    tax = lookup_table(t, fam, table)
    tax = max(0.0, tax - child_credit_monthly(kid, rates))
    tax_i = floor_unit(tax)
    return {"tax": tax_i, "local": floor_unit(tax_i * rates["income_tax"]["local_rate"])}


def salary(annual: int, tax_free: int, family: int, children: int,
           table: dict[str, Any], rates: dict[str, Any]) -> dict[str, Any]:
    """연봉 기준 월 실수령액. calc.js salary({mode:'year'}) 와 같다."""
    gross = math.floor(max(0, annual) / 12)          # 연봉 ÷ 12 내림 (급여대장 관행)
    free = max(0, min(tax_free, gross))
    taxable = gross - free
    ins = insurance(taxable, rates)
    tax = income_tax(taxable, family, children, table, rates)
    deduct = ins["total"] + tax["tax"] + tax["local"]
    net = gross - deduct
    return {"gross": gross, "tax_free": free, "taxable": taxable,
            "pension": ins["pension"], "health": ins["health"], "care": ins["care"],
            "employment": ins["employment"], "pension_capped": ins["pension_capped"],
            "tax": tax["tax"], "local": tax["local"],
            "deduct": deduct, "net": net, "net_year": net * 12, "gross_year": annual}


def service_deduction(years: int) -> int:
    """근속연수공제 (소득세법 제48조 제1항)."""
    if years <= 5:
        return 1_000_000 * years
    if years <= 10:
        return 5_000_000 + 2_000_000 * (years - 5)
    if years <= 20:
        return 15_000_000 + 2_500_000 * (years - 10)
    return 40_000_000 + 3_000_000 * (years - 20)


def converted_deduction(converted: float) -> float:
    """환산급여공제 (소득세법 제48조 제3항)."""
    if converted <= 8_000_000:
        return converted
    if converted <= 70_000_000:
        return 8_000_000 + (converted - 8_000_000) * 0.6
    if converted <= 100_000_000:
        return 45_200_000 + (converted - 70_000_000) * 0.55
    if converted <= 300_000_000:
        return 61_700_000 + (converted - 100_000_000) * 0.45
    return 151_700_000 + (converted - 300_000_000) * 0.35


def retirement_tax(payout: int, years: int, rates: dict[str, Any]) -> dict[str, Any]:
    """퇴직소득세(연분연승법). calc.js retirementTax({years}) 와 같다."""
    years = max(1, int(years))
    svc = service_deduction(years)
    after = max(0, payout - svc)
    converted = after * 12 / years
    conv_ded = converted_deduction(converted)
    base = max(0.0, converted - conv_ded)
    conv_tax = progressive_tax(base)
    tax = math.floor(conv_tax * years / 12)
    if payout <= svc:
        tax = 0
    local = math.floor(tax * rates["income_tax"]["local_rate"])
    total = tax + local
    return {"payout": payout, "years": years, "svc_deduct": svc, "converted": converted,
            "conv_deduct": conv_ded, "base": base, "tax": tax, "local": local,
            "total": total, "net": payout - total,
            "rate": (total / payout * 100) if payout > 0 else 0.0}


def severance_estimate(annual: int, years: int) -> int:
    """연봉만 알 때의 법정 퇴직금 추정치.

    법정 퇴직금 = 1일 평균임금 × 30 × 재직일수/365. 상여·수당 변동이 없고 연봉을 12개월에
    고르게 받는다고 보면 30일분 평균임금 ≈ 월급(연봉 ÷ 12)이므로 '연봉 × 근속연수 ÷ 12'(= 월급 × 근속연수, 원 미만 버림)로 근사한다.
    정확한 금액은 퇴직금 계산기(달 경계 일수 반영)로 안내한다 — 페이지에 '추정'이라고 적는다.
    """
    return math.floor(max(0, annual) * max(0, years) / 12)
