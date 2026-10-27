"""Draws the Postura icons in the same geometry as logoSVG() in web/logo.js (100-unit grid).

Postura is the word for posture in Latin, Spanish, Italian, Portuguese and Polish. The logo is a bamboo stalk — straight and segmented like a healthy spine — on a
rounded-square tile. Sky-blue tile with an amber sun.

Run: python make_icon.py  → build/<edition>/postura.ico, tray.ico, icon.png
"""
import os
from PIL import Image, ImageChops, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SS = 1024  # supersampled canvas
K = SS / 100

EDITIONS = {
    "public": dict(bg_top=(108, 184, 255), bg_bot=(47, 111, 219), sun=(255, 198, 92), stalk=(59, 178, 115),
                   hi=(140, 222, 172), node=(24, 110, 66), leaf1=(76, 195, 127), leaf2=(46, 154, 95), bands=None),
}


def p(x, y):
    return (x * K, y * K)


def quad(a, c, b, n=24):
    out = []
    for i in range(n + 1):
        t = i / n
        x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0]
        y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]
        out.append(p(x, y))
    return out


def leaf(base, tip, w):
    """Same as leafPath() in logo.js: two quadratic curves bulging either side of the base→tip line."""
    mx, my = (base[0] + tip[0]) / 2, (base[1] + tip[1]) / 2
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    ln = (dx * dx + dy * dy) ** 0.5
    nx, ny = -dy / ln * w, dx / ln * w
    return quad(base, (mx + nx, my + ny), tip) + quad(tip, (mx - nx, my - ny), base)[1:]


def draw(ed, simple=False):
    c = EDITIONS[ed]
    img = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
    # tile with a vertical gradient
    grad = Image.new("RGBA", (SS, SS))
    gd = ImageDraw.Draw(grad)
    for y in range(SS):
        t = y / (SS - 1)
        gd.line([(0, y), (SS, y)], fill=tuple(int(c["bg_top"][i] + (c["bg_bot"][i] - c["bg_top"][i]) * t) for i in range(3)) + (255,))
    mask = Image.new("L", (SS, SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle([p(4, 4), p(96, 96)], radius=22 * K, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if c["bands"]:
        layer = Image.new("RGBA", (SS, SS), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for col, pts in c["bands"]:
            # white gap along the diagonal edge, as on the cover art (half of it stays visible)
            ld.line([p(*pts[0]), p(*pts[2])], fill=(255, 255, 255, 255), width=int(4 * K))
            ld.polygon([p(*q) for q in pts], fill=col + (255,))
        img.paste(layer, (0, 0), ImageChops.multiply(layer.getchannel("A"), mask))
        d = ImageDraw.Draw(img)
    if c["sun"] and not simple:
        d.ellipse([p(56, 15), p(86, 45)], fill=c["sun"] + (70,))
        d.ellipse([p(61, 20), p(81, 40)], fill=c["sun"] + (255,))
    if not simple:
        d.polygon(leaf((55, 41), (79, 50), 7), fill=c["leaf1"] + (255,))
        d.polygon(leaf((43, 61), (22, 54), 6.5), fill=c["leaf2"] + (255,))
    # stalk, its highlight and the nodes (vertebrae)
    x0, x1 = (41, 57) if simple else (43, 55)
    d.rounded_rectangle([p(x0, 18), p(x1, 86)], radius=(x1 - x0) / 2 * K, fill=c["stalk"] + (255,))
    d.rounded_rectangle([p(x0 + 3, 24), p(x0 + 5.5, 80)], radius=1.25 * K, fill=c["hi"] + (255,))
    for y in (39, 60):
        d.rounded_rectangle([p(x0 - 2, y), p(x1 + 2, y + 4)], radius=2 * K, fill=c["node"] + (255,))
    return img


def main():
    for ed in EDITIONS:
        out = os.path.join(HERE, "build", ed)
        os.makedirs(out, exist_ok=True)
        full, simple = draw(ed), draw(ed, simple=True)
        imgs = [(simple if s <= 24 else full).resize((s, s), Image.LANCZOS) for s in SIZES]
        imgs[-1].save(os.path.join(out, "postura.ico"), format="ICO", sizes=[(s, s) for s in SIZES], append_images=imgs[:-1])
        tray = [(simple if s <= 32 else full).resize((s, s), Image.LANCZOS) for s in (16, 20, 24, 32, 40, 48, 64)]
        tray[-1].save(os.path.join(out, "tray.ico"), format="ICO", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64)], append_images=tray[:-1])
        full.resize((256, 256), Image.LANCZOS).save(os.path.join(out, "icon.png"))
        print("icons for", ed, "->", out)


if __name__ == "__main__":
    main()
