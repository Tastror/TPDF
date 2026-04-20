"""TPDF 图标生成器。

用 PIL 程序化绘制，然后保存多种尺寸：
    icon/TPDF.ico     Windows 多尺寸
    icon/TPDF.icns    macOS 多尺寸
    icon/TPDF.png     canonical 256 px PNG（用于 Tk iconphoto）
    icon/TPDF_{16,32,48,64,128,256,512}.png

执行：
    uv run python icon/generate_icon.py
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SIZES = [16, 32, 48, 64, 128, 256, 512]
ICO_SIZES = [16, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512]

OUT = Path(__file__).parent

# 设计色板（与 UI 的 COLOR_ACCENT 保持一致）
BLUE_MAIN = (37, 99, 235)      # #2563eb
BLUE_DEEP = (29, 78, 216)      # #1d4ed8
WHITE = (255, 255, 255)


def find_bold_font() -> str | None:
    """在当前系统寻找一款粗体无衬线字体。"""
    candidates = [
        # Windows
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def draw_icon(size: int) -> Image.Image:
    """在目标尺寸下绘制图标；内部 4 倍超采样再降采样得到锯齿平滑的结果。

    设计：
    - 圆角蓝色底板（#2563eb）
    - 上半部分叠一层淡白色高光，营造轻微立体感
    - 居中的白色大 "T"，略微抬高以便视觉居中
    - 底部一条白色细线条 + 小号 "PDF" 标签，暗示"文档"
    """
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── 圆角蓝色底板 ──────────────────────────
    radius = int(s * 0.22)
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BLUE_MAIN)

    # 上半部分淡白色高光
    highlight = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(highlight)
    hdraw.rounded_rectangle(
        [0, 0, s - 1, int(s * 0.55)], radius=radius,
        fill=(255, 255, 255, 26),
    )
    img = Image.alpha_composite(img, highlight)
    draw = ImageDraw.Draw(img)

    # ── 居中白色 "T"（大号、粗体、略上移） ───
    font_path = find_bold_font()
    big_px = int(s * 0.56)
    small_px = int(s * 0.17)
    if font_path:
        try:
            font_big = ImageFont.truetype(font_path, big_px)
            font_small = ImageFont.truetype(font_path, small_px)
        except Exception:
            font_big = font_small = ImageFont.load_default()
    else:
        font_big = font_small = ImageFont.load_default()

    text = "T"
    bbox = draw.textbbox((0, 0), text, font=font_big)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (s - w) / 2 - bbox[0]
    y = int(s * 0.18) - bbox[1]  # 向上靠，给底部的装饰留空间
    draw.text((x, y), text, font=font_big, fill=WHITE)

    # ── 底部装饰：细白线 + 小号 "PDF" 标签 ───
    # 大尺寸下才画（小尺寸 PDF 字会糊）；16~48 只保留大 T 更清晰
    if size >= 48:
        # 装饰线
        line_y = int(s * 0.76)
        line_half = int(s * 0.22)
        line_thick = max(2, int(s * 0.013))
        draw.rounded_rectangle(
            [s // 2 - line_half, line_y - line_thick // 2,
             s // 2 + line_half, line_y + line_thick // 2],
            radius=line_thick // 2, fill=(255, 255, 255, 180),
        )
        # PDF 标签
        label = "PDF"
        lbb = draw.textbbox((0, 0), label, font=font_small)
        lw = lbb[2] - lbb[0]
        lh = lbb[3] - lbb[1]
        draw.text(
            ((s - lw) / 2 - lbb[0], int(s * 0.80) - lbb[1]),
            label, font=font_small, fill=(255, 255, 255, 235),
        )

    # ── 降采样到目标尺寸 ───────────────────
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    print(f"→ 输出目录：{OUT}")
    pngs: dict[int, Image.Image] = {}
    for size in SIZES:
        im = draw_icon(size)
        pngs[size] = im
        p = OUT / f"TPDF_{size}.png"
        im.save(p, "PNG", optimize=True)
        print(f"   {p.name:18s}  {p.stat().st_size / 1024:.1f} KB")

    # canonical 256 PNG
    canonical = OUT / "TPDF.png"
    pngs[256].save(canonical, "PNG", optimize=True)
    print(f"   {canonical.name:18s}  {canonical.stat().st_size / 1024:.1f} KB")

    # Windows ICO
    ico = OUT / "TPDF.ico"
    pngs[256].save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print(f"   {ico.name:18s}  {ico.stat().st_size / 1024:.1f} KB")

    # macOS ICNS
    icns = OUT / "TPDF.icns"
    try:
        # Pillow 会把 base image + append_images 打包到 ICNS
        extras = [pngs[s] for s in ICNS_SIZES if s != 512]
        pngs[512].save(icns, format="ICNS", append_images=extras)
        print(f"   {icns.name:18s}  {icns.stat().st_size / 1024:.1f} KB")
    except Exception as e:
        print(f"   TPDF.icns 保存失败（macOS 外可忽略）：{e}")

    print("\n✓ 完成")


if __name__ == "__main__":
    main()
