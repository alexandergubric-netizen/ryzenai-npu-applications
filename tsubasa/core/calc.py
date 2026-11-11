"""Exact arithmetic for the chat model: small language models add and multiply unreliably, so Chat offers a
calculate tool when a message involves numbers. The expression is parsed into a syntax tree and evaluated from a
whitelist (numbers, + - * / // % **, parentheses and a few math functions); there is no eval, no names, no attributes.
"""
import ast
import math
import operator
import re

SCHEMA = {"name": "calculate", "risk": "read",
          "description": "Exact arithmetic. Use it for every sum, product, percentage, average or unit conversion instead "
                         "of calculating yourself. Example: 3*7.5 + 2*4.2, or (1250*12)*0.21, or sqrt(2*9.81*20).",
          "parameters": {"type": "object", "properties": {"expression": {"type": "string", "maxLength": 300}},
                         "required": ["expression"], "additionalProperties": False}}
# Offered when a message has a number and asks for a result.
HINT = re.compile(r"\d.*\b(total|sum|add|plus|minus|times|multiply|divide|average|mean|percent|percentage|how much|how many|"
                  r"calculate|compute|convert|cost|price|vat|tax|interest|per|rate|ratio|difference)\b|\d\s*[-+*/x×÷%^]\s*\d|"
                  r"\b(total|sum|average|calculate|compute|how much)\b.*\d", re.I | re.S)

# With an attached file the numbers are in the file, so result words alone are enough.
WORDS = re.compile(r"\b(total|sum|add up|average|mean|percent|percentage|how much|how many|calculate|compute|cost|price|"
                   r"vat|tax|difference|ratio|per cent)\b", re.I)

BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max, "log": math.log, "log10": math.log10,
         "exp": math.exp, "sin": math.sin, "cos": math.cos, "tan": math.tan, "floor": math.floor, "ceil": math.ceil}
CONSTS = {"pi": math.pi, "e": math.e}


def validate(args):
    if not isinstance(args, dict) or set(args) != {"expression"} or not isinstance(args["expression"], str) \
            or not 1 <= len(args["expression"]) <= 300:
        raise ValueError("Give one arithmetic expression of up to 300 characters.")


def _eval(node, depth=0):
    if depth > 40:
        raise ValueError("Expression too deeply nested.")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTS:
        return CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
        return UNARY[type(node.op)](_eval(node.operand, depth + 1))
    if isinstance(node, ast.BinOp) and type(node.op) in BIN:
        left, right = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise ValueError("Exponent too large.")
        return BIN[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS and not node.keywords \
            and len(node.args) <= 4:
        return FUNCS[node.func.id](*(_eval(a, depth + 1) for a in node.args))
    raise ValueError("Only numbers, + - * / // % **, parentheses and sqrt, round, min, max, abs, log, exp, sin, cos, tan, floor, ceil.")


def evaluate(expression):
    validate({"expression": expression})
    text = expression.replace("×", "*").replace("÷", "/").replace("^", "**").replace("−", "-")
    try:
        tree = ast.parse(text.strip(), mode="eval")
        value = _eval(tree)
    except (SyntaxError, ZeroDivisionError, OverflowError, TypeError) as exc:
        raise ValueError(f"Cannot calculate that: {exc}") from exc
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("The result is not a finite number.")
        value = round(value, 10)
        if value.is_integer() and abs(value) < 1e15:
            value = int(value)
    return f"{expression.strip()} = {value}"
