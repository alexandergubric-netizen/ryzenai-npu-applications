"""Draws tatami.ico (and web/icon.png) in the same geometry as logoSVG() in web/colors.js.

A 4½-mat tatami room seen from above: four mats pinwheel around a half mat, each mat a file-type colour, bound by
dark-green heri on the floor. Run: python make_icon.py
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
BG = (47, 74, 58)
MATS = [  # x, y, w, h, colour (123-unit grid, same as the SVG)
    (4, 4, 74, 37, (229, 72, 77)),
    (82, 4, 37, 74, (62, 99, 221)),
    (45, 82, 74, 37, (48, 164, 108)),
    (4, 45, 37, 74, (245, 184, 46)),
    (45, 45, 33, 33, (201, 178, 124)),
]


def draw(size):
    ss = 8 if size <= 64 else 4            # supersample, then downscale for clean edges
    S = size * ss
    k = S / 123.0
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    over = Image.new("RGBA", (S, S), (0, 0, 0, 0))   # translucent details, composited at the end
    d = ImageDraw.Draw(img)
    o = ImageDraw.Draw(over)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=14 * k, fill=BG)
    small = size < 32
    for x, y, w, h, c in MATS:
        if small:  # widen mats so the gaps stay ~1 px at 16-24 px
            x, y, w, h = x - 1, y - 1, w + 2, h + 2
        box = [x * k, y * k, (x + w) * k - 1, (y + h) * k - 1]
        d.rounded_rectangle(box, radius=3 * k, fill=c)
        if size >= 48:
            # inner highlight (the woven edge) and two weave lines along the mat
            inset = 2.5 * k
            o.rounded_rectangle([box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset], radius=1.5 * k,
                                outline=(255, 255, 255, 72), width=max(1, int(k)))
            line = (0, 0, 0, 30)
            if w > h:
                for f in (1 / 3, 2 / 3):
                    yy = (y + h * f) * k
                    o.line([(x + 6) * k, yy, (x + w - 6) * k, yy], fill=line, width=max(1, int(k)))
            else:
                for f in (1 / 3, 2 / 3):
                    xx = (x + w * f) * k
                    o.line([xx, (y + 6) * k, xx, (y + h - 6) * k], fill=line, width=max(1, int(k)))
    img = Image.alpha_composite(img, over)
    return img.resize((size, size), Image.LANCZOS)


def main():
    imgs = [draw(s) for s in SIZES]
    ico = os.path.join(HERE, "tatami.ico")
    imgs[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES], append_images=imgs[:-1])
    draw(256).save(os.path.join(HERE, "web", "icon.png"))
    print("wrote", ico)


if __name__ == "__main__":
    main()
