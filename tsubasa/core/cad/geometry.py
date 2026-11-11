"""Meshes for the CAD interpreter: OpenSCAD primitives, transforms, extrusions, convex hulls, STL and print stats.

Solids are lists of csg.Polygon (planar, outward normals). 2D shapes stay a small tree of point loops until they
are extruded: extrusion distributes over union/difference/intersection, so every 2D leaf becomes a prism (or a
revolved ring) and the same boolean tree is applied to the results, which keeps the geometry exact.
"""
import math
import struct

from core.cad.csg import Polygon, bbox, union, difference, intersection, cross, sub, dot

FN_DEFAULT, FA_DEFAULT, FS_DEFAULT = 0, 12.0, 2.0


class CadError(ValueError):
    pass


def fragments(r, fn=0, fa=FA_DEFAULT, fs=FS_DEFAULT):
    """Segments for a circle of radius r, as OpenSCAD computes them from $fn, $fa and $fs."""
    if r < 1e-6:
        return 3
    if fn and fn > 0:
        return max(int(fn), 3)
    return max(int(math.ceil(max(min(360.0 / max(fa, 0.01), r * 2 * math.pi / max(fs, 0.01)), 5))), 3)


# ---------------------------------------------------------------------------------------------- 3D primitives
def orient(polys):
    """Make normals point outward (positive signed volume)."""
    if volume(polys) < 0:
        return [p.flipped() for p in polys]
    return polys


def cube(size, center=False):
    x, y, z = size
    if min(x, y, z) <= 0:
        return []
    ox, oy, oz = (-x / 2, -y / 2, -z / 2) if center else (0, 0, 0)
    c = [(ox + i * x, oy + j * y, oz + k * z) for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return [Polygon([c[i] for i in f]) for f in faces]


def cylinder(h, r1, r2, center, n):
    if h <= 0 or (r1 <= 0 and r2 <= 0):
        return []
    z0 = -h / 2 if center else 0.0
    z1 = z0 + h
    ring = lambda r, z: [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
    bot, top = ring(r1, z0), ring(r2, z1)
    polys = []
    if r1 > 0:
        polys.append(Polygon(bot[::-1]))
    if r2 > 0:
        polys.append(Polygon(top))
    for i in range(n):
        j = (i + 1) % n
        if r1 > 0 and r2 > 0:
            polys.append(Polygon([bot[i], bot[j], top[j], top[i]]))
        elif r1 > 0:
            polys.append(Polygon([bot[i], bot[j], (0.0, 0.0, z1)]))
        else:
            polys.append(Polygon([(0.0, 0.0, z0), top[j], top[i]]))
    return polys


def sphere(r, n):
    if r <= 0:
        return []
    rings = max((n + 1) // 2, 2)
    pts = []
    for i in range(rings):
        phi = math.pi * (i + 0.5) / rings
        z, rr = r * math.cos(phi), r * math.sin(phi)
        pts.append([(rr * math.cos(2 * math.pi * k / n), rr * math.sin(2 * math.pi * k / n), z) for k in range(n)])
    polys = [Polygon(pts[0]), Polygon(pts[-1][::-1])]
    for i in range(rings - 1):
        a, b = pts[i], pts[i + 1]
        for k in range(n):
            m = (k + 1) % n
            polys.append(Polygon([a[k], b[k], b[m], a[m]]))
    return orient(polys)


def polyhedron(points, faces):
    try:
        pts = [tuple(float(c) for c in p[:3]) for p in points]
        polys = []
        for f in faces:
            vs = [pts[int(i)] for i in f]
            if len(vs) >= 3:
                # OpenSCAD lists faces clockwise seen from outside; ours are counter-clockwise
                for tri in triangulate_3d(vs[::-1]):
                    polys.append(Polygon(tri))
    except (IndexError, TypeError, ValueError) as exc:
        raise CadError(f"polyhedron(): invalid points or faces ({exc})") from exc
    return orient(polys)


def triangulate_3d(vs):
    return [[vs[0], vs[i], vs[i + 1]] for i in range(1, len(vs) - 1)]


# ---------------------------------------------------------------------------------------------- transforms
def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


IDENTITY = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def m_translate(v):
    m = [row[:] for row in IDENTITY]
    m[0][3], m[1][3], m[2][3] = v
    return m


def m_scale(v):
    m = [row[:] for row in IDENTITY]
    m[0][0], m[1][1], m[2][2] = v
    return m


def m_rotate(a, axis=None):
    if axis is not None:
        x, y, z = axis
        length = math.sqrt(x * x + y * y + z * z) or 1.0
        x, y, z = x / length, y / length, z / length
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        t = 1 - c
        return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0],
                [t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0],
                [t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0], [0, 0, 0, 1]]
    ax, ay, az = (math.radians(v) for v in a)
    rx = [[1, 0, 0, 0], [0, math.cos(ax), -math.sin(ax), 0], [0, math.sin(ax), math.cos(ax), 0], [0, 0, 0, 1]]
    ry = [[math.cos(ay), 0, math.sin(ay), 0], [0, 1, 0, 0], [-math.sin(ay), 0, math.cos(ay), 0], [0, 0, 0, 1]]
    rz = [[math.cos(az), -math.sin(az), 0, 0], [math.sin(az), math.cos(az), 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    return mat_mul(rz, mat_mul(ry, rx))   # OpenSCAD applies x, then y, then z


def m_mirror(v):
    x, y, z = v
    length2 = x * x + y * y + z * z
    if length2 == 0:
        return [row[:] for row in IDENTITY]
    x, y, z = (c / math.sqrt(length2) for c in v)
    return [[1 - 2 * x * x, -2 * x * y, -2 * x * z, 0], [-2 * x * y, 1 - 2 * y * y, -2 * y * z, 0],
            [-2 * x * z, -2 * y * z, 1 - 2 * z * z, 0], [0, 0, 0, 1]]


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
            m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def apply(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3], m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def transform(polys, m):
    flip = det3(m) < 0
    out = []
    for p in polys:
        vs = [apply(m, v) for v in p.v]
        out.append(Polygon(vs[::-1] if flip else vs))
    return out


# ---------------------------------------------------------------------------------------------- 2D shapes
class Shape2:
    """A 2D shape tree: ('loop', points) leaves and ('union' | 'difference' | 'intersection', children)."""
    __slots__ = ("op", "data")

    def __init__(self, op, data):
        self.op, self.data = op, data

    def map(self, fn):
        if self.op == "loop":
            return Shape2("loop", [fn(p) for p in self.data])
        return Shape2(self.op, [c.map(fn) for c in self.data])

    def points(self):
        if self.op == "loop":
            return list(self.data)
        return [p for c in self.data for p in c.points()]


def area2(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2


def ccw(pts):
    return pts if area2(pts) >= 0 else pts[::-1]


def square(size, center=False):
    x, y = size
    if x <= 0 or y <= 0:
        return Shape2("union", [])
    ox, oy = (-x / 2, -y / 2) if center else (0.0, 0.0)
    return Shape2("loop", [(ox, oy), (ox + x, oy), (ox + x, oy + y), (ox, oy + y)])


def circle(r, n):
    if r <= 0:
        return Shape2("union", [])
    return Shape2("loop", [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)])


def polygon(points, paths=None):
    try:
        pts = [(float(p[0]), float(p[1])) for p in points]
        if not paths:
            return Shape2("loop", pts)
        loops = [[pts[int(i)] for i in path] for path in paths]
    except (IndexError, TypeError, ValueError) as exc:
        raise CadError(f"polygon(): invalid points or paths ({exc})") from exc
    outer = Shape2("loop", loops[0])
    return Shape2("difference", [outer, *[Shape2("loop", l) for l in loops[1:]]]) if len(loops) > 1 else outer


def hull2(shape):
    pts = sorted(set(shape.points()))
    if len(pts) < 3:
        return Shape2("union", [])
    def half(points):
        h = []
        for p in points:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(p)
        return h
    lower, upper = half(pts), half(pts[::-1])
    return Shape2("loop", lower[:-1] + upper[:-1])


def ear_clip(pts):
    """Triangles of a simple polygon (counter-clockwise points)."""
    pts = ccw([p for i, p in enumerate(pts) if p != pts[i - 1]])
    idx = list(range(len(pts)))
    tris, guard = [], 0
    while len(idx) > 3 and guard < 10 * len(pts):
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            pa, pb, pc = pts[a], pts[b], pts[c]
            if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) <= 1e-12:
                continue
            if any(inside_tri(pts[o], pa, pb, pc) for o in idx if o not in (a, b, c)):
                continue
            tris.append((pa, pb, pc))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(pts[i] for i in idx))
    return tris


def inside_tri(p, a, b, c):
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def prism(loop, z0, z1, twist=0.0, scale=(1.0, 1.0), slices=1):
    pts = ccw(loop)
    if len(pts) < 3 or abs(area2(pts)) < 1e-12:
        return []
    def at(p, k):
        t = k / slices
        a = math.radians(-twist * t)
        sx, sy = 1 + (scale[0] - 1) * t, 1 + (scale[1] - 1) * t
        x, y = p[0] * sx, p[1] * sy
        return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a), z0 + (z1 - z0) * t)
    polys = []
    for tri in ear_clip(pts):
        polys.append(Polygon([at(p, 0) for p in tri[::-1]]))
        if abs(scale[0]) > 1e-9 and abs(scale[1]) > 1e-9:
            polys.append(Polygon([at(p, slices) for p in tri]))
    for k in range(slices):
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            quad = [at(p, k), at(q, k), at(q, k + 1), at(p, k + 1)]
            quad = [v for j, v in enumerate(quad) if v != quad[j - 1]]
            if len(quad) >= 3:
                if twist:
                    polys += [Polygon(t) for t in triangulate_3d(quad)]
                else:
                    polys.append(Polygon(quad))
    return orient(polys)


def revolve(loop, angle, n):
    pts = ccw(loop)
    if min(p[0] for p in pts) < -1e-9:
        if max(p[0] for p in pts) > 1e-9:
            raise CadError("rotate_extrude(): the 2D shape must lie on one side of the Y axis (all x >= 0).")
        pts = ccw([(-x, y) for x, y in pts])
    full = abs(angle) >= 360 - 1e-9
    steps = max(int(math.ceil(n * abs(angle) / 360)), 3)
    def at(p, k):
        a = math.radians(angle * k / steps)
        return (p[0] * math.cos(a), p[0] * math.sin(a), p[1])
    polys = []
    for k in range(steps):
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            quad = [at(p, k), at(q, k), at(q, k + 1), at(p, k + 1)]
            uniq = []   # points on the axis collapse a quad into a triangle
            for v in quad:
                if not any(max(abs(v[c] - u[c]) for c in range(3)) < 1e-9 for u in uniq):
                    uniq.append(v)
            if len(uniq) >= 3:
                polys.append(Polygon(uniq))
    if not full:
        for tri in ear_clip(pts):
            polys.append(Polygon([at(p, 0) for p in tri]))
            polys.append(Polygon([at(p, steps) for p in tri[::-1]]))
    return orient(polys)


def extrude(shape, fn, *args):
    """Apply the shape's boolean tree to the extruded leaves."""
    if shape.op == "loop":
        return fn(shape.data, *args)
    parts = [extrude(c, fn, *args) for c in shape.data]
    return combine(shape.op, parts)


def _touch(a, b):
    return all(a[i] <= b[i + 3] + 1e-6 and b[i] <= a[i + 3] + 1e-6 for i in range(3))


def combine(op, parts, check=None):
    """check() is called between steps (the interpreter's time limit)."""
    parts = [p for p in parts if p]
    if not parts:
        return []
    if op == "union":
        # Solids whose boxes do not touch cannot change each other: keep them as separate groups and run the BSP
        # union only where parts meet. Many separate features (holes, ribs, clips) stay fast.
        groups = []
        for p in parts:
            box = bbox(p)
            hit = [g for g in groups if _touch(g[0], box)]
            merged = list(p)
            for g in hit:
                merged = union(g[1], merged)
            if hit:
                groups = [g for g in groups if not any(g is h for h in hit)]
                box = bbox(merged) if merged else box
            groups.append((box, merged))
            if check:
                check()
        return [poly for g in groups for poly in g[1]]
    out = list(parts[0])
    for p in parts[1:]:
        out = difference(out, p) if op == "difference" else intersection(out, p)
        if check:
            check()
        if not out and op == "intersection":
            break
    return out


# ---------------------------------------------------------------------------------------------- convex hull (3D)
def hull3(points):
    pts = list({(round(p[0], 6), round(p[1], 6), round(p[2], 6)) for p in points})
    if len(pts) < 4:
        return []
    if len(pts) > 6000:
        raise CadError("hull(): too many points (over 6,000); use fewer segments ($fn).")
    a = min(pts)
    b = max(pts, key=lambda p: sum((p[i] - a[i]) ** 2 for i in range(3)))
    ab = sub(b, a)
    c = max(pts, key=lambda p: sum(x * x for x in cross(ab, sub(p, a))))
    nrm = cross(ab, sub(c, a))
    d = max(pts, key=lambda p: abs(dot(nrm, sub(p, a))))
    if abs(dot(nrm, sub(d, a))) < 1e-9:
        raise CadError("hull(): the points are flat; a 3D hull needs depth.")
    faces = [(a, b, c), (a, c, d), (a, d, b), (b, d, c)]
    centre = tuple(sum(v[i] for v in (a, b, c, d)) / 4 for i in range(3))
    def outward(f):
        n = cross(sub(f[1], f[0]), sub(f[2], f[0]))
        return f if dot(n, sub(f[0], centre)) > 0 else (f[0], f[2], f[1])
    faces = [outward(f) for f in faces]
    for p in pts:
        if p in (a, b, c, d):
            continue
        visible = []
        for f in faces:
            n = cross(sub(f[1], f[0]), sub(f[2], f[0]))
            if dot(n, sub(p, f[0])) > 1e-9 * (abs(n[0]) + abs(n[1]) + abs(n[2]) + 1):
                visible.append(f)
        if not visible:
            continue
        edges = {}
        for f in visible:
            for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                edges[e] = edges.get(e, 0) + 1
        horizon = [e for e in edges if (e[1], e[0]) not in edges]
        vis = set(visible)
        faces = [f for f in faces if f not in vis] + [(e[0], e[1], p) for e in horizon]
    return [Polygon(list(f)) for f in faces]


# ---------------------------------------------------------------------------------------------- output
def triangles(polys):
    for p in polys:
        for i in range(1, len(p.v) - 1):
            yield p.v[0], p.v[i], p.v[i + 1], p.n


def volume(polys):
    return sum(dot(a, cross(b, c)) for a, b, c, _ in triangles(polys)) / 6.0


def stl(polys, name="tsubasa"):
    tris = list(triangles(polys))
    out = bytearray(name.encode("ascii", "replace")[:80].ljust(80, b" "))
    out += struct.pack("<I", len(tris))
    for a, b, c, n in tris:
        out += struct.pack("<12fH", *n, *a, *b, *c, 0)
    return bytes(out)


def stats(polys):
    if not polys:
        return {"empty": True}
    xs = [v[0] for p in polys for v in p.v]
    ys = [v[1] for p in polys for v in p.v]
    zs = [v[2] for p in polys for v in p.v]
    zmin = min(zs)
    area = over = 0.0
    tris = 0
    for a, b, c, n in triangles(polys):
        cr = cross(sub(b, a), sub(c, a))
        t = (cr[0] ** 2 + cr[1] ** 2 + cr[2] ** 2) ** 0.5 / 2
        area += t
        tris += 1
        # faces pointing down more steeply than 45° need support, except the ones resting on the bed
        if n[2] < -0.7072 and min(a[2], b[2], c[2]) > zmin + 0.05:
            over += t
    return {"size": [round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - zmin, 3)],
            "min": [round(min(xs), 3), round(min(ys), 3), round(zmin, 3)],
            "volume_mm3": round(abs(volume(polys)), 1), "area_mm2": round(area, 1), "triangles": tris,
            "overhang_mm2": round(over, 1), "overhang_pct": round(100 * over / area, 1) if area else 0}


def mesh_floats(polys):
    """Flat triangle list (x, y, z per vertex) for the viewer."""
    out = []
    for a, b, c, _ in triangles(polys):
        out += [*a, *b, *c]
    return out


# ---------------------------------------------------------------------------------------------- separate pieces
def _on_polygon(p, poly, tol=1e-4):
    if abs(dot(poly.n, p) - poly.w) > tol:
        return False
    vs = poly.v
    for i, a in enumerate(vs):
        b = vs[(i + 1) % len(vs)]
        if dot(cross(sub(b, a), sub(p, a)), poly.n) < -tol:
            return False
    return True


def pieces(polys):
    """The separate solid pieces of a mesh, each as {min, max} (a floating part, or parts that only look joined).

    Polygons are joined when they share a vertex, or when a vertex of one lies on the other: the boolean operations
    leave T-junctions along every seam, so shared vertices alone would split one solid into several."""
    n = len(polys)
    if not n:
        return []
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner = {}
    for i, poly in enumerate(polys):
        for v in poly.v:
            k = (round(v[0], 4), round(v[1], 4), round(v[2], 4))
            j = owner.get(k)
            if j is None:
                owner[k] = i
            else:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    if len({find(i) for i in range(n)}) > 1:
        lo = [min(v[a] for p in polys for v in p.v) for a in range(3)]
        hi = [max(v[a] for p in polys for v in p.v) for a in range(3)]
        cell = max(max(h - l for l, h in zip(lo, hi)) / 40, 0.5)
        grid = {}
        for i, poly in enumerate(polys):
            mn = [int((min(v[a] for v in poly.v) - lo[a]) // cell) for a in range(3)]
            mx = [int((max(v[a] for v in poly.v) - lo[a]) // cell) for a in range(3)]
            for x in range(mn[0], mx[0] + 1):
                for y in range(mn[1], mx[1] + 1):
                    for z in range(mn[2], mx[2] + 1):
                        grid.setdefault((x, y, z), []).append(i)
        for k, i in owner.items():
            c = tuple(int((k[a] - lo[a]) // cell) for a in range(3))
            for j in grid.get(c, ()):
                if find(i) != find(j) and _on_polygon(k, polys[j]):
                    parent[find(i)] = find(j)
    groups = {}
    for i, poly in enumerate(polys):
        g = groups.setdefault(find(i), [[float("inf")] * 3, [float("-inf")] * 3])
        for v in poly.v:
            for a in range(3):
                g[0][a] = min(g[0][a], v[a])
                g[1][a] = max(g[1][a], v[a])
    out = [{"min": [round(x, 2) for x in mn], "max": [round(x, 2) for x in mx]} for mn, mx in groups.values()]
    return sorted(out, key=lambda p: -((p["max"][0] - p["min"][0]) * (p["max"][1] - p["min"][1]) * (p["max"][2] - p["min"][2])))


# ---------------------------------------------------------------------------------------------- print orientation
def _poly_area(p):
    vs, total = p.v, (0.0, 0.0, 0.0)
    for i in range(1, len(vs) - 1):
        c = cross(sub(vs[i], vs[0]), sub(vs[i + 1], vs[0]))
        total = (total[0] + c[0], total[1] + c[1], total[2] + c[2])
    return (total[0] ** 2 + total[1] ** 2 + total[2] ** 2) ** 0.5 / 2


def _to_down(d):
    """A rotation that turns direction d to (0, 0, -1)."""
    t = (0.0, 0.0, -1.0)
    c = dot(d, t)
    if c > 1 - 1e-9:
        return [row[:] for row in IDENTITY]
    if c < -1 + 1e-9:
        return m_rotate((180, 0, 0))
    axis = cross(d, t)
    return m_rotate(math.degrees(math.acos(max(-1.0, min(1.0, c)))), axis)


FACE_NAMES = {(0, 0, -1): "bottom", (0, 0, 1): "top", (1, 0, 0): "+X side", (-1, 0, 0): "−X side",
              (0, 1, 0): "+Y side", (0, -1, 0): "−Y side"}


def lay_flat(polys):
    """Turn the part so it prints well: most bed contact, least overhang, then drop it onto z = 0 centred on the bed.

    The designer models the part as it is used (a wall hook with its back against the wall); this finds the print
    orientation (that hook lying on its back plate). Returns (polygons, note); note is None when it stays as drawn."""
    if not polys:
        return polys, None
    areas = [_poly_area(p) for p in polys]
    clusters = {}
    for p, a in zip(polys, areas):
        k = (round(p.n[0], 3), round(p.n[1], 3), round(p.n[2], 3))
        clusters[k] = clusters.get(k, 0.0) + a
    cands = list(FACE_NAMES) + [k for k, _ in sorted(clusters.items(), key=lambda kv: -kv[1])[:6]]
    seen, best, drawn = set(), None, None
    for d in cands:
        length = (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5 or 1.0
        d = (d[0] / length, d[1] / length, d[2] / length)
        key = tuple(round(c, 2) for c in d)
        if key in seen:
            continue
        seen.add(key)
        m = _to_down(d)
        rz = m[2]
        zs = [[rz[0] * v[0] + rz[1] * v[1] + rz[2] * v[2] for v in p.v] for p in polys]
        zmin = min(min(z) for z in zs)
        contact = over = 0.0
        for p, a, z in zip(polys, areas, zs):
            nz = rz[0] * p.n[0] + rz[1] * p.n[1] + rz[2] * p.n[2]
            if nz < -0.999 and max(z) < zmin + 0.02:
                contact += a
            elif nz < -0.7072:
                over += a
        score = contact - over
        if key == (0, 0, -1):
            drawn = (score, d, m)
        if best is None or score > best[0]:
            best = (score, d, m)
    # Keep the designer's orientation unless it is clearly poor (it may be chosen for strength, e.g. a hook printed
    # on its side): turn only when it has less than 15 % of the best bed contact.
    if drawn and not (best[0] > 0 and drawn[0] < 0.15 * best[0]):
        best = drawn
    _, d, m = best
    turned = transform(polys, m) if tuple(round(c, 2) for c in d) != (0, 0, -1) else polys
    xs = [v[0] for p in turned for v in p.v]
    ys = [v[1] for p in turned for v in p.v]
    zs = [v[2] for p in turned for v in p.v]
    shift = m_translate((-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs)))
    out = transform(turned, shift)
    if turned is polys:
        return out, None
    name = FACE_NAMES.get(tuple(int(round(c)) for c in d) if all(abs(abs(c) - round(abs(c))) < 1e-6 for c in d) else None)
    return out, f"Turned for printing: the {name or 'largest flat'} face lies on the bed."
