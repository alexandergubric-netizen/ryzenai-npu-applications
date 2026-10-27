"""Renders all icon concepts side by side into icon-options.png (large and at real taskbar size)."""
import os

from PIL import Image, ImageDraw, ImageFont

from icon_designs import DESIGNS

here = os.path.dirname(os.path.abspath(__file__))
tile, small, pad = 240, 32, 40
W = pad + len(DESIGNS) * (tile + pad)
sheet = Image.new("RGB", (W, tile + 150), (233, 231, 225))
d = ImageDraw.Draw(sheet)
font = ImageFont.truetype(r"C:\Windows\Fonts\seguisb.ttf", 22)
for i, (label, fn) in enumerate(DESIGNS.items()):
    big = fn()
    x = pad + i * (tile + pad)
    sheet.paste(big.resize((tile, tile), Image.LANCZOS), (x, pad), big.resize((tile, tile), Image.LANCZOS))
    s = big.resize((small, small), Image.LANCZOS)
    sheet.paste(s, (x, pad + tile + 20), s)
    d.text((x + small + 12, pad + tile + 26), label, font=font, fill=(28, 27, 25))
sheet.save(os.path.join(here, "icon-options.png"))
print("written")
