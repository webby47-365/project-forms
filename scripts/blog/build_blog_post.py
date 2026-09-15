"""네이버 블로그 초안 빌더 — post.json 1개 → post.html + 사진 PNG (규칙 정본: scripts/agent/blog_draft_agent.md).

사용법:
    python scripts/blog/build_blog_post.py <초안폴더>          # 폴더 안의 post.json 을 읽는다
    python scripts/blog/build_blog_post.py <초안폴더> --check  # 검사만 (글자 수·링크·사진 자리)

글 안의 간이 표기 (그 밖의 HTML 은 전부 이스케이프된다):
    **굵게**   !!주황 굵게(주의)!!   __밑줄 굵게(기준 날짜·수치)__

복사 영역은 인라인 스타일만 쓴다 — 스마트에디터가 클래스 CSS 를 버리기 때문이다.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_images import Marker, annotate, checklist, compare, thumbnail  # noqa: E402

CATEGORIES: list[str] = ["퇴사·이직", "취업 서류", "근로·인사", "계약·분쟁", "부동산·이사", "회사 실무", "학교·생활·동의서"]
BODY_MIN, BODY_MAX = 1800, 2500
SITE = "https://freeforms.kr"

S = {
    "p": 'font-size:16px;line-height:1.9;color:#222222;margin:0 0 16px',
    "h2": 'font-size:24px;font-weight:bold;color:#1b2c40;margin:40px 0 14px',
    "li": 'font-size:16px;line-height:1.9;color:#222222;margin:0 0 8px',
    "summary": 'font-size:16px;line-height:1.9;color:#1b2c40;background-color:#eef4fb;padding:14px 16px;margin:0 0 18px',
    "td": 'border:1px solid #cfd8e3;padding:10px 12px;font-size:15px;line-height:1.7;vertical-align:top',
    "th": 'border:1px solid #cfd8e3;padding:10px 12px;font-size:15px;font-weight:bold;background-color:#1b2c40;color:#ffffff',
    "img": 'font-size:15px;font-weight:bold;color:#0b7285;background-color:#e3fafc;padding:16px;margin:10px 0 22px;text-align:center',
    "q": 'font-size:16px;line-height:1.8;font-weight:bold;color:#1b2c40;margin:18px 0 4px',
    "b": 'font-weight:bold', "em": 'font-weight:bold;color:#e8590c', "u": 'text-decoration:underline;font-weight:bold',
}


class PostError(Exception):
    """post.json 규칙 위반"""


def inline(text: str) -> str:
    s = html.escape(text, quote=True)
    s = re.sub(r"\*\*(.+?)\*\*", rf'<span style="{S["b"]}">\1</span>', s)
    s = re.sub(r"!!(.+?)!!", rf'<span style="{S["em"]}">\1</span>', s)
    s = re.sub(r"__(.+?)__", rf'<span style="{S["u"]}">\1</span>', s)
    return s


def render_block(b: dict[str, Any], images: list[dict[str, Any]]) -> str:
    t = b.get("t")
    if t == "img":
        name = images[int(b["n"]) - 1]["file"]
        return f'<p style="{S["img"]}">[사진 넣기] {html.escape(name)} — 이 줄을 지우고 사진을 넣으세요</p>'
    if t in ("p", "summary", "li", "q"):
        idattr = f' id="{b["id"]}"' if b.get("id") else ""
        return f'<p{idattr} style="{S[t]}">{inline(b["text"])}</p>'
    if t == "h2":
        return f'<p style="{S["h2"]}">{html.escape(b["text"])}</p>'
    if t == "check":
        return f'<p style="{S["li"]}">✔ {inline(b["text"])}</p>'
    if t == "table":
        head = "".join(f'<td style="{S["th"]}">{inline(h)}</td>' for h in b["head"])
        rows = "".join("<tr>" + "".join(f'<td style="{S["td"]}">{inline(c)}</td>' for c in r) + "</tr>" for r in b["rows"])
        return f'<table style="border-collapse:collapse;width:100%;margin:0 0 18px"><tr>{head}</tr>{rows}</table>'
    if t == "link":
        return (f'<p style="{S["p"]}"><a href="{html.escape(b["url"])}" '
                f'style="font-size:16px;font-weight:bold;color:#1b2c40;text-decoration:underline">{html.escape(b["text"])}</a></p>')
    raise PostError(f"알 수 없는 블록 종류: {t}")


def make_images(folder: Path, post: dict[str, Any], preview: Path | None) -> None:
    for i, im in enumerate(post["images"], 1):
        out = folder / im["file"]
        kind = im["kind"]
        if kind == "thumbnail":
            thumbnail(out, im.get("kicker", "각종서식 작성하기"), im["title"], im["subtitle"], preview)
        elif kind == "annotate":
            if not preview:
                raise PostError("annotate 사진에는 서식 미리보기 이미지가 필요합니다")
            markers = [Marker(m["no"], m["x"], m["y"], box=tuple(m["box"]) if m.get("box") else None) for m in im["markers"]]
            annotate(out, preview, markers, im.get("caption", "작성 예시 — 이름·날짜·연락처는 모두 가상의 값입니다"))
        elif kind == "compare":
            compare(out, im["title"], im["left"], im["right"], [tuple(r) for r in im["rows"]], im.get("note", ""))
        elif kind == "checklist":
            checklist(out, im["title"], im["items"], im.get("footer", "각종서식 작성하기"))
        else:
            raise PostError(f"알 수 없는 사진 종류: {kind}")
        if not out.exists():
            raise PostError(f"사진 생성 실패: {out.name}")


def check(post: dict[str, Any], body_html: str) -> tuple[int, list[str]]:
    errs: list[str] = []
    plain = re.sub(r"<[^>]+>", "", re.sub(r"\[사진 넣기\][^<]*", "", body_html))
    chars = len(re.sub(r"\s", "", html.unescape(plain)))
    if not BODY_MIN <= chars <= BODY_MAX:
        errs.append(f"본문 {chars}자 — {BODY_MIN}~{BODY_MAX}자")
    if post.get("category") not in CATEGORIES:
        errs.append(f"category 는 {CATEGORIES} 중 하나")
    if not 25 <= len(post.get("title", "")) <= 40:
        errs.append(f"제목 {len(post.get('title', ''))}자 — 25~40자")
    if not 8 <= len(post.get("tags", [])) <= 10:
        errs.append("태그 8~10개")
    blocks = post["blocks"]
    links = [b for b in blocks if b["t"] == "link"]
    if len(links) > 1:
        errs.append("외부 링크는 1개만")
    if links and blocks[-1]["t"] != "link":
        errs.append("링크는 글 맨 끝에만")
    if links and "utm_source=naver" not in links[0]["url"]:
        errs.append("링크에 UTM(utm_source=naver) 누락")
    n_img = [b["n"] for b in blocks if b["t"] == "img"]
    if sorted(n_img) != list(range(1, len(post["images"]) + 1)):
        errs.append(f"사진 자리 {n_img} 와 사진 {len(post['images'])}장이 맞지 않음")
    if len(post["images"]) < 4:
        errs.append("사진 4장 이상")
    if blocks[0].get("t") != "img" or blocks[1].get("t") != "summary":
        errs.append("첫 블록은 대표 사진, 둘째는 요약 상자")
    if not any(b.get("id") == "exp" for b in blocks):
        errs.append("경험 문단(id: exp) 누락")
    joined = " ".join(b.get("text", "") for b in blocks)
    for bad in ("알아보겠습니다", "도움이 되셨길", "도움이 되셨으면"):
        if bad in joined:
            errs.append(f"상투 문장 '{bad}'")
    return chars, errs


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>블로그 초안 — {title}</title>
<style>
body{{margin:0;background:#eef1f5;font-family:"Malgun Gothic","Noto Sans KR",sans-serif;color:#1f2937}}
.wrap{{max-width:1180px;margin:0 auto;padding:24px 16px;display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:20px}}
@media (max-width:900px){{.wrap{{grid-template-columns:1fr}}}}
.panel{{background:#fff;border:1px solid #d6dde6;border-radius:10px;padding:18px}}
.side{{position:sticky;top:16px;align-self:start}}
.side h3{{margin:18px 0 8px;font-size:14px;color:#1b2c40}} .side h3:first-child{{margin-top:0}}
.btn{{display:block;width:100%;padding:12px;border:0;border-radius:8px;background:#e8590c;color:#fff;font-size:15px;font-weight:700;cursor:pointer;margin:0 0 8px}}
.btn.sub{{background:#1b2c40}}
.meta{{font-size:13px;line-height:1.7;color:#475467}}
.imgs img{{width:100%;border:1px solid #d6dde6;border-radius:6px;margin:4px 0 2px}}
.imgs div{{font-size:12px;color:#475467;margin:0 0 10px}}
.toast{{font-size:13px;color:#146c43;min-height:18px}}
#post{{max-width:760px;margin:0 auto}}
.title{{font-size:26px;font-weight:800;color:#1b2c40;margin:0 0 6px}}
.hint{{font-size:13px;color:#6b7280;margin:0 0 18px;border-bottom:1px dashed #cfd8e3;padding-bottom:12px}}
</style></head><body>
<div class="wrap">
 <div class="panel">
  <p class="title" id="ttl">{title}</p>
  <p class="hint">발행 예정일 {date} · ↓ 점선 아래가 본문입니다. 오른쪽 <b>[본문 복사]</b>를 누르고 네이버 블로그 글쓰기 본문에 붙여넣으세요.</p>
  <div id="post">{body}</div>
 </div>
 <aside class="panel side">
  <h3>1. 복사</h3>
  <button class="btn" id="cp-post">본문 복사</button>
  <button class="btn sub" id="cp-title">제목 복사</button>
  <button class="btn sub" id="cp-tags">태그 복사</button>
  <p class="toast" id="toast"></p>
  <h3>2. 발행 정보</h3>
  <div class="meta">카테고리: <b>{category}</b><br>본문 글자 수(공백 제외): <b>{chars:,}자</b><br>외부 링크: {links}<br>태그: {tags_view}</div>
  <h3>3. 사진 넣기 (순서대로)</h3>
  <div class="imgs">{imgs}</div>
  <h3>4. 발행 전 체크</h3>
  <div class="meta">
   ☐ [사진 넣기] 줄을 모두 지우고 그 자리에 사진을 넣었다<br>
   ☐ 01 사진을 대표 사진으로 지정했다<br>
   ☐ <b>경험 문단</b>을 내 말투로 고쳤다 <a href="#" id="go-exp">[위치 보기]</a><br>
   <span style="font-size:12px;color:#6b7280">요약 상자 바로 아래 문단 — 버튼을 누르면 노란 테두리로 표시됩니다</span><br>
   ☐ 모바일 미리보기에서 표가 깨지지 않는다<br>
   ☐ 카테고리 선택 · 태그 붙여넣기 · 공개 설정 확인
  </div>
 </aside>
</div>
<script>
function toast(m) {{ var t = document.getElementById('toast'); t.textContent = m; setTimeout(function(){{ t.textContent = ''; }}, 2500); }}
function copyNode(node) {{ var r = document.createRange(); r.selectNodeContents(node); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); var ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }} s.removeAllRanges(); return ok; }}
function copyText(text) {{ var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); var ok = false; try {{ ok = document.execCommand('copy'); }} catch (e) {{ ok = false; }} document.body.removeChild(ta); return ok; }}
document.getElementById('go-exp').onclick = function (e) {{ e.preventDefault(); var el = document.getElementById('exp'); el.scrollIntoView({{behavior: 'smooth', block: 'center'}}); el.style.outline = '3px solid #fab005'; setTimeout(function () {{ el.style.outline = ''; }}, 3000); }};
document.getElementById('cp-post').onclick = function () {{ toast(copyNode(document.getElementById('post')) ? '본문을 복사했습니다 — 블로그 본문에 붙여넣기(Ctrl+V)' : '복사 실패 — 본문을 드래그해 Ctrl+C 하세요'); }};
document.getElementById('cp-title').onclick = function () {{ toast(copyText(document.getElementById('ttl').textContent) ? '제목을 복사했습니다' : '복사 실패'); }};
document.getElementById('cp-tags').onclick = function () {{ toast(copyText({tags_js}) ? '태그를 복사했습니다' : '복사 실패'); }};
</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="블로그 초안 빌드")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--preview", type=Path, help="서식 미리보기 이미지 (기본: 폴더의 _preview.webp)")
    args = ap.parse_args()

    try:
        post: dict[str, Any] = json.loads((args.folder / "post.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[블로그] post.json 없음: {args.folder}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[블로그] post.json 형식 오류: {exc}", file=sys.stderr)
        return 2

    try:
        body = "\n".join(render_block(b, post["images"]) for b in post["blocks"])
        chars, errs = check(post, body)
    except (KeyError, IndexError, ValueError, PostError) as exc:
        print(f"[블로그] 블록 오류: {exc!r}", file=sys.stderr)
        return 2
    for e in errs:
        print(f"[블로그] 규칙 위반: {e}", file=sys.stderr)
    print(f"[블로그] {post.get('date')} {post.get('form_id')} · 본문 {chars}자 · 사진 {len(post['images'])}장 · 위반 {len(errs)}건")
    if args.check or errs:
        return 1 if errs else 0

    preview = args.preview or (args.folder / "_preview.webp")
    try:
        make_images(args.folder, post, preview if preview.exists() else None)
    except (PostError, OSError) as exc:
        print(f"[블로그] 사진 오류: {exc}", file=sys.stderr)
        return 1
    links = [b for b in post["blocks"] if b["t"] == "link"]
    page = PAGE.format(
        title=html.escape(post["title"]), date=post["date"], body=body, category=html.escape(post["category"]),
        chars=chars, links="1개 (글 맨 끝, UTM 포함)" if links else "없음 (링크 없는 회차)",
        tags_view=" ".join("#" + html.escape(t) for t in post["tags"]),
        imgs="".join(f'<img src="{html.escape(i["file"])}" alt=""><div>{html.escape(i["file"])}{" — 대표 사진으로 지정" if n == 0 else ""}</div>'
                     for n, i in enumerate(post["images"])),
        tags_js=json.dumps(" ".join(post["tags"]), ensure_ascii=False),
    )
    (args.folder / "post.html").write_text(page, encoding="utf-8")
    print(f"[블로그] 완료: {args.folder / 'post.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
