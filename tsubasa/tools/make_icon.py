"""Builds web/tsubasa.ico from the same shapes as web/bird.svg (ember tile, cream bird), with no image libraries.

Each size is drawn with an exact span rasteriser (8 sub-rows per pixel, fractional span ends), so edges stay smooth
at 16 px and 256 px alike. Run:  .venv\\Scripts\\python.exe tools\\make_icon.py
"""
import math
import struct
import sys
import zlib
from pathlib import Path

TILE = [(0.0, (0xF1, 0xA0, 0x6F)), (0.55, (0xD9, 0x69, 0x3E)), (1.0, (0x8F, 0x3A, 0x20))]
WING = [(0.0, (0xFF, 0xF8, 0xF0)), (1.0, (0xFF, 0xE3, 0xCF))]
# The bird from bird.svg (viewBox 0 0 64 64): four cubic curves.
CURVES = [((8, 23), (18, 24), (25, 28), (32, 36)), ((32, 36), (39, 28), (46, 24), (56, 23)),
          ((56, 23), (47, 32), (39, 31), (32, 44)), ((32, 44), (25, 31), (17, 32), (8, 23))]
SIZES = (256, 128, 64, 48, 40, 32, 24, 20, 16)
SUB = 8


def ramp(stops, t):
    t = min(1.0, max(0.0, t))
    for (a, ca), (b, cb) in zip(stops, stops[1:]):
        if t <= b:
            k = (t - a) / (b - a)
            return tuple(ca[i] + (cb[i] - ca[i]) * k for i in range(3))
    return stops[-1][1]


def polygon(scale):
    pts = []
    for p0, p1, p2, p3 in CURVES:
        for i in range(48):
            t = i / 48
            u = 1 - t
            pts.append(tuple((u**3 * p0[k] + 3 * u * u * t * p1[k] + 3 * u * t * t * p2[k] + t**3 * p3[k]) * scale
                             for k in (0, 1)))
    return pts


def spans_add(row, x0, x1, weight):
    """Adds horizontal coverage of [x0, x1) to one pixel row, with fractional ends."""
    n = len(row)
    x0, x1 = max(0.0, x0), min(float(n), x1)
    if x1 <= x0:
        return
    i0, i1 = int(x0), int(math.ceil(x1)) - 1
    if i0 == i1:
        row[i0] += (x1 - x0) * weight
        return
    row[i0] += (i0 + 1 - x0) * weight
    for i in range(i0 + 1, i1):
        row[i] += weight
    row[i1] += (x1 - i1) * weight


def render(size, bird_scale=1.0):
    s = size / 64
    tile = [[0.0] * size for _ in range(size)]
    wing = [[0.0] * size for _ in range(size)]
    r = 16 * s
    # Small icons get a slightly larger, centred bird so it does not vanish at 16 px.
    cx, cy = 32 * s, 33.5 * s
    poly = [(cx + (x - cx) * bird_scale, cy + (y - cy) * bird_scale) for x, y in polygon(s)]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    for py in range(size):
        for k in range(SUB):
            y = py + (k + 0.5) / SUB
            # rounded square
            if y < r:
                dx = r - math.sqrt(max(0.0, r * r - (r - y) ** 2))
            elif y > size - r:
                dx = r - math.sqrt(max(0.0, r * r - (y - (size - r)) ** 2))
            else:
                dx = 0.0
            spans_add(tile[py], dx, size - dx, 1 / SUB)
            # bird (even-odd)
            xs = sorted(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                        for a, b in edges if (a[1] <= y < b[1]) or (b[1] <= y < a[1]))
            for x0, x1 in zip(xs[::2], xs[1::2]):
                spans_add(wing[py], x0, x1, 1 / SUB)
    bx0, by0 = min(p[0] for p in poly), min(p[1] for p in poly)
    bx1, by1 = max(p[0] for p in poly), max(p[1] for p in poly)
    raw = bytearray()
    for py in range(size):
        raw.append(0)
        for px in range(size):
            a = min(1.0, tile[py][px])
            w = min(1.0, wing[py][px])
            t = ((px + 0.5) / size + (py + 0.5) / size) / 2
            base = ramp(TILE, t)
            wc = ramp(WING, (((px + 0.5) - bx0) / (bx1 - bx0) + ((py + 0.5) - by0) / (by1 - by0)) / 2)
            rgb = [wc[i] * w + base[i] * (1 - w) for i in range(3)]
            raw += bytes(int(round(c)) for c in rgb) + bytes([int(round(a * 255))])
    return png(size, bytes(raw))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images):
    head = struct.pack("<HHH", 0, 1, len(images))
    offset, entries, blobs = 6 + 16 * len(images), b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    return head + entries + blobs


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "web" / "tsubasa.ico"
    images = [(n, render(n, 1.0 if n >= 48 else 1.12 if n >= 32 else 1.22 if n >= 20 else 1.32)) for n in SIZES]
    out.write_bytes(ico(images))
    print(f"wrote {out} ({out.stat().st_size:,} bytes, sizes {', '.join(map(str, SIZES))})")


if __name__ == "__main__":
    main()
