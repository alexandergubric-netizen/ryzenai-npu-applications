"""Minimalist icon concepts for Kaizen 5S. Each function returns a 1024px RGBA image."""
from PIL import Image, ImageDraw, ImageFont

S = 1024
INK, PAPER, RED = (28, 27, 25, 255), (245, 243, 238, 255), (200, 70, 61, 255)
FONTS = r"C:\Windows\Fonts"


def _tile(color):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=color)
    return img, d


def bars():
    """Five bars, sorted short to long: Seiri/Seiton at a glance."""
    img, d = _tile(PAPER)
    left, h, gap = 262, 52, 46
    top = (S - (5 * h + 4 * gap)) / 2
    for i, length in enumerate((200, 300, 400, 500, 500)):
        y = top + i * (h + gap)
        d.rounded_rectangle((left, y, left + length, y + h), radius=h / 2, fill=RED if i == 4 else INK)
    return img


def grid():
    """Four squares in perfect order, one marked."""
    img, d = _tile(INK)
    size, gap = 190, 64
    x0 = (S - (2 * size + gap)) / 2
    for r in range(2):
        for c in range(2):
            x, y = x0 + c * (size + gap), x0 + r * (size + gap)
            d.rounded_rectangle((x, y, x + size, y + size), radius=40, fill=RED if (r, c) == (1, 1) else PAPER)
    return img


def kanji(weight="L"):
    """整 (sei) - 'order', the first character of Seiri and Seiton. weight: L light, M medium (small sizes)."""
    img, d = _tile(INK)
    font = ImageFont.truetype(FONTS + rf"\YuGoth{weight}.ttc", 560)
    d.text((S / 2, S / 2 + 10), "整", font=font, fill=PAPER, anchor="mm")
    return img


def fives():
    """A plain 5S wordmark."""
    img, d = _tile(INK)
    font = ImageFont.truetype(FONTS + r"\segoeuil.ttf", 470)
    d.text((S / 2, S / 2 - 20), "5S", font=font, fill=PAPER, anchor="mm")
    return img


DESIGNS = {"A · Sorted bars": bars, "B · Order grid": grid, "C · Kanji “order”": kanji, "D · 5S wordmark": fives}
