"""Draws the Tansu icon - a kaidan-tansu (staircase chest) with coloured drawers - as web/icon.png and tansu.ico.

Same geometry as the logo in web/app.js (logoSVG). Run once: python make_icon.py
"""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024
K = 4                      # supersampling
W = S * K

# logo geometry in a 100x100 box (shared with the UI)
FRAME = [(6, 14, 40, 45), (6, 40, 68, 71), (6, 66, 96, 96)]
DRAWERS = [  # x0, y0, x1, y1, colour
    (10, 18, 36, 41, "#ef5a3c"),
    (10, 44, 36, 67, "#f4a52b"), (39, 44, 64, 67, "#3fb27f"),
    (10, 70, 36, 92, "#4a90e2"), (39, 70, 64, 92, "#9a5bd1"), (67, 70, 92, 92, "#1fb5b0"),
]
BOX = (150, 150, 874, 874)          # where the 100x100 logo sits on the tile


def P(x, y):
    return BOX[0] + (BOX[2] - BOX[0]) * x / 100 * 1.0, BOX[1] + (BOX[3] - BOX[1]) * y / 100


def R(x0, y0, x1, y1):
    a, b = P(x0, y0), P(x1, y1)
    return [a[0] * K, a[1] * K, b[0] * K, b[1] * K]


U = (BOX[2] - BOX[0]) / 100 * K   # one logo unit in supersampled pixels


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def lighten(rgb, f):
    return tuple(min(255, int(c + (255 - c) * f)) for c in rgb[:3]) + (255,)


def darken(rgb, f):
    return tuple(int(c * (1 - f)) for c in rgb[:3]) + (255,)


def vgrad(size, top, bottom):
    g = Image.linear_gradient("L").resize(size)
    a = Image.new("RGBA", size, top)
    b = Image.new("RGBA", size, bottom)
    return Image.composite(b, a, g)


def tile():
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((36 * K, 36 * K, W - 36 * K, W - 36 * K), radius=228 * K, fill=255)
    bg = vgrad((W, W), hexrgb("#1f3157"), hexrgb("#0b1222"))
    # warm glow behind the chest
    glow = Image.new("L", (W, W), 0)
    ImageDraw.Draw(glow).ellipse((260 * K, 300 * K, 820 * K, 900 * K), fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(150 * K))
    bg = Image.composite(Image.new("RGBA", (W, W), hexrgb("#f4a52b")), bg, glow.point(lambda v: v * 0.35))
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    # glossy top edge
    hl = Image.new("L", (W, W), 0)
    ImageDraw.Draw(hl).ellipse((-300 * K, -700 * K, W + 300 * K, 420 * K), fill=26)
    out.paste(Image.new("RGBA", (W, W), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(hl, mask))
    return out, mask


def rounded(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(8):
        a = math.pi / 4 * i - math.pi / 2
        rr = r if i % 2 == 0 else r * 0.28
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def draw():
    img, mask = tile()
    # shadow under the chest
    sh = Image.new("L", (W, W), 0)
    x0, y0, x1, y1 = R(4, 92, 98, 100)
    ImageDraw.Draw(sh).rounded_rectangle((x0, y0, x1, y1), radius=4 * U, fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(5 * U))
    img.paste(Image.new("RGBA", (W, W), (0, 0, 0, 255)), (0, 0), ImageChops.multiply(sh, mask))

    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # a sheet of paper peeking out of the top drawer
    paper = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    pd = ImageDraw.Draw(paper)
    rounded(pd, R(14, 3, 31, 24), 1.6 * U, (250, 246, 238, 255))
    for i, yy in enumerate((7.5, 10.5, 13.5)):
        pd.rounded_rectangle(R(17, yy, 28 - (i == 2) * 4, yy + 1.2), radius=0.6 * U, fill=(196, 188, 176, 255))
    cx, cy = P(22.5, 14)
    paper = paper.rotate(9, center=(cx * K, cy * K), resample=Image.BICUBIC)
    layer.alpha_composite(paper)
    d = ImageDraw.Draw(layer)
    # the frame (light paulownia wood), with a darker rim for depth
    for f in FRAME:
        rounded(d, R(f[0] - .6, f[1] - .6, f[2] + .6, f[3] + .6), 5.6 * U, hexrgb("#c9b48f"))
    for f in FRAME:
        rounded(d, R(*f), 5 * U, hexrgb("#f1e6d2"))
    # drawers
    for x0, y0, x1, y1, col in DRAWERS:
        c = hexrgb(col)
        box = R(x0, y0, x1, y1)
        d.rounded_rectangle((box[0] - .5 * U, box[1] - .5 * U, box[2] + .5 * U, box[3] + .5 * U), radius=3 * U,
                            fill=darken(c, .35)[:3] + (90,))
        dm = Image.new("L", (W, W), 0)
        ImageDraw.Draw(dm).rounded_rectangle(box, radius=2.6 * U, fill=255)
        layer.paste(vgrad((W, W), lighten(c, .2), darken(c, .1)).crop((0, 0, W, W)), (0, 0), dm)
        d = ImageDraw.Draw(layer)
        # brass pull
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + .5
        d.rounded_rectangle(R(mx - 5.2, my - 1.9, mx + 5.2, my + 1.9), radius=1.9 * U, fill=hexrgb("#7a5a26"))
        d.rounded_rectangle(R(mx - 4.6, my - 1.5, mx + 4.6, my + 1.3), radius=1.5 * U, fill=hexrgb("#f0cf86"))
        d.rounded_rectangle(R(mx - 3.8, my - 1.2, mx + 3.8, my - .3), radius=.5 * U, fill=hexrgb("#fff1cc"))
    # AI sparkles in the empty corner
    for (sx, sy, sr, col) in ((80, 25, 9.5, "#ffe3a3"), (91.5, 41, 4.2, "#ffffff"), (70, 41, 2.8, "#9cc9ff")):
        gl = Image.new("L", (W, W), 0)
        cx, cy = P(sx, sy)
        ImageDraw.Draw(gl).ellipse((cx * K - sr * U * 1.6, cy * K - sr * U * 1.6, cx * K + sr * U * 1.6, cy * K + sr * U * 1.6), fill=110)
        gl = gl.filter(ImageFilter.GaussianBlur(sr * U * .7))
        layer.paste(Image.new("RGBA", (W, W), hexrgb(col)), (0, 0), ImageChops.multiply(gl, Image.new("L", (W, W), 255)).point(lambda v: v * .55))
        d = ImageDraw.Draw(layer)
        star(d, cx * K, cy * K, sr * U, hexrgb(col))
    img.alpha_composite(layer)
    return img.resize((S, S), Image.LANCZOS)


if __name__ == "__main__":
    img = draw()
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "web", "icon.png"))
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(HERE, "web", "icon512.png"))
    img.save(os.path.join(HERE, "tansu.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
