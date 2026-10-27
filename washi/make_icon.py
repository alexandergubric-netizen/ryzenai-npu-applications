"""Draws the Washi icon - a sheet of washi paper with a folded corner, indigo / matcha / gold brush strokes and a
vermilion hanko seal on a deep indigo tile - as washi.ico and web/icon.png.

Same geometry as logoSVG() in web/icons.js (100x100 box). Run once: python make_icon.py
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024
K = 4
W = S * K
BOX = (120, 112, 904, 896)          # where the 100x100 logo sits on the tile
U = (BOX[2] - BOX[0]) / 100 * K


def P(x, y):
    return (BOX[0] + (BOX[2] - BOX[0]) * x / 100) * K, (BOX[1] + (BOX[3] - BOX[1]) * y / 100) * K


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def vgrad(size, top, bottom):
    g = Image.linear_gradient("L").resize(size)
    return Image.composite(Image.new("RGBA", size, bottom), Image.new("RGBA", size, top), g)


def bezier(p0, p1, p2, p3, n=80):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t ** 2
        d = t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def brush(d, pts, width, color, taper=True):
    """A brush stroke: round dots along the path, slightly thinner at the ends like ink."""
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        t = i / (n - 1)
        w = width * (0.55 + 0.45 * min(1, t * 4, (1 - t) * 3)) if taper else width
        X, Y = P(x, y)
        r = w / 2 * U
        d.ellipse((X - r, Y - r, X + r, Y + r), fill=color)


def rotate_pts(pts, cx, cy, deg):
    import math
    a = math.radians(deg)
    return [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a), cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in pts]


def tile():
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle((36 * K, 36 * K, W - 36 * K, W - 36 * K), radius=230 * K, fill=255)
    bg = vgrad((W, W), hexrgb("#2f4b8f"), hexrgb("#121c3a"))
    glow = Image.new("L", (W, W), 0)
    ImageDraw.Draw(glow).ellipse((200 * K, 220 * K, 860 * K, 900 * K), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(160 * K))
    bg = Image.composite(Image.new("RGBA", (W, W), hexrgb("#e0a526")), bg, glow.point(lambda v: v * 0.28))
    out = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    out.paste(bg, (0, 0), mask)
    hl = Image.new("L", (W, W), 0)
    ImageDraw.Draw(hl).ellipse((-300 * K, -700 * K, W + 300 * K, 420 * K), fill=24)
    out.paste(Image.new("RGBA", (W, W), (255, 255, 255, 255)), (0, 0), ImageChops.multiply(hl, mask))
    return out, mask


def draw():
    img, mask = tile()
    # soft shadow under the sheet
    sh = Image.new("L", (W, W), 0)
    ImageDraw.Draw(sh).rounded_rectangle((*P(23, 13), *P(83, 95)), radius=4 * U, fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(4 * U))
    img.paste(Image.new("RGBA", (W, W), (5, 8, 20, 255)), (0, 0), ImageChops.multiply(sh, mask))

    # the sheet with its folded corner
    sheet = Image.new("L", (W, W), 0)
    sd = ImageDraw.Draw(sheet)
    sd.rounded_rectangle((*P(21, 9), *P(80, 91)), radius=3 * U, fill=255)
    sd.polygon([P(63, 8), P(81, 8), P(81, 26)], fill=0)
    paper = vgrad((W, W), hexrgb("#fffaf0"), hexrgb("#efe3c8"))
    img.paste(paper, (0, 0), sheet)
    d = ImageDraw.Draw(img)
    # washi fibres
    for (a, b, c, e) in (((27, 20), (31, 21.5), (37, 21), (42, 19)), ((45, 31), (48, 30), (53, 30.5), (57, 33)),
                         ((28, 77), (32, 78.5), (37, 78), (41, 75.5)), ((66, 34), (68, 35), (72, 35), (75, 33.5))):
        brush(d, bezier(a, b, c, e, 30), 0.55, hexrgb("#dccfb0"), taper=False)
    # fold
    d.polygon([P(63, 9), P(63, 23), P(66, 26), P(80, 26)], fill=hexrgb("#e2d2ae"))
    d.line([P(63, 9), P(80, 26)], fill=hexrgb("#cdbf9f"), width=int(0.8 * U))
    # ink strokes
    brush(d, bezier((29, 47), (38, 41), (52, 44), (72, 39)), 7, hexrgb("#27407a"))
    brush(d, bezier((30, 59), (40, 56), (50, 58), (61, 55)), 4, hexrgb("#7aa33c"))
    brush(d, bezier((30, 68), (36, 67), (41, 68), (47, 66)), 3, hexrgb("#e0a526"))
    # hanko seal (rotated -6 degrees around its centre)
    seal = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(seal)
    sdraw.rounded_rectangle((*P(56, 63), *P(78, 85)), radius=4 * U, fill=hexrgb("#e2452f"))
    w_pts = [(60.5, 69), (63.8, 80), (67, 72.5), (70.2, 80), (73.5, 69)]
    for a, b in zip(w_pts, w_pts[1:]):
        seg = [(a[0] + (b[0] - a[0]) * t / 20, a[1] + (b[1] - a[1]) * t / 20) for t in range(21)]
        brush(sdraw, seg, 2.4, hexrgb("#fff6ee"), taper=False)
    cx, cy = P(67, 74)
    seal = seal.rotate(6, center=(cx, cy), resample=Image.BICUBIC)
    img.alpha_composite(seal)
    return img.resize((S, S), Image.LANCZOS)


if __name__ == "__main__":
    img = draw()
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "web", "icon.png"))
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(HERE, "web", "icon512.png"))
    img.save(os.path.join(HERE, "washi.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
