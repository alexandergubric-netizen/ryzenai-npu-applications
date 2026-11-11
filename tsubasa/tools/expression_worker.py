"""Restricted expressions evaluated as data. No eval, exec, attributes or imports."""
import ast
import json
import operator
import sys

OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,
     ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod,ast.Pow:operator.pow}
FUNCTIONS={"abs":abs,"round":round,"len":len,"min":min,"max":max,"sum":sum,"sorted":sorted}

def bounded(value):
    if type(value) not in (int,float,str,list,tuple,bool,type(None)):
        raise ValueError("Unsupported value.")
    if isinstance(value,int) and value.bit_length()>4096:raise ValueError("Integer too large.")
    if isinstance(value,(str,list,tuple)) and len(value)>2000:raise ValueError("Value too large.")
    return value

def parse_expression(code):
    if not isinstance(code,str) or not 1<=len(code)<=4000:raise ValueError("Enter an expression up to 4,000 characters.")
    tree=ast.parse(code,mode="eval")
    if sum(1 for _ in ast.walk(tree))>256:raise ValueError("Expression too complex.")
    allowed=(ast.Expression,ast.Constant,ast.List,ast.Tuple,ast.Load,ast.UnaryOp,ast.UAdd,ast.USub,ast.BinOp,ast.Call,ast.Name,*OPS)
    for node in ast.walk(tree):
        if not isinstance(node,allowed):raise ValueError("Unsupported expression syntax.")
        if isinstance(node,ast.Name) and node.id not in FUNCTIONS:raise ValueError("Unknown expression name.")
        if isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in FUNCTIONS or node.keywords):
            raise ValueError("Unsupported function call.")
        if isinstance(node,ast.Constant):bounded(node.value)
    return tree

def evaluate(code):
    tree=parse_expression(code)
    def visit(node,depth=0):
        if depth>24:raise ValueError("Expression nesting exceeds limit.")
        if isinstance(node,ast.Constant):return bounded(node.value)
        if isinstance(node,(ast.List,ast.Tuple)):
            return bounded([visit(item,depth+1) for item in node.elts])
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=visit(node.operand,depth+1)
            if type(value) not in (int,float):raise ValueError("Use a numeric operand.")
            return bounded(value if isinstance(node.op,ast.UAdd) else -value)
        if isinstance(node,ast.BinOp) and type(node.op) in OPS:
            a,b=visit(node.left,depth+1),visit(node.right,depth+1)
            if type(a) not in (int,float) or type(b) not in (int,float):raise ValueError("Arithmetic requires numbers.")
            if isinstance(node.op,ast.Pow) and (abs(b)>100 or abs(a)>1e12):raise ValueError("Power exceeds limit.")
            return bounded(OPS[type(node.op)](a,b))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            return bounded(FUNCTIONS[node.func.id](*[visit(arg,depth+1) for arg in node.args]))
        raise ValueError("Only literals, numeric arithmetic, lists and abs/round/len/min/max/sum/sorted are supported.")
    return visit(tree.body)

if __name__=="__main__":
    try:
        code=open(sys.argv[1],encoding="utf-8").read()
        print(json.dumps({"result":evaluate(code)},ensure_ascii=True,allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error":str(exc)}))
        sys.exit(1)

