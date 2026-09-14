"""IndexNow 통보 — 새로 올리거나 고친 페이지를 검색엔진에 즉시 알린다.

IndexNow는 빙·네이버·Yandex·Seznam 등이 함께 쓰는 규약이다(구글은 지원하지 않는다).
한 곳(api.indexnow.org)에 보내면 참여 검색엔진 전체로 전달되므로, 검색엔진마다
따로 보낼 필요가 없다. 크롤러가 찾아올 때까지 기다리지 않아도 되는 것이 핵심이다.

전제. `build_site.py` 의 INDEXNOW_KEY 가 채워져 있고, 그 키 파일
(`https://<사이트>/<키>.txt`)이 **이미 배포되어 있어야** 한다. 키 파일이 안 보이면
검색엔진이 소유 증명에 실패해 통보를 버린다. 따라서 배포가 끝난 뒤에 실행한다.

사용법:
    python scripts/ping_indexnow.py --recent 3      # 최근 등록·수정된 3종 + 관련 목록 페이지
    python scripts/ping_indexnow.py --ids a,b,c     # 특정 서식 id 만
    python scripts/ping_indexnow.py --all           # 전 페이지 (처음 한 번만 권장)
    python scripts/ping_indexnow.py --recent 3 --dry-run   # 보낼 목록만 확인
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

ENDPOINT = "https://api.indexnow.org/IndexNow"
MAX_URLS = 10000  # 규약상 1회 상한
TIMEOUT = 30


def load_settings() -> tuple[str, str]:
    """build_site.py 에서 사이트 주소와 IndexNow 키를 읽는다(값을 한 곳에서만 관리)."""
    import build_site  # noqa: PLC0415 — 경로를 잡은 뒤 가져와야 한다

    key = getattr(build_site, "INDEXNOW_KEY", "")
    if not key:
        raise SystemExit("[중단] build_site.py 의 INDEXNOW_KEY 가 비어 있습니다.")
    return build_site.SITE_URL, key


def load_catalog() -> list[dict[str, Any]]:
    data = json.loads((ROOT / "catalog" / "catalog.json").read_text(encoding="utf-8"))
    return [f for f in data["forms"] if f.get("status", "published") == "published"]


def key_file_ok(site_url: str, key: str) -> bool:
    """키 파일이 실제로 배포돼 있는지 먼저 확인한다. 없으면 통보해도 버려진다."""
    url = f"{site_url}/{key}.txt"
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as res:
            return res.status == 200 and res.read().decode("utf-8").strip() == key
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        print(f"[중단] 키 파일을 확인할 수 없습니다 — {url} ({exc})")
        return False


def collect_urls(forms: list[dict[str, Any]], site_url: str,
                 mode: str, recent: int, ids: list[str]) -> list[str]:
    """통보할 URL 목록을 만든다. 상세 페이지만 보내면 목록 페이지가 낡은 채로 남는다."""
    if mode == "all":
        targets = forms
    elif mode == "ids":
        by_id = {f["id"]: f for f in forms}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise SystemExit(f"[중단] 카탈로그에 없는 id: {', '.join(missing)}")
        targets = [by_id[i] for i in ids]
    else:  # recent
        targets = sorted(forms, key=lambda f: (f.get("updated_at") or f.get("created_at") or ""),
                         reverse=True)[:recent]

    urls = [f"{site_url}/form/{f['id']}/" for f in targets]

    if mode == "all":
        # 전체 통보에서는 목록 페이지도 전부 넣는다
        cats = json.loads((ROOT / "catalog" / "categories.json").read_text(encoding="utf-8"))
        urls += [f"{site_url}/category/{c['key']}/{s['key']}/"
                 for c in cats["categories"] for s in c["subcategories"]]
        urls += [f"{site_url}/series/{k}/" for k in
                 {f["series"] for f in forms if f.get("series")}]
        cpath = ROOT / "catalog" / "collections.json"
        if cpath.exists():
            urls += [f"{site_url}/collection/{c['key']}/"
                     for c in json.loads(cpath.read_text(encoding="utf-8"))["collections"]]
        urls += [f"{site_url}/", f"{site_url}/about/", f"{site_url}/request/"]
        # 직장인 도구(허브 + 개별 도구). build_site 의 TOOLS 목록을 그대로 따라가므로
        # 도구를 추가해도 여기는 손댈 필요가 없다.
        import build_site  # noqa: PLC0415 — 도구 목록을 한 곳(TOOLS)에서만 관리한다
        urls.append(f"{site_url}/tools/")
        urls += [f"{site_url}{t['path']}" for t in getattr(build_site, "TOOLS", [])]
    else:
        # 새 서식이 걸린 분류 페이지와 메인도 함께 (목록에 새 항목이 추가되므로)
        subs = {f"{f['category']}/{f['subcategory']}" for f in targets}
        urls += [f"{site_url}/category/{s}/" for s in sorted(subs)]
        urls += [f"{site_url}/series/{k}/" for k in
                 sorted({f["series"] for f in targets if f.get("series")})]
        urls.append(f"{site_url}/")

    # 순서를 지키면서 중복 제거
    return list(dict.fromkeys(urls))[:MAX_URLS]


def submit(site_url: str, key: str, urls: list[str]) -> int:
    """한 번의 요청으로 전체 목록을 보낸다. 200/202 가 접수 성공이다."""
    host = site_url.split("//", 1)[-1].rstrip("/")
    body = json.dumps({
        "host": host,
        "key": key,
        "keyLocation": f"{site_url}/{key}.txt",
        "urlList": urls,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            print(f"[IndexNow] {res.status} {res.reason} — URL {len(urls)}건 접수")
            return 0
    except urllib.error.HTTPError as exc:
        detail = {
            400: "요청 형식 오류", 403: "키가 유효하지 않음(키 파일 확인 필요)",
            422: "URL이 host와 맞지 않거나 키 불일치", 429: "요청이 너무 잦음",
        }.get(exc.code, "")
        print(f"[IndexNow] 실패 {exc.code} {exc.reason} {detail}")
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[IndexNow] 전송 실패 — {exc}")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="IndexNow 통보")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--recent", type=int, metavar="N", help="최근 등록·수정된 N종")
    g.add_argument("--ids", help="쉼표로 구분한 서식 id")
    g.add_argument("--all", action="store_true", help="전 페이지 (처음 한 번만)")
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 목록만 출력")
    args = ap.parse_args()

    site_url, key = load_settings()
    forms = load_catalog()

    if args.all:
        mode, recent, ids = "all", 0, []
    elif args.ids:
        mode, recent, ids = "ids", 0, [x.strip() for x in args.ids.split(",") if x.strip()]
    else:
        mode, recent, ids = "recent", (args.recent or 3), []

    urls = collect_urls(forms, site_url, mode, recent, ids)
    if not urls:
        print("[IndexNow] 보낼 URL이 없습니다.")
        return 0

    print(f"[IndexNow] 대상 {len(urls)}건")
    for u in urls[:12]:
        print("   ", u)
    if len(urls) > 12:
        print(f"    … 외 {len(urls) - 12}건")

    if args.dry_run:
        print("[IndexNow] --dry-run 이므로 전송하지 않았습니다.")
        return 0
    if not key_file_ok(site_url, key):
        print("        배포가 끝난 뒤에 실행해야 합니다(키 파일이 사이트에 있어야 함).")
        return 1
    return submit(site_url, key, urls)


if __name__ == "__main__":
    raise SystemExit(main())
