"""미리보기 예시에 쓰는 정적 이미지 생성기.

현재는 증명사진 자리에 넣는 실루엣 1종만 만든다. 실제 인물 사진을 쓰지 않으므로
초상권·저작권 문제가 없고, 사용자는 '여기에 사진이 들어간다'를 한눈에 알 수 있다.

사용법:
    python scripts/make_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# 3×4cm 증명사진 비율 (가로:세로 = 3:4)
W, H = 360, 480
BG = (238, 242, 247)        # 아주 연한 회청 배경
FIGURE = (150, 165, 182)    # 실루엣 (중간 톤 슬레이트)
BORDER = (201, 210, 221)    # 얇은 테두리


def make_photo_sample(out_path: Path) -> Path:
    """증명사진 실루엣 PNG를 만든다."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 머리: 지름이 가로폭의 약 44%가 되도록 (증명사진 표준 구도에 가깝게)
    head_d = int(W * 0.44)
    head_x = (W - head_d) // 2
    head_y = int(H * 0.20)
    d.ellipse([head_x, head_y, head_x + head_d, head_y + head_d], fill=FIGURE)

    # 어깨: 아래쪽이 잘린 큰 타원으로 상반신을 표현
    body_w = int(W * 0.78)
    body_h = int(H * 0.52)
    body_x = (W - body_w) // 2
    body_y = head_y + head_d + int(H * 0.045)
    d.ellipse([body_x, body_y, body_x + body_w, body_y + body_h * 2], fill=FIGURE)

    # 테두리 (이미지 경계가 셀 선과 겹쳐 보이지 않도록 안쪽에 1px)
    d.rectangle([0, 0, W - 1, H - 1], outline=BORDER, width=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path


def main() -> int:
    """엔트리포인트."""
    path = make_photo_sample(ASSETS / "photo-sample.png")
    print(f"[자산] 생성 완료: {path} ({path.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
