"""지금 기준 방문자 현황 — GA4 Data API (실시간 30분 · 오늘 · 어제 · 최근 7일 · 오늘 인기 페이지 · 유입 경로).

사용: GA4_SA_JSON(서비스 계정 키 내용)·GA4_PROPERTY_ID 환경변수를 넣고 실행.
    python scripts/visitors_now.py
키 내용은 출력하지 않는다. 시간은 GA4 속성 시간대(KST) 기준.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
BASE = "https://analyticsdata.googleapis.com/v1beta/properties/{pid}:{method}"


def session() -> Any:
    raw = os.environ.get("GA4_SA_JSON", "").strip()
    if not raw or not os.environ.get("GA4_PROPERTY_ID"):
        raise SystemExit("[방문자] GA4_SA_JSON·GA4_PROPERTY_ID 환경변수가 없습니다")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as exc:
        raise SystemExit(f"[방문자] google-auth 미설치: {exc.name}") from exc
    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[방문자] 키 파일 JSON 형식 오류 (줄 {exc.lineno})") from exc
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/analytics.readonly"])
    return AuthorizedSession(creds)


def call(s: Any, method: str, body: dict) -> list[dict]:
    import requests
    url = BASE.format(pid=os.environ["GA4_PROPERTY_ID"].strip(), method=method)
    try:
        r = s.post(url, json=body, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(f"연결 실패 {type(exc).__name__}") from exc
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    d = r.json()
    dims = [x["name"] for x in d.get("dimensionHeaders", [])]
    mets = [x["name"] for x in d.get("metricHeaders", [])]
    out = []
    for row in d.get("rows", []):
        item = {n: v["value"] for n, v in zip(dims, row.get("dimensionValues", []))}
        for n, v in zip(mets, row.get("metricValues", [])):
            item[n] = float(v["value"])
        out.append(item)
    return out


def total(s: Any, start: str, end: str) -> dict:
    rows = call(s, "runReport", {"dateRanges": [{"startDate": start, "endDate": end}],
                                  "metrics": [{"name": "activeUsers"}, {"name": "sessions"},
                                              {"name": "screenPageViews"}, {"name": "userEngagementDuration"}]})
    return rows[0] if rows else {"activeUsers": 0, "sessions": 0, "screenPageViews": 0, "userEngagementDuration": 0}


def downloads(s: Any, start: str, end: str) -> float:
    rows = call(s, "runReport", {"dateRanges": [{"startDate": start, "endDate": end}],
                                  "dimensions": [{"name": "eventName"}], "metrics": [{"name": "eventCount"}],
                                  "dimensionFilter": {"filter": {"fieldName": "eventName",
                                                                 "inListFilter": {"values": ["dl_pdf", "dl_docx", "dl_hwpx"]}}}})
    return sum(r["eventCount"] for r in rows)


def main() -> int:
    s = session()
    now = datetime.now(KST)
    print(f"[freeforms.kr 방문자 현황] {now:%Y-%m-%d %H:%M} KST 기준 (GA4는 보통 수 시간 늦게 집계됩니다)")
    try:
        rt = call(s, "runRealtimeReport", {"metrics": [{"name": "activeUsers"}]})
        print(f"- 실시간(최근 30분) 활성 사용자: {rt[0]['activeUsers'] if rt else 0:,.0f}명")
    except RuntimeError as exc:
        print(f"- 실시간 조회 실패: {exc}")

    print("\n| 기간 | 방문자 | 세션 | 페이지뷰 | 다운로드 | 평균 참여 시간 |")
    print("|---|---|---|---|---|---|")
    for label, a, b in [("오늘(지금까지)", "today", "today"), ("어제", "yesterday", "yesterday"),
                        ("최근 7일", "6daysAgo", "today"), ("개설 후 전체", "2026-09-13", "today")]:
        try:
            t = total(s, a, b)
            eng = t["userEngagementDuration"] / t["activeUsers"] if t["activeUsers"] else 0
            print(f"| {label} | {t['activeUsers']:,.0f} | {t['sessions']:,.0f} | {t['screenPageViews']:,.0f} | "
                  f"{downloads(s, a, b):,.0f} | {int(eng // 60)}분 {int(eng % 60)}초 |")
        except RuntimeError as exc:
            print(f"| {label} | 조회 실패: {exc} | | | | |")

    for title, dim, lim in [("오늘·어제 인기 페이지 5", "pagePath", 5), ("최근 7일 유입 경로", "sessionSourceMedium", 6)]:
        try:
            rng = [{"startDate": "yesterday", "endDate": "today"}] if dim == "pagePath" else [{"startDate": "6daysAgo", "endDate": "today"}]
            met = "screenPageViews" if dim == "pagePath" else "sessions"
            rows = call(s, "runReport", {"dateRanges": rng, "dimensions": [{"name": dim}], "metrics": [{"name": met}],
                                         "orderBys": [{"metric": {"metricName": met}, "desc": True}], "limit": lim})
            print(f"\n{title}")
            for i, r in enumerate(rows, 1):
                print(f"  {i}. {r[dim]} — {r[met]:,.0f}")
            if not rows:
                print("  (데이터 없음)")
        except RuntimeError as exc:
            print(f"\n{title}: 조회 실패 {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
