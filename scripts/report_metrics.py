"""일일·주간 지표 수집 — GA4 Data API + 서치콘솔 API → 리포트용 마크다운.

GitHub Actions(daily-forms.yml)가 에이전트 실행 전에 부른다. 에이전트는 결과 파일을 리포트에 그대로 붙인다.

    python scripts/report_metrics.py --out logs/_metrics_today.md            # 매일
    python scripts/report_metrics.py --out logs/_metrics_today.md --weekly   # 월요일 (주간 표 추가)

필요한 저장소 Secrets (값은 절대 로그·커밋·대화에 남기지 않는다):
    GA4_SA_JSON      서비스 계정 JSON 키 전체 내용
    GA4_PROPERTY_ID  GA4 속성 ID (숫자, 측정 ID G-... 가 아님)
    GSC_SITE         (선택) 서치콘솔 속성. 기본 sc-domain:freeforms.kr

Secrets 가 없거나 API 호출이 실패해도 **항상 종료코드 0** 으로 끝나고 "지표 미연결/실패" 한 줄을 남긴다.
지표 때문에 서식 생성·배포가 멈추면 안 된다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

KST: timezone = timezone(timedelta(hours=9))
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]
GA4_URL: str = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:runReport"
GSC_URL: str = "https://searchconsole.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query"
TIMEOUT: int = 30

# 실행계획서 2절 목표 (11/30 기준)
TARGETS: dict[str, str] = {
    "organic_sessions": "500 이상/주",
    "engagement_sec": "90초 이상",
    "pages_per_session": "1.8 이상",
    "guide_to_form_rate": "25% 이상",
    "blog_sessions": "100 이상/주",
}


class MetricsUnavailable(Exception):
    """자격증명이 없거나 형식이 틀려 지표를 뽑을 수 없음"""


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, text: str = "") -> None:
        self.lines.append(text)

    def render(self) -> str:
        out = list(self.lines)
        if self.errors:
            out.append("")
            out.append("지표 일부 실패: " + " / ".join(self.errors))
        return "\n".join(out).rstrip() + "\n"


# ── API 호출 ─────────────────────────────────────────────────────────────
def make_session() -> Any:
    """서비스 계정 세션. 라이브러리·Secrets 가 없으면 MetricsUnavailable."""
    raw: str = os.environ.get("GA4_SA_JSON", "").strip()
    if not raw or not os.environ.get("GA4_PROPERTY_ID", "").strip():
        raise MetricsUnavailable("Secrets(GA4_SA_JSON·GA4_PROPERTY_ID) 미등록")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise MetricsUnavailable(f"google-auth 미설치 ({exc.name})") from exc
    try:
        info: dict = json.loads(raw)
    except json.JSONDecodeError as exc:
        # 비밀값 내용은 출력하지 않는다 — 위치만
        raise MetricsUnavailable(f"GA4_SA_JSON 이 JSON 형식이 아님 (줄 {exc.lineno})") from exc
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    except (ValueError, KeyError) as exc:
        raise MetricsUnavailable(f"서비스 계정 키 필드 오류: {type(exc).__name__}") from exc
    return AuthorizedSession(creds)


def ga4(session: Any, body: dict) -> list[dict]:
    """GA4 runReport → [{dim..., met...}] 행 목록"""
    import requests  # google-auth 와 함께 설치됨

    url = GA4_URL.format(pid=os.environ["GA4_PROPERTY_ID"].strip())
    try:
        r = session.post(url, json=body, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"GA4 연결 실패: {type(exc).__name__}") from exc
    if r.status_code != 200:
        msg = r.json().get("error", {}).get("message", "")[:120] if r.headers.get("content-type", "").startswith("application/json") else ""
        raise RuntimeError(f"GA4 HTTP {r.status_code} {msg}")
    data: dict = r.json()
    dims = [d["name"] for d in data.get("dimensionHeaders", [])]
    mets = [m["name"] for m in data.get("metricHeaders", [])]
    rows: list[dict] = []
    for row in data.get("rows", []):
        item: dict[str, Any] = {}
        for n, v in zip(dims, row.get("dimensionValues", [])):
            item[n] = v.get("value", "")
        for n, v in zip(mets, row.get("metricValues", [])):
            try:
                item[n] = float(v.get("value", "0"))
            except ValueError:
                item[n] = 0.0
        rows.append(item)
    return rows


def gsc_queries(session: Any, start: str, end: str, limit: int = 5) -> list[dict]:
    import requests

    site = os.environ.get("GSC_SITE", "").strip() or "sc-domain:freeforms.kr"
    url = GSC_URL.format(site=quote(site, safe=""))
    body = {"startDate": start, "endDate": end, "dimensions": ["query"], "rowLimit": limit}
    try:
        r = session.post(url, json=body, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"서치콘솔 연결 실패: {type(exc).__name__}") from exc
    if r.status_code == 403:
        raise RuntimeError("서치콘솔 403 — 서비스 계정을 서치콘솔 사용자(제한됨)로 추가해야 함")
    if r.status_code != 200:
        raise RuntimeError(f"서치콘솔 HTTP {r.status_code}")
    return r.json().get("rows", [])


# ── 보고서 조립 ──────────────────────────────────────────────────────────
def _event_filter(names: list[str]) -> dict:
    return {"filter": {"fieldName": "eventName", "inListFilter": {"values": names}}}


def event_counts(session: Any, start: str, end: str, names: list[str]) -> dict[str, float]:
    rows = ga4(session, {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "dimensionFilter": _event_filter(names),
    })
    counts = {n: 0.0 for n in names}
    for row in rows:
        counts[row["eventName"]] = row["eventCount"]
    return counts


def blog_sessions(session: Any, start: str, end: str) -> float:
    rows = ga4(session, {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "metrics": [{"name": "sessions"}],
        "dimensionFilter": {"filter": {"fieldName": "sessionSource",
                                       "stringFilter": {"matchType": "CONTAINS", "value": "blog.naver"}}},
    })
    return rows[0]["sessions"] if rows else 0.0


def pct(num: float, den: float) -> str:
    return f"{num / den * 100:.1f}%" if den else "—"


def build_daily(session: Any, rep: Report, today: datetime) -> None:
    # GA4 속성 시간대(KST) 기준 '어제' = 08:00 실행 시점의 최근 하루
    rep.add("[지표] 전일(어제 00:00~24:00 KST) 기준")
    try:
        rows = ga4(session, {"dateRanges": [{"startDate": "yesterday", "endDate": "yesterday"}],
                             "metrics": [{"name": "activeUsers"}, {"name": "sessions"}]})
        users = rows[0]["activeUsers"] if rows else 0
        sess = rows[0]["sessions"] if rows else 0
        rep.add(f"- 방문자 {users:,.0f}명 · 세션 {sess:,.0f}")
    except RuntimeError as exc:
        rep.errors.append(str(exc))

    try:
        dl = event_counts(session, "yesterday", "yesterday", ["dl_pdf", "dl_docx", "dl_hwpx"])
        rep.add(f"- 다운로드 {sum(dl.values()):,.0f}건 (PDF {dl['dl_pdf']:,.0f} · Word {dl['dl_docx']:,.0f} · 한글 {dl['dl_hwpx']:,.0f})")
    except RuntimeError as exc:
        rep.errors.append(str(exc))

    # 서치콘솔은 2~3일 늦게 확정되므로 3일 전까지의 최근 7일
    end_d = (today - timedelta(days=3)).date()
    start_d = end_d - timedelta(days=6)
    try:
        qs = gsc_queries(session, start_d.isoformat(), end_d.isoformat())
        rep.add(f"- 검색 유입 상위 검색어 ({start_d:%m/%d}~{end_d:%m/%d}, 구글)")
        if not qs:
            rep.add("  · 아직 데이터 없음")
        for i, q in enumerate(qs, 1):
            rep.add(f"  {i}. {q['keys'][0]} — 클릭 {q.get('clicks', 0):,.0f} · 노출 {q.get('impressions', 0):,.0f} · 평균순위 {q.get('position', 0):.1f}")
    except RuntimeError as exc:
        rep.errors.append(str(exc))

    try:
        rows = ga4(session, {
            "dateRanges": [{"startDate": "yesterday", "endDate": "yesterday"}],
            "dimensions": [{"name": "pagePath"}],
            "metrics": [{"name": "eventCount"}],
            "dimensionFilter": _event_filter(["guide_view"]),
            "orderBys": [{"metric": {"metricName": "eventCount"}, "desc": True}],
            "limit": 3,
        })
        rep.add("- 가이드 조회 상위 3편")
        if not rows:
            rep.add("  · 조회 없음")
        for i, row in enumerate(rows, 1):
            rep.add(f"  {i}. {row['pagePath']} — {row['eventCount']:,.0f}회")
        ev = event_counts(session, "yesterday", "yesterday", ["guide_view", "guide_to_form", "article_card_click"])
        rep.add(f"- 가이드→서식 전환 {pct(ev['guide_to_form'], ev['guide_view'])} "
                f"({ev['guide_to_form']:,.0f}/{ev['guide_view']:,.0f}) · 상세→가이드 클릭 {ev['article_card_click']:,.0f}회")
    except RuntimeError as exc:
        rep.errors.append(str(exc))

    try:
        b = blog_sessions(session, "yesterday", "yesterday")
        if b > 0:
            rep.add(f"- 네이버 블로그 유입 {b:,.0f}세션")
    except RuntimeError as exc:
        rep.errors.append(str(exc))


def build_weekly(session: Any, rep: Report) -> None:
    rep.add("")
    rep.add("[주간 지표] 최근 7일 (7일 전~어제, KST) · 목표는 11/30 기준")
    rep.add("| 지표 | 값 | 목표 |")
    rep.add("|---|---|---|")
    rng = [{"startDate": "7daysAgo", "endDate": "yesterday"}]
    try:
        rows = ga4(session, {
            "dateRanges": rng,
            "metrics": [{"name": "sessions"}],
            "dimensionFilter": {"filter": {"fieldName": "sessionDefaultChannelGroup",
                                           "stringFilter": {"matchType": "EXACT", "value": "Organic Search"}}},
        })
        rep.add(f"| 검색 유입 세션 | {rows[0]['sessions'] if rows else 0:,.0f} | {TARGETS['organic_sessions']} |")
        rows = ga4(session, {"dateRanges": rng, "metrics": [
            {"name": "activeUsers"}, {"name": "userEngagementDuration"}, {"name": "screenPageViewsPerSession"}]})
        r0 = rows[0] if rows else {"activeUsers": 0, "userEngagementDuration": 0, "screenPageViewsPerSession": 0}
        eng = r0["userEngagementDuration"] / r0["activeUsers"] if r0["activeUsers"] else 0
        rep.add(f"| 평균 참여 시간 | {int(eng // 60)}분 {int(eng % 60)}초 | {TARGETS['engagement_sec']} |")
        rep.add(f"| 세션당 페이지 | {r0['screenPageViewsPerSession']:.2f} | {TARGETS['pages_per_session']} |")
        ev = event_counts(session, "7daysAgo", "yesterday", ["guide_view", "guide_to_form"])
        rep.add(f"| 가이드→서식 전환 | {pct(ev['guide_to_form'], ev['guide_view'])} | {TARGETS['guide_to_form_rate']} |")
        rep.add(f"| 네이버 블로그 유입 | {blog_sessions(session, '7daysAgo', 'yesterday'):,.0f} | {TARGETS['blog_sessions']} |")
    except RuntimeError as exc:
        rep.errors.append(str(exc))
    rep.add("| 구글 색인 페이지 | 서치콘솔에서 수동 확인 | 300 이상 |")


def main() -> int:
    ap = argparse.ArgumentParser(description="GA4·서치콘솔 지표 → 리포트 마크다운")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--weekly", action="store_true", help="주간 지표표 추가 (월요일)")
    args = ap.parse_args()

    rep = Report()
    now = datetime.now(KST)
    try:
        session = make_session()
        build_daily(session, rep, now)
        if args.weekly:
            build_weekly(session, rep)
    except MetricsUnavailable as exc:
        rep.lines = [f"[지표] 지표 미연결 — {exc}. GA4·서치콘솔 수치는 수동 확인"]

    text = rep.render()
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"[지표] 파일 저장 실패: {exc}", file=sys.stderr)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
