"""Write the largest picture inside an .ico as a PNG (mac/build_app.sh turns it into Tsubasa.icns with sips/iconutil).

    python3 mac/make_icns.py web/tsubasa.ico out.png
"""
import struct
import sys


def largest_png(ico):
    data = open(ico, "rb").read()
    _, kind, count = struct.unpack_from("<HHH", data, 0)
    if kind != 1:
        raise SystemExit("not an .ico file")
    best = None
    for i in range(count):
        w, h, _, _, _, _, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + i * 16)
        blob = data[offset:offset + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n" and (best is None or (w or 256) > best[0]):
            best = (w or 256, blob)
    if not best:
        raise SystemExit("the .ico holds no PNG picture")
    return best[1]


if __name__ == "__main__":
    open(sys.argv[2], "wb").write(largest_png(sys.argv[1]))
