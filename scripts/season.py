"""시즌 가중치 계산기 — 일일 에이전트가 후보 배점(3절)과 가이드 주제 선정(5-1절)에 쓴다.

사용법:
    python scripts/season.py                 # 오늘(KST) 기준 활성 시즌 표
    python scripts/season.py --date 2026-11-05
    python scripts/season.py --json          # 기계가 읽는 형식

규칙 (catalog/season_calendar.json):
    - 선행 구간  = 시즌 시작일 - lead_days ≤ 오늘 < 시즌 시작일   → +20점 (검색 수요가 오르기 전에 색인을 끝낸다)
    - 시즌 중    = 시즌 시작일 ≤ 오늘 ≤ 시즌 종료일              → +10점
    - 그 외 0점. 한 후보가 여러 시즌에 걸리면 가장 높은 점수 하나만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
CALENDAR: Path = ROOT / "catalog" / "season_calendar.json"
KST: timezone = timezone(timedelta(hours=9))


@dataclass
class ActiveSeason:
    key: str
    name: str
    phase: str          # "lead" | "in_season"
    score: int
    start: str
    end: str
    days_to_start: int  # 선행 구간이면 양수, 시즌 중이면 0 이하
    keywords: list[str]


def _windows(season: dict, today: date) -> list[tuple[date, date]]:
    """시즌의 (시작, 종료) 구간 목록 — 매년 반복형은 작년·올해·내년을 펼쳐 연말연시 경계를 처리한다."""
    out: list[tuple[date, date]] = []
    for s, e in season.get("dates", []):
        out.append((date.fromisoformat(s), date.fromisoformat(e)))
    for s, e in season.get("every_year", []):
        for y in (today.year - 1, today.year, today.year + 1):
            start = date.fromisoformat(f"{y}-{s}")
            end = date.fromisoformat(f"{y}-{e}")
            if end < start:  # 해를 넘기는 구간(예: 12-15~01-31)
                end = date.fromisoformat(f"{y + 1}-{e}")
            out.append((start, end))
    return out


def active_seasons(today: date, calendar_path: Path = CALENDAR) -> list[ActiveSeason]:
    try:
        cal: dict = json.loads(calendar_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[시즌] 캘린더 없음: {calendar_path} — 시즌 가중치 0으로 진행", file=sys.stderr)
        return []
    except json.JSONDecodeError as exc:
        print(f"[시즌] 캘린더 JSON 오류: {exc} — 시즌 가중치 0으로 진행", file=sys.stderr)
        return []

    default_lead: int = int(cal.get("lead_days_default", 28))
    score: dict = cal.get("score", {"lead": 20, "in_season": 10})
    result: list[ActiveSeason] = []
    for season in cal.get("seasons", []):
        lead: int = int(season.get("lead_days", default_lead))
        best: ActiveSeason | None = None
        for start, end in _windows(season, today):
            if start - timedelta(days=lead) <= today < start:
                cand = ActiveSeason(season["key"], season["name"], "lead", int(score["lead"]),
                                    start.isoformat(), end.isoformat(), (start - today).days,
                                    season.get("keywords", []))
            elif start <= today <= end:
                cand = ActiveSeason(season["key"], season["name"], "in_season", int(score["in_season"]),
                                    start.isoformat(), end.isoformat(), (start - today).days,
                                    season.get("keywords", []))
            else:
                continue
            if best is None or cand.score > best.score:
                best = cand
        if best:
            result.append(best)
    result.sort(key=lambda a: (-a.score, a.days_to_start))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="오늘 적용할 시즌 가중치")
    ap.add_argument("--date", help="기준일 YYYY-MM-DD (기본: 오늘 KST)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    try:
        today: date = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    except ValueError:
        print(f"[시즌] 날짜 형식 오류: {args.date} (YYYY-MM-DD)", file=sys.stderr)
        return 2

    seasons = active_seasons(today)
    if args.json:
        print(json.dumps([asdict(s) for s in seasons], ensure_ascii=False, indent=2))
        return 0

    print(f"[시즌 가중치] 기준일 {today.isoformat()} (KST)")
    if not seasons:
        print("  활성 시즌 없음 — 시즌 가중치 0점")
        return 0
    for s in seasons:
        phase = f"선행 +{s.score}점 (시작 {s.days_to_start}일 전)" if s.phase == "lead" else f"시즌 중 +{s.score}점"
        print(f"  - {s.name}: {phase} · {s.start}~{s.end} · 키워드: {', '.join(s.keywords)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
