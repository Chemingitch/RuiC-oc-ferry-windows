# -*- coding: utf-8 -*-
"""生成 OC Ferry Deployer 应用图标（六边形徽标，与界面 logo 同源）。"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

SS = 1024                      # 超采样尺寸，保证缩放后边缘干净
HERE = os.path.dirname(os.path.abspath(__file__))
ICO = os.path.join(HERE, "app.ico")
PREVIEW = os.path.join(HERE, "icon-preview.png")

CYAN = (0, 229, 255)
EDGE = (127, 234, 255)
BG = (10, 15, 26)


def hexa(cx, cy, r, rot=-90):
    return [
        (cx + r * math.cos(math.radians(60 * i + rot)),
         cy + r * math.sin(math.radians(60 * i + rot)))
        for i in range(6)
    ]


def build():
    S = SS
    c = S / 2

    # 深色圆角方底（保证在浅色/深色任务栏上都可辨识）
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=BG + (255,)
    )

    outer = hexa(c, c, S * 0.365)

    # 外发光
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(outer, outline=CYAN + (255,), width=int(S * 0.030))
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.038))

    # 主图形
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.polygon(outer, fill=CYAN + (24,), outline=CYAN + (255,), width=int(S * 0.034))

    inner = hexa(c, c, S * 0.218)
    d.polygon(inner, fill=EDGE + (30,), outline=EDGE + (230,), width=int(S * 0.019))

    r_dot = S * 0.070
    d.ellipse([c - r_dot, c - r_dot, c + r_dot, c + r_dot], fill=CYAN + (255,))

    out = Image.alpha_composite(base, glow)
    out = Image.alpha_composite(out, layer)
    return out


def main():
    img = build().resize((256, 256), Image.LANCZOS)
    img.save(ICO, format="ICO",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    img.save(PREVIEW)
    print("ICO     ", ICO, os.path.getsize(ICO), "bytes")
    print("PREVIEW ", PREVIEW)


if __name__ == "__main__":
    main()
