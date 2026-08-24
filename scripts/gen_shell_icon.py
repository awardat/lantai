"""生成兰台桌面壳图标（shell/icons/）：藏青渐变圆角方块 + 白色「兰」字。

输出：icon.ico（16/24/32/48/64/128/256 多尺寸）、icon.png（512）、
32x32.png、128x128.png、128x128@2x.png（Tauri 默认图标集）、
ui 启动页 logo.png（256）。

用法：python scripts/gen_shell_icon.py
依赖：Pillow（backend/requirements.txt 已含）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SHELL_ROOT = Path(__file__).resolve().parent.parent / "shell"
ICONS_DIR = SHELL_ROOT / "src-tauri" / "icons"
PUBLIC_DIR = SHELL_ROOT / "ui" / "public"

TOP = (24, 51, 94)      # 藏青
BOTTOM = (13, 27, 51)   # 深藏青
CHAR = "兰"
FG = (245, 246, 250)


def font_for(px: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, px)
    raise FileNotFoundError("未找到中文字体（msyh/simhei/simsun）")


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.20
    # 垂直渐变圆角方块
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(size - 1, 1)
        c = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (size, y)], fill=c)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    # 「兰」字居中
    f = font_for(int(size * 0.60))
    d = ImageDraw.Draw(img)
    bbox = d.textbbox((0, 0), CHAR, font=f)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    d.text((x, y), CHAR, font=f, fill=FG)
    return img


def main() -> int:
    if not ICONS_DIR.is_dir():
        print(f"错误：{ICONS_DIR} 不存在（先复制壳工程）", file=sys.stderr)
        return 1
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    base = draw_icon(512)
    # ico 多尺寸
    base.save(ICONS_DIR / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    base.save(ICONS_DIR / "icon.png")
    draw_icon(32).save(ICONS_DIR / "32x32.png")
    draw_icon(128).save(ICONS_DIR / "128x128.png")
    draw_icon(256).save(ICONS_DIR / "128x128@2x.png")
    draw_icon(256).save(PUBLIC_DIR / "logo.png")
    print("图标已生成：", ICONS_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
