/* 무료서식 다운로드 — 직장인 계산기 엔진 (퇴직금·연차·실수령액)
 *
 * 정적 호스팅이라 계산은 전부 이 파일 안에서 한다. 입력값은 서버로 전송하지 않는다.
 * 요율은 catalog/rates_2026.json → 페이지에 window.FF_RATES 로 심어져 들어온다.
 * 간이세액표는 public/assets/tax_table.json 을 필요할 때만 내려받는다(실수령액 페이지에서만).
 */
(function (global) {
  'use strict';

  /* ────────────────────────── 숫자·날짜 유틸 ────────────────────────── */

  /** "1,234,000원" 같은 입력에서 숫자만 뽑는다. 실패하면 0. */
  function num(v) {
    if (typeof v === 'number') return isFinite(v) ? v : 0;
    var s = String(v == null ? '' : v).replace(/[^0-9.-]/g, '');
    var n = parseFloat(s);
    return isFinite(n) ? n : 0;
  }

  /** 1234567 → "1,234,567" */
  function fmt(n) {
    var v = Math.round(num(n));
    var neg = v < 0;
    var s = String(Math.abs(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (neg ? '-' : '') + s;
  }

  /** 보험료·세액은 10원 미만을 버린다(공단·국세청 고지 방식). */
  function floorUnit(n, unit) {
    var u = unit || 10;
    // 부동소수점 오차로 29,700원이 29,699.999…가 되어 한 단위 내려가는 것을 막는다.
    return Math.floor((num(n) + 1e-6) / u) * u;
  }

  /** "2026-09-14" → Date(UTC 자정). 시간대 때문에 하루가 밀리는 것을 막는다. */
  function toDate(iso) {
    if (iso instanceof Date) return iso;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || '').trim());
    if (!m) return null;
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  }

  function toISO(d) {
    return d.toISOString().slice(0, 10);
  }

  var DAY = 86400000;

  /** 두 날짜 사이의 일수 (b - a). */
  function diffDays(a, b) {
    return Math.round((b.getTime() - a.getTime()) / DAY);
  }

  function addDays(d, n) {
    return new Date(d.getTime() + n * DAY);
  }

  /** 달을 더한다. 말일 보정: 1/31 + 1개월 = 2/28(29). */
  function addMonths(d, n) {
    var y = d.getUTCFullYear(), m = d.getUTCMonth(), day = d.getUTCDate();
    var t = new Date(Date.UTC(y, m + n, 1));
    var last = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth() + 1, 0)).getUTCDate();
    t.setUTCDate(Math.min(day, last));
    return t;
  }

  /** 그 달의 마지막 날. */
  function endOfMonth(d) {
    return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  }

  function ymd(d) {
    return d.getUTCFullYear() + '.' + String(d.getUTCMonth() + 1).padStart(2, '0') + '.' +
      String(d.getUTCDate()).padStart(2, '0');
  }

  /* ────────────────────────── 4대보험 ────────────────────────── */

  /**
   * 근로자 부담분 4대보험료. taxable 은 비과세를 뺀 월 과세 급여.
   * 산재보험은 전액 사업주 부담이라 근로자 공제에 들어가지 않는다.
   */
  function insurance(taxable, R) {
    var t = Math.max(0, num(taxable));
    if (t <= 0) return { pension: 0, health: 0, care: 0, employment: 0, total: 0 };

    // 국민연금은 기준소득월액 상·하한 안으로 잘라서 부과한다.
    var np = R.national_pension;
    var base = Math.min(Math.max(t, np.base_min), np.base_max);
    var pension = floorUnit(base * np.rate_employee, 10);

    var health = floorUnit(t * R.health.rate_employee, 10);
    var care = floorUnit(health * R.long_term_care.rate_of_health, 10);
    var employment = floorUnit(t * R.employment.rate_employee, 10);

    return {
      pension: pension, health: health, care: care, employment: employment,
      pensionCapped: t > np.base_max,
      total: pension + health + care + employment
    };
  }

  /* ────────────────────────── 소득세 ────────────────────────── */

  /** 근로소득공제 (연간 총급여 기준, 한도 2,000만원) */
  function earnedDeduction(g) {
    var d;
    if (g <= 5000000) d = g * 0.7;
    else if (g <= 15000000) d = 3500000 + (g - 5000000) * 0.4;
    else if (g <= 45000000) d = 7500000 + (g - 15000000) * 0.15;
    else if (g <= 100000000) d = 12000000 + (g - 45000000) * 0.05;
    else d = 14750000 + (g - 100000000) * 0.02;
    return Math.min(d, 20000000);
  }

  /** 기본세율 (과세표준 → 산출세액) */
  var TAX_BRACKETS = [
    [14000000, 0.06, 0], [50000000, 0.15, 1260000], [88000000, 0.24, 5760000],
    [150000000, 0.35, 15440000], [300000000, 0.38, 19940000], [500000000, 0.40, 25940000],
    [1000000000, 0.42, 35940000], [Infinity, 0.45, 65940000]
  ];

  function progressiveTax(base) {
    if (base <= 0) return 0;
    for (var i = 0; i < TAX_BRACKETS.length; i++) {
      if (base <= TAX_BRACKETS[i][0]) return base * TAX_BRACKETS[i][1] - TAX_BRACKETS[i][2];
    }
    return 0;
  }

  /** 근로소득세액공제 (총급여에 따라 한도가 다르다) */
  function earnedTaxCredit(calculated, g) {
    var c = calculated <= 1300000 ? calculated * 0.55 : 715000 + (calculated - 1300000) * 0.3;
    var cap;
    if (g <= 33000000) cap = 740000;
    else if (g <= 70000000) cap = Math.max(660000, 740000 - (g - 33000000) * 0.008);
    else if (g <= 120000000) cap = Math.max(500000, 660000 - (g - 70000000) * 0.5);
    else cap = Math.max(200000, 500000 - (g - 120000000) * 0.5);
    return Math.min(c, cap);
  }

  /** 8~20세 자녀 세액공제 — 간이세액표에서 빼는 월 금액 */
  function childCreditMonthly(children, R) {
    var c = R.income_tax.child_credit_monthly;
    if (children <= 0) return 0;
    if (children === 1) return c['1'];
    if (children === 2) return c['2'];
    return c['2'] + (children - 2) * c['3plus_add'];
  }

  /**
   * 간이세액표에서 월 소득세를 찾는다.
   * table 이 없으면(아직 탑재 전) 연말정산 산식으로 근사한다 — approx:true 로 표시한다.
   *
   * @param taxable 비과세를 뺀 월 과세 급여
   * @param family  공제대상가족 수(본인 포함)
   * @param children 8~20세 자녀 수
   */
  function incomeTax(taxable, family, children, table, R) {
    var t = Math.max(0, num(taxable));
    var fam = Math.min(Math.max(Math.round(family) || 1, 1), 11);
    var kid = Math.max(0, Math.round(children) || 0);

    if (t <= 0) return { tax: 0, local: 0, approx: !table };

    var tax;
    if (table && table.rows && table.rows.length) {
      tax = lookupTable(t, fam, table);
      tax = Math.max(0, tax - childCreditMonthly(kid, R));
      tax = floorUnit(tax, 10);
      return { tax: tax, local: floorUnit(tax * R.income_tax.local_rate, 10), approx: false };
    }

    // ── 표가 없을 때: 연말정산 산식으로 계산한 연간 결정세액 ÷ 12 ──
    var g = t * 12;
    var incomeAmt = g - earnedDeduction(g);
    var personal = 1500000 * fam;
    var pension = Math.min(Math.max(t, R.national_pension.base_min), R.national_pension.base_max) *
      R.national_pension.rate_employee * 12;
    var base = Math.max(0, incomeAmt - personal - pension);
    var calculated = progressiveTax(base);
    var credit = earnedTaxCredit(calculated, g);
    var childYear = kid === 0 ? 0 : (kid === 1 ? 250000 : (kid === 2 ? 550000 : 550000 + (kid - 2) * 400000));
    var decided = Math.max(0, calculated - credit - childYear);
    tax = floorUnit(decided / 12, 10);
    return { tax: tax, local: floorUnit(tax * R.income_tax.local_rate, 10), approx: true };
  }

  /** 간이세액표 조회. 표 밖(1,000만원 초과)은 별표2의 고액급여 산식을 쓴다. */
  function lookupTable(t, fam, T) {
    var col = Math.min(fam, T.family_max || 11) - 1;
    if (t < T.min) return 0;
    if (t <= T.max) {
      // 구간 간격이 일정하지 않을 수 있어 하한 목록에서 이분 탐색한다.
      var i;
      if (T.bounds && T.bounds.length === T.rows.length) {
        var lo = 0, hi = T.bounds.length - 1;
        while (lo < hi) {
          var mid = (lo + hi + 1) >> 1;
          if (T.bounds[mid] <= t) lo = mid; else hi = mid - 1;
        }
        i = lo;
      } else {
        i = Math.min(Math.floor((t - T.min) / T.step), T.rows.length - 1);
      }
      return T.rows[i][col] || 0;
    }
    // 월급여 1,000만원 초과 — 1,000만원일 때의 세액에 초과분을 더한다.
    var top = T.rows[T.rows.length - 1][col] || 0;
    var x = t;
    if (x <= 14000000) return top + (x - 10000000) * 0.98 * 0.35 + 25000;
    if (x <= 28000000) return top + 1397000 + (x - 14000000) * 0.98 * 0.38;
    if (x <= 30000000) return top + 6610600 + (x - 28000000) * 0.98 * 0.40;
    if (x <= 45000000) return top + 7394600 + (x - 30000000) * 0.40;
    if (x <= 87000000) return top + 13394600 + (x - 45000000) * 0.42;
    return top + 31034600 + (x - 87000000) * 0.45;
  }

  /* ────────────────────────── 실수령액 ────────────────────────── */

  /**
   * @param opt.mode 'year' | 'month'
   * @param opt.amount 연봉 또는 월급 (세전)
   * @param opt.taxFree 월 비과세액
   * @param opt.family 부양가족 수(본인 포함), opt.children 8~20세 자녀 수
   */
  function salary(opt, table, R) {
    var amount = Math.max(0, num(opt.amount));
    // 연봉을 12로 나눠 떨어지지 않을 때는 내림한다. 급여대장이 원 미만을 버리는 관행과 같고,
    // 반올림하면 보험료가 한 단계(10원) 올라가 다른 계산기와 어긋난다.
    var gross = opt.mode === 'month' ? amount : Math.floor(amount / 12);
    gross = Math.floor(gross);
    var free = Math.max(0, Math.min(num(opt.taxFree), gross));
    var taxable = gross - free;

    var ins = insurance(taxable, R);
    var tax = incomeTax(taxable, opt.family, opt.children, table, R);
    var deduct = ins.total + tax.tax + tax.local;
    var net = gross - deduct;

    return {
      gross: gross, taxFree: free, taxable: taxable,
      pension: ins.pension, health: ins.health, care: ins.care, employment: ins.employment,
      pensionCapped: ins.pensionCapped,
      tax: tax.tax, local: tax.local, approx: tax.approx,
      deduct: deduct, net: net, netYear: net * 12,
      grossYear: opt.mode === 'month' ? gross * 12 : Math.round(amount)
    };
  }

  /* ────────────────────────── 퇴직금 ────────────────────────── */

  /**
   * 평균임금 산정기간(퇴직일 이전 3개월)을 달 경계로 쪼갠다.
   * 고용노동부 계산기와 같은 방식이라 입력 칸이 보통 3~4개가 된다.
   */
  function avgPeriods(joinISO, leaveISO) {
    var join = toDate(joinISO), leave = toDate(leaveISO);
    if (!join || !leave || diffDays(join, leave) <= 0) return null;

    var end = addDays(leave, -1);                 // 마지막 근무일
    var start = addMonths(leave, -3);             // 퇴직일 이전 3개월
    if (diffDays(join, start) < 0) start = join;  // 재직 3개월 미만이면 입사일부터

    var segs = [], cur = start;
    while (diffDays(cur, end) >= 0) {
      var last = endOfMonth(cur);
      var segEnd = diffDays(last, end) < 0 ? end : last;
      segs.push({ from: toISO(cur), to: toISO(segEnd), label: ymd(cur) + ' ~ ' + ymd(segEnd),
                  days: diffDays(cur, segEnd) + 1 });
      cur = addDays(segEnd, 1);
    }
    return { periods: segs, totalDays: segs.reduce(function (s, p) { return s + p.days; }, 0) };
  }

  /**
   * @param opt.join, opt.leave (YYYY-MM-DD, leave = 마지막 근무일의 다음 날)
   * @param opt.pay [{basic, extra}] — avgPeriods 순서와 같은 길이
   * @param opt.bonus 연간 상여금 총액, opt.leavePay 연차수당(전년도 지급분)
   * @param opt.ordinaryDaily 1일 통상임금 (0이면 비교하지 않음)
   */
  function severance(opt, R) {
    var p = avgPeriods(opt.join, opt.leave);
    if (!p) return { error: '입사일과 퇴직일을 확인해 주세요. 퇴직일은 마지막 근무일의 다음 날입니다.' };

    var join = toDate(opt.join), leave = toDate(opt.leave);
    var serviceDays = diffDays(join, leave);
    if (serviceDays < 365) {
      return { error: '계속 근로기간이 1년 미만이면 법정 퇴직금이 발생하지 않습니다.',
               serviceDays: serviceDays, periods: p.periods };
    }

    var wage = 0;
    (opt.pay || []).forEach(function (row) { wage += num(row.basic) + num(row.extra); });
    var bonus = num(opt.bonus) * 3 / 12;
    var leavePay = num(opt.leavePay) * 3 / 12;
    var totalWage = wage + bonus + leavePay;

    var avgDaily = p.totalDays > 0 ? totalWage / p.totalDays : 0;
    var ordinary = num(opt.ordinaryDaily);
    var usedDaily = Math.max(avgDaily, ordinary);      // 평균임금이 통상임금보다 적으면 통상임금
    var byOrdinary = ordinary > avgDaily && ordinary > 0;

    var amount = Math.floor(usedDaily * 30 * (serviceDays / 365));

    return {
      periods: p.periods, totalDays: p.totalDays,
      serviceDays: serviceDays, serviceYears: Math.floor(serviceDays / 365),
      serviceLabel: serviceLabel(join, leave),
      wage: wage, bonus: bonus, leavePay: leavePay, totalWage: totalWage,
      avgDaily: avgDaily, avgMonthly: avgDaily * 30, ordinaryDaily: ordinary,
      usedDaily: usedDaily, byOrdinary: byOrdinary, amount: amount
    };
  }

  /** "3년 2개월 14일" */
  function serviceLabel(join, leave) {
    var y = leave.getUTCFullYear() - join.getUTCFullYear();
    var m = leave.getUTCMonth() - join.getUTCMonth();
    var d = leave.getUTCDate() - join.getUTCDate();
    if (d < 0) { m -= 1; d += new Date(Date.UTC(leave.getUTCFullYear(), leave.getUTCMonth(), 0)).getUTCDate(); }
    if (m < 0) { y -= 1; m += 12; }
    var out = [];
    if (y) out.push(y + '년');
    if (m) out.push(m + '개월');
    if (d) out.push(d + '일');
    return out.join(' ') || '0일';
  }

  /* ────────────────────────── 퇴직소득세 ────────────────────────── */

  /** 근속연수공제 (소득세법 제48조 제1항) */
  function serviceDeduction(years) {
    if (years <= 5) return 1000000 * years;
    if (years <= 10) return 5000000 + 2000000 * (years - 5);
    if (years <= 20) return 15000000 + 2500000 * (years - 10);
    return 40000000 + 3000000 * (years - 20);
  }

  /** 환산급여공제 (소득세법 제48조 제3항) */
  function convertedDeduction(converted) {
    if (converted <= 8000000) return converted;
    if (converted <= 70000000) return 8000000 + (converted - 8000000) * 0.6;
    if (converted <= 100000000) return 45200000 + (converted - 70000000) * 0.55;
    if (converted <= 300000000) return 61700000 + (converted - 100000000) * 0.45;
    return 151700000 + (converted - 300000000) * 0.35;
  }

  /**
   * 세법상 근속연수. 1년 미만의 기간이 있으면 1년으로 올린다(소득세법 제48조 제1항).
   * 기간은 근로를 시작한 날부터 퇴직한 날까지다(시행령 제105조).
   * leave 는 퇴직금 계산기와 같은 규약 — 마지막 근무일의 다음 날.
   */
  function serviceYears(joinISO, leaveISO) {
    var join = toDate(joinISO), leave = toDate(leaveISO);
    if (!join || !leave || diffDays(join, leave) <= 0) return 0;
    var y = 0;
    while (diffDays(addMonths(join, 12 * (y + 1)), leave) >= 0) y++;   // 꽉 찬 해
    var rest = diffDays(addMonths(join, 12 * y), leave);               // 남는 기간
    return rest > 0 ? y + 1 : y;
  }

  /**
   * 퇴직소득세 (연분연승법).
   * 퇴직급여 → 근속연수공제 → 환산급여(×12÷근속연수) → 환산급여공제 → 과세표준
   * → 기본세율 → 환산산출세액 → ÷12×근속연수 = 산출세액. 지방소득세는 그 10%.
   *
   * @param opt.payout 퇴직급여액(세전), opt.join·opt.leave 또는 opt.years(직접 입력)
   */
  function retirementTax(opt, R) {
    var payout = Math.max(0, num(opt.payout));
    var years = opt.years ? Math.max(1, Math.round(num(opt.years)))
                          : serviceYears(opt.join, opt.leave);
    if (!years) {
      return { error: '입사일과 퇴직일을 확인해 주세요. 퇴직일은 마지막 근무일의 다음 날입니다.' };
    }

    var svcDeduct = serviceDeduction(years);
    var afterSvc = Math.max(0, payout - svcDeduct);
    var converted = afterSvc * 12 / years;                 // 환산급여
    var convDeduct = convertedDeduction(converted);
    var base = Math.max(0, converted - convDeduct);        // 과세표준
    var convTax = progressiveTax(base);                    // 환산산출세액
    var tax = Math.floor(convTax * years / 12);            // 산출세액 (원 단위 절사)
    if (payout <= svcDeduct) tax = 0;
    var local = Math.floor(tax * R.income_tax.local_rate);
    var total = tax + local;

    return {
      payout: payout, years: years,
      serviceLabel: (opt.join && opt.leave) ? serviceLabel(toDate(opt.join), toDate(opt.leave)) : '',
      svcDeduct: svcDeduct, afterSvc: afterSvc,
      converted: converted, convDeduct: convDeduct, base: base, convTax: convTax,
      tax: tax, local: local, total: total,
      net: payout - total,
      rate: payout > 0 ? total / payout * 100 : 0
    };
  }

  /* ────────────────────────── 연차 ────────────────────────── */

  /** 근속연수 n년차에 발생하는 연차일수 (근로기준법 60조: 15일 + 2년마다 1일, 한도 25일) */
  function leaveDaysFor(years) {
    if (years < 1) return 0;
    return Math.min(25, 15 + Math.floor((years - 1) / 2));
  }

  /**
   * @param opt.join 입사일, opt.base 기준일(보통 오늘)
   * @param opt.mode 'join'(입사일 기준) | 'fiscal'(회계연도 1/1 기준)
   * @param opt.used 이미 사용한 연차일수
   * @param opt.monthlyOrdinary 월 통상임금 (미사용 수당 계산용, 0이면 생략)
   */
  function annualLeave(opt, R) {
    var join = toDate(opt.join), base = toDate(opt.base);
    if (!join || !base || diffDays(join, base) < 0) {
      return { error: '입사일과 기준일을 확인해 주세요. 기준일은 입사일 이후여야 합니다.' };
    }
    var rows = [], total = 0;

    // 1) 입사 1년 미만 — 1개월 개근마다 1일 (최대 11일).
    //    2020.3.31 개정으로 이 휴가는 모두 '입사일로부터 1년' 안에만 쓸 수 있다.
    var monthly = 0;
    for (var k = 1; k <= 11; k++) {
      if (diffDays(addMonths(join, k), base) >= 0) monthly = k;
    }
    if (monthly > 0) {
      rows.push({ when: ymd(addMonths(join, 1)) + (monthly > 1 ? ' ~ ' + ymd(addMonths(join, monthly)) : ''),
                  name: '입사 1년 미만 — 1개월 개근마다 1일', days: monthly,
                  expires: addDays(addMonths(join, 12), -1) });
      total += monthly;
    }

    if (opt.mode === 'fiscal') {
      // 2-A) 회계연도 기준 — 입사 다음 해 1월 1일에 첫 해 재직일수에 비례해 발생.
      //      각 발생분은 그 해 12월 31일까지 쓴다.
      var firstJan = new Date(Date.UTC(join.getUTCFullYear() + 1, 0, 1));
      if (diffDays(firstJan, base) >= 0) {
        var yearEnd = new Date(Date.UTC(join.getUTCFullYear(), 11, 31));
        var worked = diffDays(join, yearEnd) + 1;
        var pro = Math.round(15 * worked / 365 * 10) / 10;
        rows.push({ when: ymd(firstJan), name: '회계연도 첫 해 비례 (15일 × ' + worked + '/365)', days: pro,
                    expires: new Date(Date.UTC(firstJan.getUTCFullYear(), 11, 31)) });
        total += pro;
        var y = join.getUTCFullYear() + 2;
        while (diffDays(new Date(Date.UTC(y, 0, 1)), base) >= 0) {
          var yrs = y - join.getUTCFullYear();          // 1/1 시점의 근속연수(회계연도 관행)
          var d = leaveDaysFor(yrs);
          rows.push({ when: ymd(new Date(Date.UTC(y, 0, 1))),
                      name: y + '년 회계연도 (근속 ' + yrs + '년차' + (d > 15 ? ', 가산 ' + (d - 15) + '일' : '') + ')',
                      days: d, expires: new Date(Date.UTC(y, 11, 31)) });
          total += d;
          y++;
        }
      }
    } else {
      // 2-B) 입사일 기준 — 매년 입사일에 발생하고, 그 발생일로부터 1년간 쓴다.
      var n = 1;
      while (diffDays(addMonths(join, 12 * n), base) >= 0) {
        var dd = leaveDaysFor(n);
        var on = addMonths(join, 12 * n);
        rows.push({ when: ymd(on),
                    name: '근속 ' + n + '년차' + (dd > 15 ? ' (가산 ' + (dd - 15) + '일)' : ''), days: dd,
                    expires: addDays(addMonths(on, 12), -1) });
        total += dd;
        n++;
        if (n > 60) break;
      }
    }

    // 3) 유효기간이 지난 발생분은 소멸한다(미사용분은 수당으로 정산되거나 사라진다).
    var active = 0, expired = 0;
    rows.forEach(function (r) {
      r.alive = diffDays(base, r.expires) >= 0;
      r.expiresLabel = ymd(r.expires) + '까지';
      if (r.alive) active += r.days; else expired += r.days;
    });

    total = Math.round(total * 10) / 10;
    active = Math.round(active * 10) / 10;
    expired = Math.round(expired * 10) / 10;
    var used = Math.max(0, num(opt.used));
    var remain = Math.round((active - used) * 10) / 10;

    var mo = num(opt.monthlyOrdinary);
    var hourly = mo > 0 ? mo / R.work.monthly_standard_hours : 0;
    var daily = hourly * 8;
    var pay = remain > 0 ? Math.floor(daily * remain) : 0;

    return {
      rows: rows, total: total, active: active, expired: expired,
      used: used, remain: remain,
      serviceLabel: serviceLabel(join, base),
      hourly: Math.floor(hourly), daily: Math.floor(daily), pay: pay,
      nextOn: opt.mode === 'fiscal'
        ? ymd(new Date(Date.UTC(base.getUTCFullYear() + 1, 0, 1)))
        : ymd(nextJoinAnniv(join, base))
    };
  }

  function nextJoinAnniv(join, base) {
    var n = 1;
    while (diffDays(addMonths(join, 12 * n), base) >= 0) n++;
    return addMonths(join, 12 * n);
  }

  /* ────────────────────────── 결과 공유 (복사·이미지) ────────────────────────── */

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); } catch (e) { /* 무시 */ }
    document.body.removeChild(ta);
    return Promise.resolve();
  }

  /** 결과를 카드 이미지로 그린다(공유·저장용). rows = [[라벨, 값], ...] */
  function resultImage(opt) {
    var W = 900, pad = 48, rowH = 44;
    var rows = opt.rows || [];
    var H = pad * 2 + 150 + rows.length * rowH + 70;
    var cv = document.createElement('canvas');
    cv.width = W * 2; cv.height = H * 2;
    var c = cv.getContext('2d');
    c.scale(2, 2);
    var F = '"Pretendard Variable",Pretendard,-apple-system,"Malgun Gothic",sans-serif';

    c.fillStyle = '#ffffff'; c.fillRect(0, 0, W, H);
    c.fillStyle = '#24384f'; c.fillRect(0, 0, W, 150);
    c.fillStyle = '#c7d5e8'; c.font = '600 17px ' + F; c.textBaseline = 'top';
    c.fillText(opt.title || '', pad, 34);
    c.fillStyle = '#ffffff'; c.font = '800 46px ' + F;
    c.fillText(opt.heroValue || '', pad, 62);
    if (opt.heroSub) { c.fillStyle = '#b9cae0'; c.font = '500 15px ' + F; c.fillText(opt.heroSub, pad, 118); }

    var y = 150 + 24;
    rows.forEach(function (r) {
      c.fillStyle = '#eef1f5'; c.fillRect(pad, y + rowH - 1, W - pad * 2, 1);
      c.fillStyle = '#6b7280'; c.font = '500 16px ' + F; c.textAlign = 'left';
      c.fillText(r[0], pad, y + 12);
      c.fillStyle = r[2] ? '#24384f' : '#1f2937'; c.font = (r[2] ? '800 ' : '600 ') + '17px ' + F;
      c.textAlign = 'right'; c.fillText(r[1], W - pad, y + 11);
      c.textAlign = 'left';
      y += rowH;
    });

    c.fillStyle = '#9aa4b2'; c.font = '500 13px ' + F;
    c.fillText((opt.note || '') , pad, y + 16);
    c.textAlign = 'right'; c.fillStyle = '#24384f'; c.font = '700 14px ' + F;
    c.fillText('freeforms.kr', W - pad, y + 16);
    return cv;
  }

  function download(canvas, filename) {
    var a = document.createElement('a');
    a.download = filename + '.png';
    a.href = canvas.toDataURL('image/png');
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  }

  /** GA4 이벤트 — 도구 사용 집계 */
  function track(tool, action) {
    if (typeof global.gtag === 'function') {
      global.gtag('event', 'tool_use', { tool: tool, action: action || 'calc' });
    }
  }

  /** 숫자 입력칸에 천 단위 쉼표를 넣어 준다. */
  function bindMoney(el, onChange) {
    if (!el) return;
    el.addEventListener('input', function () {
      var pos = el.value.length - el.selectionStart;
      el.value = el.value === '' ? '' : fmt(num(el.value));
      var p = el.value.length - pos;
      try { el.setSelectionRange(p, p); } catch (e) { /* 무시 */ }
      if (onChange) onChange();
    });
  }

  /** 간이세액표를 한 번만 내려받는다. 실패해도 페이지는 근사 계산으로 동작한다. */
  function loadTaxTable(url) {
    return fetch(url, { cache: 'force-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  global.FFCalc = {
    num: num, fmt: fmt, floorUnit: floorUnit, toDate: toDate, toISO: toISO,
    diffDays: diffDays, addDays: addDays, addMonths: addMonths, ymd: ymd,
    insurance: insurance, incomeTax: incomeTax, salary: salary,
    avgPeriods: avgPeriods, severance: severance,
    retirementTax: retirementTax, serviceYears: serviceYears,
    serviceDeduction: serviceDeduction, convertedDeduction: convertedDeduction,
    annualLeave: annualLeave, leaveDaysFor: leaveDaysFor,
    copyText: copyText, resultImage: resultImage, download: download,
    track: track, bindMoney: bindMoney, loadTaxTable: loadTaxTable
  };
})(typeof window !== 'undefined' ? window : globalThis);

if (typeof module !== 'undefined' && module.exports) module.exports = globalThis.FFCalc;
