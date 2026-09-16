"""법정서식 재현 명세 조립기: 원문 변환 blocks + 메타 YAML → specs/<id>.yaml.

역할 분담(SPEC_GUIDE 3-5절):
  - blocks      : scripts/pdf_to_gov_spec.py 가 원문 PDF 에서 자동 생성 (사람·에이전트가 손대지 않음)
  - 메타 YAML   : 에이전트가 작성 (tags·summary·usage·howto·faq·related·samples)
  - law_ref     : 원문 머리 줄에서 서식 번호·개정일을 자동으로 읽고, 법령명·주소는 출처표에서 가져온다

사용법:
    python scripts/assemble_gov_spec.py <id> [<id> ...] [--work sources/gov]
    (작업 폴더 기본값 sources/gov: blocks/<id>.yaml · meta/<id>.yaml · law_sources.tsv · roster_batch1.tsv)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

class AssembleError(RuntimeError):
    """조립 실패."""


def _norm(text: str) -> str:
    return re.sub(r"[\s·ㆍ()（）\[\]:：*※]", "", text)


def _read_tsv(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter="\t"))
    if rows and rows[0] and rows[0][0] == "id":
        head = rows[0]
        return {r[0]: dict(zip(head, r + [""] * (len(head) - len(r)))) for r in rows[1:] if r}
    return {r[0]: {"id": r[0], "law": r[1], "bylNo": r[2], "bylBrNo": r[3]} for r in rows if r}


def law_url(law: str, no: str, br: str) -> str:
    """국가법령정보센터 별표·서식 고정 주소(최신 시행본으로 열린다)."""
    q = urllib.parse.quote_plus(law)
    return (f"https://www.law.go.kr/LSW/lsBylInfoPLinkR.do?lsNm={q}&bylNo={no}&bylBrNo={br}"
            f"&bylCls=BF&bylEfYdYn=Y")


def fix_header(blocks: list[dict[str, Any]], law: str) -> tuple[str, str]:
    """원문 머리 줄에서 (서식번호, 개정일)을 읽고, 쪼개진 머리 줄을 정리한다.

    원문은 머리 줄 오른쪽에 '홈택스에서도 신청할 수 있습니다' 같은 안내를 함께 두어, 글자 줄이
    섞여 읽힌다. 머리 줄은 표준 한 줄로 다시 쓰고, 남는 안내문은 오른쪽 정렬 문단으로 보존한다.
    """
    head_paras: list[dict[str, Any]] = []
    for b in blocks[:6]:
        if b["type"] != "para":
            break
        head_paras.append(b)
        if re.search(r"(개정|신설)", " ".join(x["text"] for x in head_paras)) and \
                re.search(r"\d{1,2}\.\s*>", " ".join(x["text"] for x in head_paras)):
            break
    joined = " ".join(b["text"] for b in head_paras)
    m = re.search(r"\[\s*별지\s*(제\s*[^\]]*?서식(?:\(\d\))?)\s*\]", joined)
    d = re.search(r"<\s*(개정|신설)\s*(\d{4})\.\s*(\d{1,2})\.\s*(.*?)(\d{1,2})\.?\s*>", joined, re.S)
    if not m or not d:
        raise AssembleError("원문 머리 줄에서 서식 번호·개정일을 읽지 못했습니다.")
    form_no = "별지 " + re.sub(r"\s+", "", m.group(1))
    y, mo, day = int(d.group(2)), int(d.group(3)), int(d.group(5))
    amended = f"{y:04d}-{mo:02d}-{day:02d}"
    rest = joined.replace(d.group(0), " " + d.group(4) + " ")
    rest = re.sub(r"■?[^\[]*\[\s*별지[^\]]*\]", " ", rest, count=1)
    rest = " ".join(rest.split())
    first = head_paras[0]
    first["text"] = f"■ {law} [{form_no}] <{d.group(1)} {y}. {mo}. {day}.>"
    first["align"] = "left"
    for b in head_paras[1:]:
        blocks.remove(b)
    if rest:
        blocks.insert(blocks.index(first) + 1,
                      {"type": "para", "text": rest, "align": "right", "size": first.get("size", 7.5),
                       "space_after": 0, "line_spacing": 1.0})
    return form_no, amended


def place_samples(blocks: list[dict[str, Any]], samples: list[dict[str, str]]) -> list[str]:
    """{label, value} 예시를 라벨 칸 오른쪽 빈 칸(없으면 라벨 칸 자체)에 넣는다. 못 넣은 라벨을 돌려준다."""
    missed: list[str] = []
    tables = [b for b in blocks if b["type"] == "gov_table"]
    for item in samples or []:
        label, value = _norm(str(item.get("label", ""))), str(item.get("value", "")).strip()
        if not label or not value:
            continue
        done = False
        for tb in tables:
            cells = tb.get("cells") or []
            index = {(c["at"][0], c["at"][1]): c for c in cells}
            for c in cells:
                lines = c.get("lines") or []
                if not lines or _norm(lines[0][1]) != label or c.get("sample"):
                    continue
                r, col, _rs, cs = c["at"]
                right = index.get((r, col + cs))
                if right is not None and not right.get("lines") and not right.get("sample"):
                    right["sample"] = value  # 라벨 칸 | 빈 기입 칸
                else:
                    c["sample"] = value  # 라벨과 기입란이 한 칸(칸 이름이 왼쪽 위)인 원문
                done = True
                break
            if done:
                break
        if not done:
            missed.append(str(item.get("label")))
    return missed


def assemble(form_id: str, blocks_path: Path, meta_path: Path, source: dict[str, str],
             roster: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    blocks = yaml.safe_load(blocks_path.read_text(encoding="utf-8"))["blocks"]
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    law = source["law"]
    form_no, amended = fix_header(blocks, law)
    missed = place_samples(blocks, meta.pop("samples", []) or [])
    pages = 1 + sum(1 for b in blocks if b["type"] == "page_break")
    if not any(b["type"] == "doc_title" for b in blocks):
        pass  # 제목이 표 안에 있는 옛 서식(입찰서 등) — 원문대로 둔다
    spec: dict[str, Any] = {
        "id": form_id,
        "title": roster["title"],
        "category": roster["category"],
        "subcategory": roster["subcategory"],
        "tags": meta["tags"],
        "summary": meta["summary"],
        "usage": meta["usage"],
        "source": "law-standard",
        "source_note": f"{law} {form_no}",
        "law_ref": {
            "law": law, "form_no": form_no, "amended": amended,
            "url": law_url(law, source["bylNo"], source["bylBrNo"]),
            "agency": roster.get("agency", ""),
            "checked": datetime.now(KST).strftime("%Y-%m-%d"),
        },
        "featured": False,
        "target_pages": pages,
        "created_by": "gov-batch",
    }
    if roster.get("series_with"):
        base = yaml.safe_load((ROOT / "specs" / f"{roster['series_with']}.yaml").read_text(encoding="utf-8"))
        spec["series"] = base.get("series") or roster["series_with"]
        spec["series_name"] = base.get("series_name") or base["title"]
        spec["variant"] = "법정서식"
        spec["variant_rank"] = 2
        spec["variant_use"] = meta.get("variant_use") or "관공서에 그대로 제출할 법정 양식이 필요할 때 씁니다."
    for key in ("howto", "faq", "related"):
        if meta.get(key):
            spec[key] = meta[key]
    spec["blocks"] = blocks
    return spec, missed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--work", type=Path, default=ROOT / "sources" / "gov")
    args = ap.parse_args(argv)
    sources = _read_tsv(args.work / "law_sources.tsv")
    roster = _read_tsv(args.work / "roster_batch1.tsv")
    code = 0
    for fid in args.ids:
        try:
            spec, missed = assemble(fid, args.work / "blocks" / f"{fid}.yaml", args.work / "meta" / f"{fid}.yaml",
                                    sources[fid], roster[fid])
        except (AssembleError, KeyError, OSError, yaml.YAMLError) as exc:
            print(f"[오류] {fid}: {exc}")
            code = 1
            continue
        out = ROOT / "specs" / f"{fid}.yaml"
        out.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
        note = f" · 예시 못 넣은 라벨 {missed}" if missed else ""
        print(f"[조립] {fid} ({spec['law_ref']['form_no']}, 개정 {spec['law_ref']['amended']}){note}")
    return code


if __name__ == "__main__":
    sys.exit(main())
