"""A safe interpreter for the OpenSCAD language subset that the 3D Print mode uses.

Supported: variables, arithmetic and logic, vectors, ranges, list comprehensions, `let`, functions and modules
(with children()), `for`, `if`/`else`, the modifiers * ! # %, and these objects:
  3D  cube sphere cylinder polyhedron        2D  square circle polygon
  linear_extrude rotate_extrude  translate rotate scale mirror multmatrix color resize hull
  union difference intersection render children echo assert
Not supported (an error says so, and the model is asked to rewrite): minkowski, offset, text, import, surface,
projection, include/use. The interpreter has no file, network or process access; limits on steps, time,
recursion and polygon count keep a runaway script from hanging the app.
"""
import math
import re
import time

from core.cad import geometry as g
from core.cad.geometry import CadError, Shape2

MAX_STEPS, MAX_SECONDS, MAX_DEPTH, MAX_POLYS = 3_000_000, 40.0, 120, 80_000
HULL_FN = 40
UNSUPPORTED = {"minkowski": "minkowski() is not available; round edges with hull() of spheres/cylinders instead.",
               "offset": "offset() is not available; draw the 2D outline with polygon() or hull() instead.",
               "import": "import() is not available.",
               "surface": "surface() is not available.", "projection": "projection() is not available."}

TOKEN = re.compile(r"""\s*(?:(//[^\n]*|/\*.*?\*/)|(\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?)|("(?:\\.|[^"\\])*")|
                       ([A-Za-z_$][A-Za-z0-9_]*)|(==|!=|<=|>=|&&|\|\||[-+*/%^!<>=?:;,(){}\[\].#]))""", re.S | re.X)


def tokenize(src):
    toks, pos = [], 0
    src = src.replace("\r\n", "\n")
    # Typographic operators a model sometimes writes; comments and strings are unaffected in meaning.
    for a, b in (("×", "*"), ("÷", "/"), ("−", "-"), ("≤", "<="), ("≥", ">="), ("≠", "!="), (" ", " ")):
        src = src.replace(a, b)
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m or m.end() == pos:
            if src[pos:].strip() == "":
                break
            line = src.count("\n", 0, pos) + 1
            raise CadError(f"Line {line}: unexpected character {src[pos:pos + 1]!r}.")
        pos = m.end()
        if m.group(1):
            continue
        line = src.count("\n", 0, m.start(m.lastindex)) + 1    # where the token starts, after its leading space
        if m.group(2):
            toks.append(("num", float(m.group(2)), line))
        elif m.group(3):
            toks.append(("str", m.group(3)[1:-1].encode().decode("unicode_escape", "replace"), line))
        elif m.group(4):
            toks.append(("id", m.group(4), line))
        else:
            toks.append(("op", m.group(5), line))
    toks.append(("eof", None, src.count("\n") + 1))
    return toks


# ---------------------------------------------------------------------------------------------- parser
class Parser:
    def __init__(self, src):
        self.t = tokenize(src)
        self.i = 0

    def peek(self, k=0):
        return self.t[min(self.i + k, len(self.t) - 1)]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def _looks_like_def(self):
        """name(...) { return ... }: a C/JavaScript-style function, at the current token."""
        j, depth = self.i + 1, 0
        while j < len(self.t):
            kind, val, _ = self.t[j]
            if kind == "op" and val == "(":
                depth += 1
            elif kind == "op" and val == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        nxt = self.t[j + 1:j + 3]
        return len(nxt) == 2 and nxt[0][1] == "{" and nxt[1][0] == "id" and nxt[1][1] == "return"

    def accept(self, value):
        if self.peek()[1] == value and self.peek()[0] in ("op", "id"):
            self.i += 1
            return True
        return False

    def expect(self, value):
        tok = self.next()
        if tok[1] != value:
            found = "the code ended" if tok[0] == "eof" else f"found '{tok[1]}'"
            raise CadError(f"Line {tok[2]}: expected '{value}' but {found}.")
        return tok

    def program(self):
        out = []
        while self.peek()[0] != "eof":
            out.append(self.statement())
        return ("block", out)

    def statement(self):
        tok = self.peek()
        if tok[0] == "op":
            if tok[1] == ";":
                self.next()
                return ("block", [])
            if tok[1] == "{":
                self.next()
                body = []
                while not self.accept("}"):
                    if self.peek()[0] == "eof":
                        raise CadError(f"Line {tok[2]}: a '{{' is never closed.")
                    body.append(self.statement())
                return ("block", body)
            if tok[1] in ("*", "!", "#", "%"):
                self.next()
                return ("mod", tok[1], self.statement())
            raise CadError(f"Line {tok[2]}: unexpected '{tok[1]}'.")
        if tok[0] != "id":
            raise CadError(f"Line {tok[2]}: unexpected {tok[1]!r}.")
        name = tok[1]
        if name in ("include", "use"):
            raise CadError(f"Line {tok[2]}: {name} <file> is not available; write the whole model in one file.")
        # Other languages' habits: say how OpenSCAD writes it, so a repair can fix it.
        if name in ("return", "var", "const", "def", "int", "float", "double", "local", "end", "then", "elif", "else"):
            hint = {"return": "OpenSCAD has no 'return'. A function is one expression: function to_rad(a) = a * PI / 180;",
                    "else": "'else' must follow an if (...) statement directly.",
                    "elif": "write 'else if (...)'."}.get(name, f"OpenSCAD has no '{name}'. Assign variables as: name = value;")
            raise CadError(f"Line {tok[2]}: {hint}")
        if self.peek(1)[1] == "(" and self._looks_like_def():
            raise CadError(f"Line {tok[2]}: '{name}(...) {{ ... }}' with 'return' is not OpenSCAD. Write "
                           f"function {name}(x) = expression; or module {name}() {{ shapes }}.")
        if name == "module":
            self.next()
            mname = self.next()[1]
            params = self.params()
            if self.peek()[1] in (":", "="):
                raise CadError(f"Line {self.peek()[2]}: a module body goes in braces, not after '{self.peek()[1]}': "
                               f"module {mname}(...) {{ shapes; }}. Or leave the module out and call the shape directly.")
            return ("module", mname, params, self.statement())
        if name == "function":
            self.next()
            fname = self.next()[1]
            params = self.params()
            self.expect("=")
            body = self.expr()
            self.expect(";")
            return ("function", fname, params, body)
        if name == "if":
            self.next()
            self.expect("(")
            cond = self.expr()
            self.expect(")")
            then = self.statement()
            other = self.statement() if self.accept("else") else None
            return ("if", cond, then, other)
        if name in ("for", "intersection_for"):
            self.next()
            self.expect("(")
            assigns = self.assignments(")")
            return ("for", assigns, self.statement(), name == "intersection_for")
        if name == "let" and self.peek(1)[1] == "(":
            self.next()
            self.expect("(")
            assigns = self.assignments(")")
            return ("let", assigns, self.statement())
        if self.peek(1)[1] == "=" and self.peek(1)[0] == "op":
            self.next()
            self.next()
            value = self.expr()
            self.expect(";")
            return ("assign", name, value, tok[2])
        self.next()
        self.expect("(")
        args = self.args(")")
        if self.accept(";"):
            child = ("block", [])
        else:
            child = self.statement()
        return ("call", name, args, child, tok[2])

    def params(self):
        self.expect("(")
        out = []
        while not self.accept(")"):
            name = self.next()[1]
            default = self.expr() if self.accept("=") else None
            out.append((name, default))
            self.accept(",")
        return out

    def assignments(self, close):
        out = []
        while not self.accept(close):
            name = self.next()[1]
            self.expect("=")
            out.append((name, self.expr()))
            self.accept(",")
        return out

    def args(self, close):
        out = []
        while not self.accept(close):
            if self.peek()[0] == "id" and self.peek(1)[1] == "=" and self.peek(1)[0] == "op":
                name = self.next()[1]
                self.next()
                out.append((name, self.expr()))
            else:
                out.append((None, self.expr()))
            if not self.accept(","):
                self.expect(close)
                break
        return out

    # expressions, lowest precedence first
    def expr(self):
        if self.peek()[1] == "let" and self.peek(1)[1] == "(":
            self.next()
            self.expect("(")
            assigns = self.assignments(")")
            return ("let", assigns, self.expr())
        cond = self.binary(0)
        if self.accept("?"):
            a = self.expr()
            self.expect(":")
            return ("?", cond, a, self.expr())
        return cond

    LEVELS = [("||",), ("&&",), ("==", "!="), ("<", "<=", ">", ">="), ("+", "-"), ("*", "/", "%")]

    def binary(self, level):
        if level == len(self.LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.peek()[0] == "op" and self.peek()[1] in self.LEVELS[level]:
            op = self.next()[1]
            left = ("bin", op, left, self.binary(level + 1))
        return left

    def unary(self):
        if self.peek()[0] == "op" and self.peek()[1] in ("-", "+", "!"):
            op = self.next()[1]
            return ("un", op, self.unary())
        return self.power()

    def power(self):
        base = self.postfix()
        if self.accept("^"):
            return ("bin", "^", base, self.unary())
        return base

    def postfix(self):
        node = self.primary()
        while True:
            if self.accept("("):
                node = ("callf", node, self.args(")"))
            elif self.accept("["):
                idx = self.expr()
                self.expect("]")
                node = ("index", node, idx)
            elif self.accept("."):
                node = ("member", node, self.next()[1])
            else:
                return node

    def primary(self):
        tok = self.next()
        kind, val, line = tok
        if kind == "num":
            return ("const", val)
        if kind == "str":
            return ("const", val)
        if kind == "id":
            if val == "true":
                return ("const", True)
            if val == "false":
                return ("const", False)
            if val == "undef":
                return ("const", None)
            if val == "PI":
                return ("const", math.pi)
            if val == "function":
                raise CadError(f"Line {line}: function literals are not available.")
            return ("var", val, line)
        if val == "(":
            e = self.expr()
            self.expect(")")
            return e
        if val == "[":
            return self.vector()
        raise CadError(f"Line {line}: unexpected '{val}'.")

    def vector(self):
        if self.accept("]"):
            return ("vec", [])
        if self.peek()[1] in ("for", "each", "let", "if") and self.peek()[0] == "id":
            items = []
            while True:
                items.append(self.comprehension())
                if not self.accept(","):
                    break
            self.expect("]")
            return ("vec", items)
        first = self.expr()
        if self.accept(":"):
            second = self.expr()
            if self.accept(":"):
                third = self.expr()
                self.expect("]")
                return ("range", first, second, third)
            self.expect("]")
            return ("range", first, ("const", 1.0), second)
        items = [first]
        while self.accept(","):
            if self.peek()[1] == "]":
                break
            items.append(self.comprehension() if self.peek()[1] in ("for", "each") else self.expr())
        self.expect("]")
        return ("vec", items)

    def comprehension(self):
        if self.accept("for"):
            self.expect("(")
            assigns = self.assignments(")")
            return ("lc_for", assigns, self.comprehension())
        if self.accept("if"):
            self.expect("(")
            cond = self.expr()
            self.expect(")")
            then = self.comprehension()
            other = self.comprehension() if self.accept("else") else None
            return ("lc_if", cond, then, other)
        if self.accept("let"):
            self.expect("(")
            assigns = self.assignments(")")
            return ("lc_let", assigns, self.comprehension())
        if self.accept("each"):
            return ("lc_each", self.expr())
        return self.expr()


# ---------------------------------------------------------------------------------------------- evaluation
class Range:
    def __init__(self, start, step, end):
        if step == 0 or not all(isinstance(v, (int, float)) for v in (start, step, end)):
            raise CadError("A range needs numbers and a non-zero step.")
        if (end - start) / step > 100_000:
            raise CadError("A range is too long (over 100,000 values).")
        self.start, self.step, self.end = start, step, end

    def __iter__(self):
        v, n = self.start, 0
        while (v <= self.end + 1e-9) if self.step > 0 else (v >= self.end - 1e-9):
            yield v
            n += 1
            v = self.start + n * self.step


class Scope:
    def __init__(self, parent=None):
        self.vars, self.funcs, self.mods, self.parent = {}, {}, {}, parent

    def get(self, name):
        s = self
        while s:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None

    def lookup(self, table, name):
        s = self
        while s:
            if name in getattr(s, table):
                return getattr(s, table)[name]
            s = s.parent
        return None


def shown(v):
    return "undef (a missing or misspelled variable?)" if v is None else repr(v)


def num(v, what):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CadError(f"{what} must be a number (got {shown(v)}).")
    return float(v)


def vec3(v, what, fill=0.0):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (float(v),) * 3
    if not isinstance(v, list) or not v:
        raise CadError(f"{what} must be a number or a vector (got {shown(v)}).")
    vals = [num(x, what) for x in v[:3]]
    while len(vals) < 3:
        vals.append(fill)
    return tuple(vals)


class Interpreter:
    def __init__(self, overrides=None):
        self.steps = 0
        self.started = time.monotonic()
        self.echo = []
        self.overrides = overrides or {}
        self.depth = 0
        self.fn_cap = 0
        self.undef = None

    def tick(self):
        self.steps += 1
        if self.steps > MAX_STEPS:
            raise CadError("The model takes too many steps to compute (a loop that is too long?).")
        if self.steps % 2000 == 0 and time.monotonic() - self.started > MAX_SECONDS:
            raise CadError(f"The model took longer than {MAX_SECONDS:.0f} s to build; use fewer segments or parts.")

    # ---- expressions
    def ev(self, node, sc):
        self.tick()
        kind = node[0]
        if kind == "const":
            return node[1]
        if kind == "var":
            name = node[1]
            if name in ("$fn", "$fa", "$fs", "$t", "$preview", "$children"):
                val = sc.get(name)
                return {"$fn": 0.0, "$fa": 12.0, "$fs": 2.0, "$t": 0.0, "$preview": False, "$children": 0}[name] if val is None else val
            val = sc.get(name)
            if val is None and not name.startswith("$"):
                self.undef = name       # named in the error if this undef reaches a shape
            return val
        if kind == "vec":
            out = []
            for item in node[1]:
                if item[0].startswith("lc_"):
                    out += self.lc(item, sc)
                else:
                    out.append(self.ev(item, sc))
            return out
        if kind == "range":
            return Range(self.ev(node[1], sc), self.ev(node[2], sc), self.ev(node[3], sc))
        if kind == "un":
            v = self.ev(node[2], sc)
            if node[1] == "!":
                return not truthy(v)
            if node[1] == "-":
                return neg(v)
            return v
        if kind == "bin":
            op = node[1]
            if op == "&&":
                return truthy(self.ev(node[2], sc)) and truthy(self.ev(node[3], sc))
            if op == "||":
                return truthy(self.ev(node[2], sc)) or truthy(self.ev(node[3], sc))
            return binop(op, self.ev(node[2], sc), self.ev(node[3], sc))
        if kind == "?":
            return self.ev(node[2] if truthy(self.ev(node[1], sc)) else node[3], sc)
        if kind == "index":
            base, idx = self.ev(node[1], sc), self.ev(node[2], sc)
            if isinstance(base, (list, str)) and isinstance(idx, (int, float)) and not isinstance(idx, bool):
                i = int(idx)
                return base[i] if 0 <= i < len(base) else None
            return None
        if kind == "member":
            base = self.ev(node[1], sc)
            pos = {"x": 0, "y": 1, "z": 2}.get(node[2])
            return base[pos] if isinstance(base, list) and pos is not None and pos < len(base) else None
        if kind == "let":
            inner = Scope(sc)
            for name, e in node[1]:
                inner.vars[name] = self.ev(e, inner)
            return self.ev(node[2], inner)
        if kind == "callf":
            return self.call_function(node, sc)
        raise CadError(f"Unknown expression {kind}.")

    def lc(self, node, sc):
        kind = node[0]
        if kind == "lc_for":
            out = []
            def loop(i, scope):
                if i == len(node[1]):
                    out.extend(self.lc_item(node[2], scope))
                    return
                name, e = node[1][i]
                for v in iterate(self.ev(e, scope)):
                    inner = Scope(scope)
                    inner.vars[name] = v
                    loop(i + 1, inner)
            loop(0, sc)
            return out
        if kind == "lc_if":
            if truthy(self.ev(node[1], sc)):
                return self.lc_item(node[2], sc)
            return self.lc_item(node[3], sc) if node[3] is not None else []
        if kind == "lc_let":
            inner = Scope(sc)
            for name, e in node[1]:
                inner.vars[name] = self.ev(e, inner)
            return self.lc_item(node[2], inner)
        if kind == "lc_each":
            return list(iterate(self.ev(node[1], sc)))
        return [self.ev(node, sc)]

    def lc_item(self, node, sc):
        return self.lc(node, sc) if node[0].startswith("lc_") else [self.ev(node, sc)]

    def call_function(self, node, sc):
        target = node[1]
        if target[0] != "var":
            raise CadError("Only named functions can be called.")
        name = target[1]
        args = [(k, self.ev(e, sc)) for k, e in node[2]]
        user = sc.lookup("funcs", name)
        if user:
            params, body, defscope = user
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CadError(f"Function {name}() recurses too deeply.")
            try:
                inner = Scope(defscope)
                bind(inner, params, args, self, defscope)
                return self.ev(body, inner)
            finally:
                self.depth -= 1
        pos = [v for k, v in args if k is None]
        named = {k: v for k, v in args if k}
        fn = BUILTINS.get(name)
        if fn is None:
            raise CadError(f"Unknown function {name}().")
        try:
            return fn(*pos, **named)
        except CadError:
            raise
        except (TypeError, ValueError, ZeroDivisionError, OverflowError, IndexError):
            return None

    # ---- statements
    def run_block(self, stmts, sc):
        """OpenSCAD order: definitions and assignments first (the last assignment wins), then the objects."""
        for st in stmts:
            if st[0] == "module":
                sc.mods[st[1]] = (st[2], st[3], sc)
            elif st[0] == "function":
                sc.funcs[st[1]] = (st[2], st[3], sc)
        for st in stmts:
            if st[0] == "assign":
                if sc.parent is None and st[1] in self.overrides:
                    sc.vars[st[1]] = self.overrides[st[1]]
                else:
                    sc.vars[st[1]] = self.ev(st[2], sc)
        out = []
        for st in stmts:
            if st[0] not in ("assign", "module", "function"):
                out += self.run(st, sc)
        return out

    def run(self, st, sc):
        self.tick()
        kind = st[0]
        if kind == "block":
            return self.run_block(st[1], Scope(sc))
        if kind == "mod":
            if st[1] in ("*", "%"):
                return []
            return self.run(st[2], sc)
        if kind == "if":
            if truthy(self.ev(st[1], sc)):
                return self.run(st[2], sc)
            return self.run(st[3], sc) if st[3] is not None else []
        if kind == "let":
            inner = Scope(sc)
            for name, e in st[1]:
                inner.vars[name] = self.ev(e, inner)
            return self.run(st[2], inner)
        if kind == "for":
            items = []
            def loop(i, scope):
                if i == len(st[1]):
                    items.append(self.run(st[2], scope))
                    return
                name, e = st[1][i]
                for v in iterate(self.ev(e, scope)):
                    inner = Scope(scope)
                    inner.vars[name] = v
                    loop(i + 1, inner)
            loop(0, sc)
            if st[3]:
                return [self.combine("intersection", [x for x in items if x])]
            return [o for x in items for o in x]
        if kind == "call":
            return self.instantiate(st, sc)
        if kind in ("assign", "module", "function"):
            return []
        raise CadError(f"Unknown statement {kind}.")

    def instantiate(self, st, sc):
        _, name, argnodes, child, line = st
        self.undef = None
        args = [(k, self.ev(e, sc)) for k, e in argnodes]
        missing = self.undef
        if name in UNSUPPORTED:
            raise CadError(f"Line {line}: {UNSUPPORTED[name]}")
        if name == "children":
            caller = sc.get("$__children")
            if caller is None:
                return []
            stmts, cscope = caller
            pos = [v for k, v in args if k is None]
            if pos:
                idx = pos[0]
                picks = list(iterate(idx)) if isinstance(idx, (list, Range)) else [idx]
                chosen = [stmts[int(i)] for i in picks if isinstance(i, (int, float)) and 0 <= int(i) < len(stmts)]
            else:
                chosen = stmts
            out = []
            for c in chosen:
                out += self.run(c, cscope)
            return out
        user = sc.lookup("mods", name)
        if user:
            params, body, defscope = user
            self.depth += 1
            if self.depth > MAX_DEPTH:
                raise CadError(f"Line {line}: module {name}() recurses too deeply.")
            try:
                inner = Scope(defscope)
                bind(inner, params, args, self, defscope)
                stmts = child[1] if child[0] == "block" else [child]
                inner.vars["$__children"] = (stmts, sc)
                inner.vars["$children"] = len(stmts)
                for special in ("$fn", "$fa", "$fs"):
                    if inner.vars.get(special) is None and sc.get(special) is not None:
                        inner.vars[special] = sc.get(special)
                return self.run(body, inner)
            finally:
                self.depth -= 1
        fn = OBJECTS.get(name)
        if fn is None:
            raise CadError(f"Line {line}: unknown module {name}().")
        pos = [v for k, v in args if k is None]
        named = {k: v for k, v in args if k}
        local = Scope(sc)
        for special in ("$fn", "$fa", "$fs"):
            if special in named:
                local.vars[special] = named.pop(special)
        res = {"fn": num(local.get("$fn") or 0, "$fn"), "fa": num(local.get("$fa") or 12, "$fa"),
               "fs": num(local.get("$fs") or 2, "$fs")}
        if self.fn_cap and res["fn"] > self.fn_cap:
            res["fn"] = float(self.fn_cap)
        try:
            return fn(self, pos, named, child, local, res, line)
        except CadError as exc:
            if str(exc).startswith("Line "):
                raise
            hint = f" '{missing}' is not defined." if missing and "undef" in str(exc) else ""
            raise CadError(f"Line {line}: {name}(): {exc}{hint}") from exc
        except (TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
            raise CadError(f"Line {line}: {name}() has invalid arguments ({exc}).") from exc

    def children(self, child, sc):
        return self.run(child, sc)

    def combine(self, op, objs):
        objs = [o for o in objs if o is not None]
        if not objs:
            return None
        if all(isinstance(o, Shape2) for o in objs):
            return Shape2(op, objs) if len(objs) > 1 else objs[0]
        if any(isinstance(o, Shape2) for o in objs):
            raise CadError("2D and 3D objects are mixed in one operation; extrude the 2D shape first.")
        too_many = f"The model has too many faces (over {MAX_POLYS:,}); use fewer segments ($fn) or parts."
        if sum(len(o) for o in objs) > MAX_POLYS:
            raise CadError(too_many)
        out = g.combine(op, objs, self.clock)
        if len(out) > MAX_POLYS:
            raise CadError(too_many)
        self.clock()
        return out

    def clock(self):
        if time.monotonic() - self.started > MAX_SECONDS:
            raise CadError(f"The model took longer than {MAX_SECONDS:.0f} s to build; use fewer segments or parts.")


def bind(scope, params, args, it, defscope):
    named = {k: v for k, v in args if k}
    pos = [v for k, v in args if k is None]
    for i, (pname, default) in enumerate(params):
        if pname in named:
            scope.vars[pname] = named[pname]
        elif i < len(pos):
            scope.vars[pname] = pos[i]
        else:
            scope.vars[pname] = it.ev(default, scope) if default is not None else None
    for k, v in named.items():
        if k.startswith("$"):
            scope.vars[k] = v


def truthy(v):
    if isinstance(v, (list, str)):
        return len(v) > 0
    return bool(v)


def neg(v):
    if isinstance(v, list):
        return [neg(x) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return -v
    return None


def binop(op, a, b):
    isnum = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if op in ("==", "!="):
        eq = a == b
        return eq if op == "==" else not eq
    if op in ("<", "<=", ">", ">="):
        if isnum(a) and isnum(b) or isinstance(a, str) and isinstance(b, str):
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        return None
    if isnum(a) and isnum(b):
        try:
            if op == "+": return a + b
            if op == "-": return a - b
            if op == "*": return a * b
            if op == "/": return a / b if b else (math.inf if a > 0 else -math.inf if a < 0 else math.nan)
            if op == "%": return math.fmod(a, b) if b else math.nan
            if op == "^":
                if abs(b) > 1000: raise CadError("Exponent too large.")
                return a ** b
        except (OverflowError, ValueError):
            return None
    if isinstance(a, list) and isinstance(b, list) and op in ("+", "-"):
        return [binop(op, x, y) for x, y in zip(a, b)]
    if isinstance(a, list) and isinstance(b, list) and op == "*":
        if a and isinstance(a[0], list):
            if b and isinstance(b[0], list):
                return [[sum(r[k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for r in a]
            return [sum(x * y for x, y in zip(r, b)) for r in a]
        return sum(x * y for x, y in zip(a, b))
    if isinstance(a, list) and isnum(b) and op in ("*", "/"):
        return [binop(op, x, b) for x in a]
    if isnum(a) and isinstance(b, list) and op == "*":
        return [binop(op, a, x) for x in b]
    return None


def iterate(v):
    if isinstance(v, Range):
        return iter(v)
    if isinstance(v, list):
        return iter(v)
    if v is None:
        return iter(())
    return iter([v])


def _deg(fn):
    return lambda x: fn(math.radians(x))


BUILTINS = {
    "sin": _deg(math.sin), "cos": _deg(math.cos), "tan": _deg(math.tan),
    "asin": lambda x: math.degrees(math.asin(x)), "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)), "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "abs": abs, "sign": lambda x: (x > 0) - (x < 0), "floor": math.floor, "ceil": math.ceil, "round": lambda x: math.floor(x + 0.5),
    "sqrt": math.sqrt, "pow": lambda a, b: a ** b, "exp": math.exp, "ln": math.log, "log": lambda a, b=None: math.log10(a) if b is None else math.log(b, a),
    "min": lambda *a: min(a[0]) if len(a) == 1 and isinstance(a[0], list) else min(a),
    "max": lambda *a: max(a[0]) if len(a) == 1 and isinstance(a[0], list) else max(a),
    "norm": lambda v: math.sqrt(sum(x * x for x in v)), "len": lambda v: len(v) if isinstance(v, (list, str)) else None,
    "concat": lambda *a: [x for part in a for x in (part if isinstance(part, list) else [part])],
    "cross": lambda a, b: [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
    "lookup": lambda k, table: _lookup(k, table), "str": lambda *a: "".join(str(x) for x in a),
    "is_num": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool), "is_list": lambda v: isinstance(v, list),
    "is_undef": lambda v: v is None, "is_bool": lambda v: isinstance(v, bool), "is_string": lambda v: isinstance(v, str),
    "chr": lambda *a: "".join(chr(int(x)) for x in a), "version": lambda: [2021, 1, 0], "version_num": lambda: 20210100,
}


def _lookup(k, table):
    pts = sorted((p[0], p[1]) for p in table)
    if k <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if k <= x1:
            return y0 + (y1 - y0) * (k - x0) / (x1 - x0)
    return pts[-1][1]


# ---------------------------------------------------------------------------------------------- objects
def arg(pos, named, i, name, default=None):
    if name in named:
        return named[name]
    return pos[i] if i < len(pos) else default


def o_cube(it, pos, named, child, sc, res, line):
    size = arg(pos, named, 0, "size", 1)
    return [g.cube(vec3(size, "cube size", 1.0) if isinstance(size, list) else (num(size, "cube size"),) * 3,
                   truthy(arg(pos, named, 1, "center", False)))]


def radius(named, pos, i=0, keys=("r", "d")):
    if "d" in named and named["d"] is not None:
        return num(named["d"], "d") / 2
    if "r" in named and named["r"] is not None:
        return num(named["r"], "r")
    if i < len(pos) and pos[i] is not None:
        return num(pos[i], "r")
    return 1.0


def o_sphere(it, pos, named, child, sc, res, line):
    r = radius(named, pos)
    return [g.sphere(r, g.fragments(r, res["fn"], res["fa"], res["fs"]))]


def o_cylinder(it, pos, named, child, sc, res, line):
    h = num(arg(pos, named, 0, "h", 1), "h")
    r = named.get("r", pos[1] if len(pos) > 1 else None)
    r = num(named["d"], "d") / 2 if named.get("d") is not None else (num(r, "r") if r is not None else 1.0)
    r1 = num(named["d1"], "d1") / 2 if named.get("d1") is not None else num(named.get("r1", pos[1] if len(pos) > 1 and "r" not in named else r), "r1")
    r2 = num(named["d2"], "d2") / 2 if named.get("d2") is not None else num(named.get("r2", pos[2] if len(pos) > 2 else r), "r2")
    if "r" in named or "d" in named:
        r1 = num(named["d1"], "d1") / 2 if named.get("d1") is not None else num(named.get("r1", r), "r1")
        r2 = num(named["d2"], "d2") / 2 if named.get("d2") is not None else num(named.get("r2", r), "r2")
    center = truthy(named.get("center", pos[3] if len(pos) > 3 else False))
    n = g.fragments(max(r1, r2), res["fn"], res["fa"], res["fs"])
    return [g.cylinder(h, r1, r2, center, n)]


def o_polyhedron(it, pos, named, child, sc, res, line):
    return [g.polyhedron(arg(pos, named, 0, "points", []), arg(pos, named, 1, "faces", arg(pos, named, 1, "triangles", [])))]


def o_square(it, pos, named, child, sc, res, line):
    size = arg(pos, named, 0, "size", 1)
    s = (num(size, "size"),) * 2 if not isinstance(size, list) else tuple(num(v, "size") for v in (size + [1, 1])[:2])
    return [g.square(s, truthy(arg(pos, named, 1, "center", False)))]


def o_circle(it, pos, named, child, sc, res, line):
    r = radius(named, pos)
    return [g.circle(r, g.fragments(r, res["fn"], res["fa"], res["fs"]))]


def o_polygon(it, pos, named, child, sc, res, line):
    return [g.polygon(arg(pos, named, 0, "points", []), arg(pos, named, 1, "paths", None))]


def group(it, child, sc, op="union"):
    objs = it.children(child, sc)
    if op == "difference":
        objs = [o for o in objs if o is not None]
        if not objs:
            return None
        rest = it.combine("union", objs[1:]) if len(objs) > 1 else None
        return it.combine("difference", [objs[0], rest]) if rest is not None else objs[0]
    return it.combine(op, objs)


def transformed(it, child, sc, m3, m2=None):
    obj = group(it, child, sc)
    if obj is None:
        return []
    if isinstance(obj, Shape2):
        return [obj.map(lambda p: g.apply(m3, (p[0], p[1], 0.0))[:2])]
    return [g.transform(obj, m3)]


def o_translate(it, pos, named, child, sc, res, line):
    return transformed(it, child, sc, g.m_translate(vec3(arg(pos, named, 0, "v", [0, 0, 0]), "translate")))


def o_rotate(it, pos, named, child, sc, res, line):
    a, v = arg(pos, named, 0, "a", 0), arg(pos, named, 1, "v", None)
    if isinstance(a, list):
        return transformed(it, child, sc, g.m_rotate(vec3(a, "rotate")))
    a = num(a, "rotate angle")
    return transformed(it, child, sc, g.m_rotate(a, vec3(v, "rotate axis")) if v is not None else g.m_rotate((0, 0, a)))


def o_scale(it, pos, named, child, sc, res, line):
    return transformed(it, child, sc, g.m_scale(vec3(arg(pos, named, 0, "v", 1), "scale", 1.0)))


def o_mirror(it, pos, named, child, sc, res, line):
    return transformed(it, child, sc, g.m_mirror(vec3(arg(pos, named, 0, "v", [1, 0, 0]), "mirror")))


def o_multmatrix(it, pos, named, child, sc, res, line):
    m = arg(pos, named, 0, "m", None)
    rows = [[float(x) for x in (r + [0, 0, 0, 0])[:4]] for r in (m or [])[:4]]
    while len(rows) < 4:
        rows.append([0, 0, 0, 1] if len(rows) == 3 else [1.0 if i == len(rows) else 0.0 for i in range(4)])
    return transformed(it, child, sc, rows)


def o_resize(it, pos, named, child, sc, res, line):
    target = vec3(arg(pos, named, 0, "newsize", [0, 0, 0]), "resize")
    obj = group(it, child, sc)
    if obj is None or isinstance(obj, Shape2) or not obj:
        return [obj] if obj is not None else []
    xs = [v[0] for p in obj for v in p.v]
    ys = [v[1] for p in obj for v in p.v]
    zs = [v[2] for p in obj for v in p.v]
    cur = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    f = [t / c if t > 0 and c > 0 else None for t, c in zip(target, cur)]
    # auto=true scales the axes given as 0 by the same factor as the ones given (OpenSCAD: the largest given factor)
    auto = named.get("auto", False)
    autos = auto if isinstance(auto, list) else [auto] * 3
    given = [x for x in f if x is not None]
    f = [x if x is not None else (max(given) if given and i < len(autos) and truthy(autos[i]) else 1.0) for i, x in enumerate(f)]
    return [g.transform(obj, g.m_scale(f))]


def o_pass(it, pos, named, child, sc, res, line):
    obj = group(it, child, sc)
    return [obj] if obj is not None else []


def o_union(it, pos, named, child, sc, res, line):
    return o_pass(it, pos, named, child, sc, res, line)


def o_difference(it, pos, named, child, sc, res, line):
    obj = group(it, child, sc, "difference")
    return [obj] if obj is not None else []


def o_intersection(it, pos, named, child, sc, res, line):
    obj = group(it, child, sc, "intersection")
    return [obj] if obj is not None else []


def o_hull(it, pos, named, child, sc, res, line):
    # A hull is smooth anyway: at most 40 segments per circle inside it keeps the point count (and time) in check.
    before = it.fn_cap
    it.fn_cap = min(before or HULL_FN, HULL_FN)
    try:
        objs = [o for o in it.children(child, sc) if o is not None]
    finally:
        it.fn_cap = before
    if not objs:
        return []
    if all(isinstance(o, Shape2) for o in objs):
        return [g.hull2(Shape2("union", objs))]
    if any(isinstance(o, Shape2) for o in objs):
        raise CadError(f"Line {line}: hull() mixes 2D and 3D objects.")
    return [g.hull3([v for o in objs for p in o for v in p.v])]


def o_linear_extrude(it, pos, named, child, sc, res, line):
    h = num(arg(pos, named, 0, "height", named.get("h", 100)), "height")
    center = truthy(named.get("center", False))
    twist = num(named.get("twist", 0) or 0, "twist")
    s = named.get("scale", 1)
    sc2 = (num(s, "scale"),) * 2 if not isinstance(s, list) else (num(s[0], "scale"), num(s[1], "scale"))
    slices = int(named.get("slices") or (max(int(abs(twist) / 5), 1) if twist else 1))
    shape = group(it, child, sc)
    if shape is None:
        return []
    if not isinstance(shape, Shape2):
        raise CadError(f"Line {line}: linear_extrude() needs a 2D shape (square, circle, polygon).")
    z0 = -h / 2 if center else 0.0
    return [g.extrude(shape, g.prism, z0, z0 + h, twist, sc2, min(slices, 200))]


def o_rotate_extrude(it, pos, named, child, sc, res, line):
    angle = num(named.get("angle", 360), "angle")
    shape = group(it, child, sc)
    if shape is None:
        return []
    if not isinstance(shape, Shape2):
        raise CadError(f"Line {line}: rotate_extrude() needs a 2D shape.")
    rmax = max(abs(p[0]) for p in shape.points()) if shape.points() else 1
    return [g.extrude(shape, g.revolve, angle, g.fragments(rmax, res["fn"], res["fa"], res["fs"]))]


def o_echo(it, pos, named, child, sc, res, line):
    it.echo.append(", ".join([repr(v) for v in pos] + [f"{k} = {v!r}" for k, v in named.items()]))
    return it.children(child, sc)


def o_assert(it, pos, named, child, sc, res, line):
    if pos and not truthy(pos[0]):
        raise CadError(f"Line {line}: assert failed{': ' + str(pos[1]) if len(pos) > 1 else ''}.")
    return it.children(child, sc)


OBJECTS = {"cube": o_cube, "sphere": o_sphere, "cylinder": o_cylinder, "polyhedron": o_polyhedron,
           "square": o_square, "circle": o_circle, "polygon": o_polygon, "translate": o_translate, "rotate": o_rotate,
           "scale": o_scale, "mirror": o_mirror, "multmatrix": o_multmatrix, "resize": o_resize, "color": o_pass,
           "render": o_pass, "group": o_pass, "union": o_union, "difference": o_difference,
           "intersection": o_intersection, "hull": o_hull, "linear_extrude": o_linear_extrude,
           "rotate_extrude": o_rotate_extrude, "echo": o_echo, "assert": o_assert,
           "text": lambda it, pos, named, child, sc, res, line: o_skip(it, line, "text() lettering")}


def o_skip(it, line, what):
    """Decoration the interpreter cannot draw: leave it out and say so, instead of failing the whole part."""
    note = f"SKIPPED: line {line}: {what} is not available, so it was left out of the model."
    if note not in it.echo:
        it.echo.append(note)
    return []

# Parameters: top-level assignments like  `width = 40; // Width of the base [10:200]`  become editable fields.
PARAM = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?|true|false)\s*;\s*(?://\s*(.*))?$", re.M)


def parameters(src):
    out = []
    for m in PARAM.finditer(src):
        if m.group(1).startswith("$"):
            continue
        note = (m.group(3) or "").strip()
        rng = re.search(r"\[\s*([-+]?\d*\.?\d+)\s*:\s*([-+]?\d*\.?\d+)(?:\s*:\s*([-+]?\d*\.?\d+))?\s*\]", note)
        raw = m.group(2)
        value = raw == "true" if raw in ("true", "false") else float(raw)
        label = re.sub(r"\s*\[.*?\]\s*", " ", note).strip()
        label = re.sub(r"[\s,]*\(?\b(?:in\s+)?(?:mm|millimet(?:er|re)s?)\b\)?\s*$", "", label, flags=re.I).strip(" -:,")
        item = {"name": m.group(1), "value": value, "label": label or m.group(1)}
        if rng:
            lo, hi = float(rng.group(1)), float(rng.group(3) or rng.group(2))
            step = float(rng.group(2)) if rng.group(3) else None
            item.update(min=lo, max=hi, step=step)
        out.append(item)
    # only the first block of parameters at the top counts (later assignments are usually derived values)
    return out[:24]


def build(src, overrides=None):
    """(polygons, echo lines) for an OpenSCAD source; raises CadError with a line number on problems."""
    if not isinstance(src, str) or not src.strip():
        raise CadError("The model is empty.")
    if len(src) > 60_000:
        raise CadError("The model source is too long (over 60,000 characters).")
    tree = Parser(src).program()
    it = Interpreter({k: v for k, v in (overrides or {}).items() if isinstance(v, (int, float, bool))})
    objs = it.run_block(tree[1], Scope())
    objs = [o for o in objs if o is not None]
    solids = [o for o in objs if not isinstance(o, Shape2)]
    if not solids:
        if objs:
            raise CadError("The model is only 2D; extrude it with linear_extrude() to print it.")
        raise CadError("The model produced no solid (is everything inside a disabled * block?).")
    out = it.combine("union", solids)
    if not out:
        raise CadError("The model is empty after the boolean operations (a difference removed everything?).")
    return out, it.echo
