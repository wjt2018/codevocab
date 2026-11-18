"""
生成插件商店图标 images/icon.png（128×128）。

用法：python scripts/make_icon.py
需要 Pillow（pip install pillow）。先在 4 倍尺寸上绘制再缩小，边缘更平滑。
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 128
SCALE = 4
S = SIZE * SCALE
OUT = Path(__file__).resolve().parent.parent / "images" / "icon.png"

TOP = (37, 99, 235)  # 蓝
BOTTOM = (124, 58, 237)  # 紫
WHITE = (255, 255, 255, 255)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
MONO_CANDIDATES = [
    "C:/Windows/Fonts/consolab.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]


def load_font(candidates, size):
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def main():
    # 渐变背景
    gradient = Image.new("RGBA", (S, S))
    draw = ImageDraw.Draw(gradient)
    for y in range(S):
        t = y / (S - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
        draw.line([(0, y), (S, y)], fill=color + (255,))

    # 圆角遮罩
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=S * 0.22, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(gradient, (0, 0), mask)
    draw = ImageDraw.Draw(icon)

    # 上方的 </>：代表写代码
    mono = load_font(MONO_CANDIDATES, int(S * 0.17))
    draw.text((S * 0.50, S * 0.25), "</>", font=mono, fill=(255, 255, 255, 200), anchor="mm")

    # 中间的 Aa：代表单词
    bold = load_font(FONT_CANDIDATES, int(S * 0.40))
    draw.text((S * 0.38, S * 0.63), "Aa", font=bold, fill=WHITE, anchor="mm")

    # 右侧的声波：代表朗读
    cx, cy = S * 0.60, S * 0.63
    for i, r in enumerate((0.09, 0.15, 0.21)):
        rad = S * r
        box = [cx - rad + S * 0.04, cy - rad, cx + rad + S * 0.04, cy + rad]
        draw.arc(box, start=-45, end=45, fill=(255, 255, 255, 255 - i * 50), width=int(S * 0.028))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    icon.resize((SIZE, SIZE), Image.LANCZOS).save(OUT)
    print(f"已生成 {OUT}")


if __name__ == "__main__":
    main()
