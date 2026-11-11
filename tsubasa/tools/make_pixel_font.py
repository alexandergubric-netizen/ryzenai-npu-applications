"""Builds web/fonts/tsubasa-bitmap.ttf: an original 5×7 pixel font for the Bitmap (1-bit retro) theme.

Every glyph is drawn here as rows of '#' (ink) and '.' (paper); accented letters (Slovak, Czech, German) are built
from a base letter plus an accent. The font is written as a plain TrueType file with the standard library only:
each run of ink pixels in a row becomes one rectangle. One pixel is 125 units on a 1000-unit em, so at 16 px a
font pixel is exactly 2 screen pixels and edges stay sharp.   Run:  .venv\\Scripts\\python.exe tools\\make_pixel_font.py
"""
import struct
import sys
import time
from pathlib import Path

PX, EM, ASCENT, DESCENT = 125, 1000, 9 * 125, 2 * 125
NAME = "Tsubasa Bitmap"

# 7 rows above the baseline (top first), optionally 2 more below it (descenders).
G = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".####"],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"],
    "J": ["..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "#.#.#", ".#.#."],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "a": [".....", ".....", ".###.", "....#", ".####", "#...#", ".####"],
    "b": ["#....", "#....", "####.", "#...#", "#...#", "#...#", "####."],
    "c": ["....", "....", ".###", "#...", "#...", "#...", ".###"],
    "d": ["....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"],
    "e": [".....", ".....", ".###.", "#...#", "#####", "#....", ".###."],
    "f": ["..##", ".#..", "###.", ".#..", ".#..", ".#..", ".#.."],
    "g": [".....", ".....", ".####", "#...#", "#...#", "#...#", ".####", "....#", ".###."],
    "h": ["#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"],
    "i": ["#", ".", "#", "#", "#", "#", "#"],
    "j": ["..#", "...", "..#", "..#", "..#", "..#", "..#", "#.#", ".#."],
    "k": ["#...", "#...", "#..#", "#.#.", "##..", "#.#.", "#..#"],
    "l": ["#", "#", "#", "#", "#", "#", "#"],
    "m": [".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"],
    "n": [".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "p": [".....", ".....", "####.", "#...#", "#...#", "#...#", "####.", "#....", "#...."],
    "q": [".....", ".....", ".####", "#...#", "#...#", "#...#", ".####", "....#", "....#"],
    "r": ["....", "....", "#.##", "##..", "#...", "#...", "#..."],
    "s": ["....", "....", ".###", "#...", ".##.", "...#", "###."],
    "t": [".#..", ".#..", "####", ".#..", ".#..", ".#..", "..##"],
    "u": [".....", ".....", "#...#", "#...#", "#...#", "#...#", ".####"],
    "v": [".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "w": [".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."],
    "x": [".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"],
    "y": [".....", ".....", "#...#", "#...#", "#...#", "#...#", ".####", "....#", ".###."],
    "z": [".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": [".#.", "##.", ".#.", ".#.", ".#.", ".#.", "###"],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    "!": ["#", "#", "#", "#", "#", ".", "#"],
    '"': ["#.#", "#.#", "...", "...", "...", "...", "..."],
    "#": [".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."],
    "$": ["..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."],
    "%": ["##...", "##..#", "...#.", "..#..", ".#...", "#..##", "...##"],
    "&": [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "'": ["#", "#", ".", ".", ".", ".", "."],
    "(": ["..#", ".#.", "#..", "#..", "#..", ".#.", "..#"],
    ")": ["#..", ".#.", "..#", "..#", "..#", ".#.", "#.."],
    "*": [".....", "..#..", "#.#.#", ".###.", "#.#.#", "..#..", "....."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    ",": ["..", "..", "..", "..", "..", ".#", ".#", "#."],
    "-": ["....", "....", "....", "####", "....", "....", "...."],
    ".": [".", ".", ".", ".", ".", ".", "#"],
    "/": ["....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."],
    ":": [".", ".", "#", ".", ".", ".", "#"],
    ";": ["..", "..", ".#", "..", "..", ".#", ".#", "#."],
    "<": ["...#", "..#.", ".#..", "#...", ".#..", "..#.", "...#"],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    ">": ["#...", ".#..", "..#.", "...#", "..#.", ".#..", "#..."],
    "?": [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    "@": [".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".####"],
    "[": ["##", "#.", "#.", "#.", "#.", "#.", "##"],
    "\\": ["#....", "#....", ".#...", "..#..", "...#.", "....#", "....#"],
    "]": ["##", ".#", ".#", ".#", ".#", ".#", "##"],
    "^": ["..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    "`": ["#.", ".#", "..", "..", "..", "..", ".."],
    "{": ["..#", ".#.", ".#.", "#..", ".#.", ".#.", "..#"],
    "|": ["#", "#", "#", "#", "#", "#", "#", "#"],
    "}": ["#..", ".#.", ".#.", "..#", ".#.", ".#.", "#.."],
    "~": [".....", ".....", ".#...", "#.#.#", "...#.", ".....", "....."],
    "–": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "—": ["......", "......", "......", "######", "......", "......", "......"],
    "…": [".....", ".....", ".....", ".....", ".....", ".....", "#.#.#"],
    "‘": [".#", "#.", "..", "..", "..", "..", ".."],
    "’": [".#", "#.", "..", "..", "..", "..", ".."],
    "“": [".#.#", "#.#.", "....", "....", "....", "....", "...."],
    "”": [".#.#", "#.#.", "....", "....", "....", "....", "...."],
    "„": ["....", "....", "....", "....", "....", ".#.#", "#.#."],
    "•": ["...", "...", ".#.", "###", ".#.", "...", "..."],
    "·": [".", ".", ".", "#", ".", ".", "."],
    "°": ["###", "#.#", "###", "...", "...", "...", "..."],
    "×": [".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "....."],
    "÷": [".....", "..#..", ".....", "#####", ".....", "..#..", "....."],
    "€": [".###.", "#....", "####.", "#....", "####.", "#....", ".###."],
    "→": [".....", "...#.", "....#", "#####", "....#", "...#.", "....."],
    "←": [".....", ".#...", "#....", "#####", "#....", ".#...", "....."],
    "✓": [".....", "....#", "...#.", "#.#..", ".#...", ".....", "....."],
    "✕": [".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "....."],
    "ß": [".##.", "#..#", "#.#.", "#..#", "#..#", "#.#.", "#.#."],
    "ı": [".", ".", "#", "#", "#", "#", "#"],
}
ACCENT = {"acute": ["..#", ".#."], "grave": ["#..", ".#."], "caron": ["#.#", ".#."], "circ": [".#.", "#.#"],
          "uml": ["#.#", "..."], "ring": [".#.", "#.#"]}
COMPOSED = {
    "á": ("a", "acute"), "ä": ("a", "uml"), "č": ("c", "caron"), "é": ("e", "acute"), "ě": ("e", "caron"),
    "í": ("ı", "acute"), "ĺ": ("l", "acute"), "ó": ("o", "acute"), "ô": ("o", "circ"), "ö": ("o", "uml"),
    "ŕ": ("r", "acute"), "ř": ("r", "caron"), "š": ("s", "caron"), "ú": ("u", "acute"), "ů": ("u", "ring"),
    "ü": ("u", "uml"), "ý": ("y", "acute"), "ž": ("z", "caron"), "ň": ("n", "caron"), "à": ("a", "grave"),
    "è": ("e", "grave"), "â": ("a", "circ"), "ê": ("e", "circ"), "ë": ("e", "uml"), "ï": ("ı", "uml"),
    "Á": ("A", "acute"), "Ä": ("A", "uml"), "Č": ("C", "caron"), "Ď": ("D", "caron"), "É": ("E", "acute"),
    "Ě": ("E", "caron"), "Í": ("I", "acute"), "Ĺ": ("L", "acute"), "Ň": ("N", "caron"), "Ó": ("O", "acute"),
    "Ô": ("O", "circ"), "Ö": ("O", "uml"), "Ŕ": ("R", "acute"), "Ř": ("R", "caron"), "Š": ("S", "caron"),
    "Ť": ("T", "caron"), "Ú": ("U", "acute"), "Ů": ("U", "ring"), "Ü": ("U", "uml"), "Ý": ("Y", "acute"),
    "Ž": ("Z", "caron"), "À": ("A", "grave"), "È": ("E", "grave"),
}
# Slovak/Czech letters whose caron is a small apostrophe beside the stem.
BESIDE = {"ď": "d", "ť": "t", "ľ": "l", "Ľ": "L"}


def rows_of(glyph):
    """(width, {y: row string}) with y=0 the baseline row, 6 the cap top, -1/-2 descenders, 7/8 accents."""
    w = max(len(r) for r in glyph)
    out = {}
    for i, r in enumerate(glyph):
        out[6 - i] = r.ljust(w, ".")
    return w, out


def compose(base, accent):
    w, rows = rows_of(G[base])
    acc = ACCENT[accent]
    tall = any("#" in rows.get(y, "") for y in (5, 6))      # capitals and ascenders: accent goes above the cap
    top = 8 if tall else 6
    aw = len(acc[0])
    nw = max(w, aw)
    bo, ao = (nw - w) // 2, (nw - aw) // 2
    out = {y: ("." * bo + r + "." * nw)[:nw] for y, r in rows.items()}
    for k, line in enumerate(acc):
        y = top - k
        cur = list(out.get(y, "." * nw))
        for j, ch in enumerate(line):
            if ch == "#":
                cur[ao + j] = "#"
        out[y] = "".join(cur)
    return nw, out


def beside(base):
    w, rows = rows_of(G[base])
    nw = w + 2
    out = {y: r + ".." for y, r in rows.items()}
    for y in (6, 5):
        out[y] = out[y][:w + 1] + "#"
    return nw, out


def rects(rows):
    """Ink runs per row as (x0, y0, x1, y1) font units; vertically equal runs merge into taller rectangles."""
    runs = {}
    for y, r in rows.items():
        x = 0
        while x < len(r):
            if r[x] == "#":
                s = x
                while x < len(r) and r[x] == "#":
                    x += 1
                runs.setdefault((s, x), []).append(y)
            else:
                x += 1
    out = []
    for (s, e), ys in runs.items():
        ys.sort()
        start = prev = ys[0]
        for y in ys[1:] + [None]:
            if y is not None and y == prev + 1:
                prev = y
                continue
            out.append((s * PX, start * PX, e * PX, (prev + 1) * PX))
            if y is not None:
                start = prev = y
    return out


def glyph_data(boxes):
    if not boxes:
        return b"", (0, 0, 0, 0), 0, 0
    pts, ends = [], []
    for x0, y0, x1, y1 in boxes:                     # clockwise in y-up coordinates = filled
        pts += [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]
        ends.append(len(pts) - 1)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    data = struct.pack(">hhhhh", len(ends), *bbox) + struct.pack(f">{len(ends)}H", *ends) + struct.pack(">H", 0)
    data += bytes([0x01]) * len(pts)                   # on-curve, 16-bit deltas
    px = py = 0
    xd, yd = b"", b""
    for x, y in pts:
        xd += struct.pack(">h", x - px)
        yd += struct.pack(">h", y - py)
        px, py = x, y
    data += xd + yd
    if len(data) % 4:
        data += b"\0" * (4 - len(data) % 4)
    return data, bbox, len(pts), len(ends)


def checksum(data):
    data += b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def build():
    chars = {" ": (3, {})}
    for ch, g in G.items():
        chars[ch] = rows_of(g)
    for ch, (b, a) in COMPOSED.items():
        chars[ch] = compose(b, a)
    for ch, b in BESIDE.items():
        chars[ch] = beside(b)
    order = sorted(chars, key=ord)
    glyphs = [(None, glyph_data(rects({6 - i: r for i, r in enumerate(["####", "#..#", "#..#", "#..#", "#..#", "#..#", "####"])})), 5 * PX)]
    for ch in order:
        w, rows = chars[ch]
        glyphs.append((ch, glyph_data(rects(rows)), (w + 1) * PX if ch != " " else 4 * PX))
    glyf, loca = b"", [0]
    for _, (data, *_), _ in glyphs:
        glyf += data
        loca.append(len(glyf))
    n = len(glyphs)
    bboxes = [g[1][1] for g in glyphs if g[1][0]]
    xmin, ymin = min(b[0] for b in bboxes), min(b[1] for b in bboxes)
    xmax, ymax = max(b[2] for b in bboxes), max(b[3] for b in bboxes)
    adv = [g[2] for g in glyphs]
    lsb = [g[1][1][0] for g in glyphs]
    now = int(time.time()) + 2082844800
    head = struct.pack(">IIIIHHqqhhhhHHhhh", 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x000B, EM, now, now,
                       xmin, ymin, xmax, ymax, 0, 8, 2, 1, 0)
    hhea = struct.pack(">IhhhHhhhhhhhhhhhH", 0x00010000, ASCENT, -DESCENT, 0, max(adv), min(lsb),
                       min(a - g[1][1][2] for a, g in zip(adv, glyphs) if g[1][0]), xmax, 1, 0, 0, 0, 0, 0, 0, 0, n)
    maxp = struct.pack(">IHHHHHHHHHHHHHH", 0x00010000, n, max(g[1][2] for g in glyphs), max(g[1][3] for g in glyphs),
                       0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0)
    hmtx = b"".join(struct.pack(">Hh", a, l) for a, l in zip(adv, lsb))
    codes = [ord(c) for c in order]
    first, last = min(codes), max(c for c in codes if c < 0xFFFF)
    # OS/2 version 4 (96 bytes): sub/superscript sizes, strikeout, family class, panose, ranges, metrics.
    os2 = struct.pack(">HhHHHhhhhhhhhhhh10sIIIIIHHHhhhHHIIhhHHH",
                      4, sum(adv) // n, 400, 5, 0, 650, 600, 0, 75, 650, 600, 0, 350, 62, 250, 0,
                      bytes([2, 0, 6, 9, 0, 0, 0, 0, 0, 0]), 0x00000007, 0, 0, 0, int.from_bytes(b"TSBS", "big"),
                      0x0040, first, last, ASCENT, -DESCENT, 0, ASCENT, DESCENT, 0x00000003, 0, 5 * PX, 7 * PX, 0, 32, 1)
    # cmap format 4: one segment per code point (simple and valid), plus the 0xFFFF end segment.
    segs = [(c, c, (i + 1 - c) & 0xFFFF) for i, c in enumerate(codes)] + [(0xFFFF, 0xFFFF, 1)]
    sc = len(segs)
    search = 2 ** (sc.bit_length() - 1) * 2
    f4 = struct.pack(">HHHHHHH", 4, 0, 0, sc * 2, search, (search // 2).bit_length() - 1, sc * 2 - search)
    f4 += b"".join(struct.pack(">H", e) for _, e, _ in segs) + b"\0\0"
    f4 += b"".join(struct.pack(">H", s) for s, _, _ in segs)
    f4 += b"".join(struct.pack(">H", d) for _, _, d in segs)
    f4 += b"\0\0" * sc
    f4 = f4[:2] + struct.pack(">H", len(f4)) + f4[4:]
    cmap = struct.pack(">HHHHI", 0, 1, 3, 1, 12) + f4
    names = {1: NAME, 2: "Regular", 3: NAME + " 1.0", 4: NAME, 5: "Version 1.0", 6: "TsubasaBitmap-Regular"}
    recs, strs = b"", b""
    for nid, s in names.items():
        enc = s.encode("utf-16-be")
        recs += struct.pack(">HHHHHH", 3, 1, 0x409, nid, len(enc), len(strs))
        strs += enc
    name = struct.pack(">HHH", 0, len(names), 6 + 12 * len(names)) + recs + strs
    post = struct.pack(">IIhhIIIII", 0x00030000, 0, -75, 50, 0, 0, 0, 0, 0)
    loca_t = b"".join(struct.pack(">I", o) for o in loca)
    tables = {b"OS/2": os2, b"cmap": cmap, b"glyf": glyf, b"head": head, b"hhea": hhea, b"hmtx": hmtx,
              b"loca": loca_t, b"maxp": maxp, b"name": name, b"post": post}
    tags = sorted(tables)
    nt = len(tags)
    es = 2 ** (nt.bit_length() - 1)
    out = struct.pack(">IHHHH", 0x00010000, nt, es * 16, es.bit_length() - 1, nt * 16 - es * 16)
    offset = 12 + 16 * nt
    body = b""
    for t in tags:
        d = tables[t]
        out += struct.pack(">4sIII", t, checksum(d), offset + len(body), len(d))
        body += d + b"\0" * (-len(d) % 4)
    font = bytearray(out + body)
    adj = (0xB1B0AFBA - checksum(bytes(font))) & 0xFFFFFFFF
    head_off = offset + sum(len(tables[t]) + (-len(tables[t]) % 4) for t in tags[:tags.index(b"head")])
    font[head_off + 8:head_off + 12] = struct.pack(">I", adj)
    return bytes(font), len(order)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "web" / "fonts" / "tsubasa-bitmap.ttf"
    out.parent.mkdir(parents=True, exist_ok=True)
    data, count = build()
    out.write_bytes(data)
    print(f"wrote {out} ({len(data):,} bytes, {count} characters)")


if __name__ == "__main__":
    main()
