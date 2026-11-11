"""Solid geometry booleans (union, difference, intersection) on closed polygon meshes, with BSP trees.

The classic constructive-solid-geometry algorithm: each solid is a list of planar convex polygons; a BSP tree of
one solid clips the other's polygons, and the kept pieces form the result. Exact for flat faces, so dimensions
stay exactly as written. Solids whose bounding boxes do not touch skip the tree work entirely.
"""
EPS = 1e-6
COPLANAR, FRONT, BACK, SPANNING = 0, 1, 2, 3


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


class Polygon:
    __slots__ = ("v", "n", "w")

    def __init__(self, verts, plane=None):
        self.v = verts
        if plane is None:
            # Newell's method: robust normal for any planar polygon
            nx = ny = nz = 0.0
            for i, a in enumerate(verts):
                b = verts[(i + 1) % len(verts)]
                nx += (a[1] - b[1]) * (a[2] + b[2])
                ny += (a[2] - b[2]) * (a[0] + b[0])
                nz += (a[0] - b[0]) * (a[1] + b[1])
            length = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            n = (nx / length, ny / length, nz / length)
            plane = (n, dot(n, verts[0]))
        self.n, self.w = plane

    def flipped(self):
        return Polygon(self.v[::-1], ((-self.n[0], -self.n[1], -self.n[2]), -self.w))


def split(plane_n, plane_w, poly, cofront, coback, front, back):
    types, kind = [], 0
    for v in poly.v:
        t = dot(plane_n, v) - plane_w
        c = BACK if t < -EPS else FRONT if t > EPS else COPLANAR
        kind |= c
        types.append(c)
    if kind == COPLANAR:
        (cofront if dot(plane_n, poly.n) > 0 else coback).append(poly)
    elif kind == FRONT:
        front.append(poly)
    elif kind == BACK:
        back.append(poly)
    else:
        f, b = [], []
        vs = poly.v
        for i, vi in enumerate(vs):
            j = (i + 1) % len(vs)
            ti, tj, vj = types[i], types[j], vs[j]
            if ti != BACK:
                f.append(vi)
            if ti != FRONT:
                b.append(vi)
            if (ti | tj) == SPANNING:
                t = (plane_w - dot(plane_n, vi)) / dot(plane_n, sub(vj, vi))
                p = lerp(vi, vj, t)
                f.append(p)
                b.append(p)
        if len(f) >= 3:
            front.append(Polygon(f, (poly.n, poly.w)))
        if len(b) >= 3:
            back.append(Polygon(b, (poly.n, poly.w)))


class Node:
    __slots__ = ("plane", "front", "back", "polys")

    def __init__(self, polys=None):
        self.plane = None
        self.front = self.back = None
        self.polys = []
        if polys:
            self.build(polys)

    def invert(self):
        stack = [self]
        while stack:
            node = stack.pop()
            node.polys = [p.flipped() for p in node.polys]
            if node.plane:
                n, w = node.plane
                node.plane = ((-n[0], -n[1], -n[2]), -w)
            node.front, node.back = node.back, node.front
            stack += [c for c in (node.front, node.back) if c]

    def clip_polygons(self, polys):
        """Polygons outside this solid (iterative, so deep trees cannot hit Python's recursion limit)."""
        out, stack = [], [(self, polys)]
        while stack:
            node, ps = stack.pop()
            if not node.plane:
                out += ps
                continue
            n, w = node.plane
            f, b = [], []
            for p in ps:
                split(n, w, p, f, b, f, b)
            if node.front:
                stack.append((node.front, f))
            else:
                out += f
            if node.back:
                stack.append((node.back, b))
        return out

    def clip_to(self, other):
        stack = [self]
        while stack:
            node = stack.pop()
            node.polys = other.clip_polygons(node.polys)
            stack += [c for c in (node.front, node.back) if c]

    def all(self):
        out, stack = [], [self]
        while stack:
            node = stack.pop()
            out += node.polys
            stack += [c for c in (node.front, node.back) if c]
        return out

    def build(self, polys):
        stack = [(self, polys)]
        while stack:
            node, ps = stack.pop()
            if not ps:
                continue
            if not node.plane:
                node.plane = (ps[0].n, ps[0].w)
            n, w = node.plane
            f, b = [], []
            for p in ps:
                split(n, w, p, node.polys, node.polys, f, b)
            if f:
                node.front = node.front or Node()
                stack.append((node.front, f))
            if b:
                node.back = node.back or Node()
                stack.append((node.back, b))


def bbox(polys):
    xs = [v[0] for p in polys for v in p.v]
    ys = [v[1] for p in polys for v in p.v]
    zs = [v[2] for p in polys for v in p.v]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def apart(a, b):
    if not a or not b:
        return True
    p, q = bbox(a), bbox(b)
    return any(p[i] > q[i + 3] + EPS or q[i] > p[i + 3] + EPS for i in range(3))


def union(a, b):
    if apart(a, b):
        return a + b
    na, nb = Node(a), Node(b)
    na.clip_to(nb)
    nb.clip_to(na)
    nb.invert()
    nb.clip_to(na)
    nb.invert()
    na.build(nb.all())
    return na.all()


def difference(a, b):
    if apart(a, b):
        return list(a)
    na, nb = Node(a), Node(b)
    na.invert()
    na.clip_to(nb)
    nb.clip_to(na)
    nb.invert()
    nb.clip_to(na)
    nb.invert()
    na.build(nb.all())
    na.invert()
    return na.all()


def intersection(a, b):
    if apart(a, b):
        return []
    na, nb = Node(a), Node(b)
    na.invert()
    nb.clip_to(na)
    nb.invert()
    na.clip_to(nb)
    nb.clip_to(na)
    na.build(nb.all())
    na.invert()
    return na.all()
