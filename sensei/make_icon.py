"""Draws the Sensei logo - a blue tile with a dark prompt chevron and a white cursor - as web/icon.png,
web/logo.svg and sensei.ico, all in the same geometry. Run: python make_icon.py"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
S = 1024
TOP, BOTTOM = (122, 162, 255), (70, 92, 230)
INK = (13, 21, 48, 255)
WHITE = (255, 255, 255, 255)
W = 92                               # stroke width of the chevron and the cursor

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#7AA2FF"/><stop offset="1" stop-color="#465CE6"/>
    </linearGradient>
  </defs>
  <rect class="tile" x="40" y="40" width="944" height="944" rx="230" fill="url(#tile)"/>
  <path class="chev" d="M 270 330 L 470 512 L 270 694" fill="none" stroke="#0D1530" stroke-width="92"
        stroke-linecap="round" stroke-linejoin="round"/>
  <rect class="cursor" x="540" y="650" width="240" height="92" rx="46" fill="#FFFFFF"/>
</svg>
"""


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    for y in range(S):
        t = y / (S - 1)
        grad.paste(tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,), (0, y, S, y + 1))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.line([(270, 330), (470, 512), (270, 694)], fill=INK, width=W, joint="curve")
    for x, y in [(270, 330), (270, 694), (470, 512)]:
        d.ellipse((x - W / 2, y - W / 2, x + W / 2, y + W / 2), fill=INK)
    d.rounded_rectangle((540, 650, 780, 650 + W), radius=W // 2, fill=WHITE)
    return img


if __name__ == "__main__":
    img = draw()
    img.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "web", "icon.png"))
    img.save(os.path.join(HERE, "sensei.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    with open(os.path.join(HERE, "web", "logo.svg"), "w", encoding="utf-8") as f:
        f.write(SVG)
    print("logo written")
