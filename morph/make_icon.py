"""Draws the Morph icon (web/icon.png and morph.ico). Run once: python make_icon.py"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024


def blob_mask():
    """A soft organic blob (same idea as the animated logo)."""
    pts = []
    for i in range(360):
        a = math.radians(i)
        r = 400 + 26 * math.sin(3 * a + 0.6) + 18 * math.cos(2 * a - 0.4)
        pts.append((S / 2 + r * math.cos(a), S / 2 + r * math.sin(a)))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.filter(ImageFilter.GaussianBlur(1.5))


def draw():
    grad = Image.new("RGBA", (S, S))
    a, b = (123, 108, 255), (47, 198, 181)
    px = grad.load()
    for y in range(S):
        for x in range(S):
            t = min(max((x * 0.75 + y * 0.45) / (S * 1.2), 0), 1)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), blob_mask())
    d = ImageDraw.Draw(img)
    w = 70
    box = (S / 2 - 210, S / 2 - 210, S / 2 + 210, S / 2 + 210)
    d.arc(box, 200, 330, fill="white", width=w)   # two arrows chasing each other = conversion
    d.arc(box, 20, 150, fill="white", width=w)
    for ang, sign in ((330, 1), (150, 1)):
        r = 210 - w / 2
        cx, cy = S / 2 + r * math.cos(math.radians(ang)), S / 2 + r * math.sin(math.radians(ang))
        t = math.radians(ang + 90 * sign)
        tip = (cx + 70 * math.cos(t), cy + 70 * math.sin(t))
        n = math.radians(ang)
        left = (cx + 70 * math.cos(n), cy + 70 * math.sin(n))
        right = (cx - 70 * math.cos(n), cy - 70 * math.sin(n))
        d.polygon([tip, left, right], fill="white")
    return img


if __name__ == "__main__":
    img = draw()
    os.makedirs(os.path.join(HERE, "web"), exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "web", "icon.png"))
    img.save(os.path.join(HERE, "morph.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
