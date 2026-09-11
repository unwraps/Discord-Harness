"""
Calculator Skill: Safely evaluate mathematical expressions using AST.
"""

from __future__ import annotations
import ast
import math
import operator
from skills.base import skill

# Allowed operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed math functions
FUNCTIONS = {
    "abs": abs,
    "round": round,
    "pow": pow,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": math.pi,
    "e": math.e,
}


def _eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value}")
    elif isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](left, right)
        raise ValueError(f"Unsupported operator: {op_type.__name__}")
    elif isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        op_type = type(node.op)
        if op_type in OPERATORS:
            return OPERATORS[op_type](operand)
        raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
    elif isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            fn = FUNCTIONS[node.func.id]
            args = [_eval_node(arg) for arg in node.args]
            return fn(*args)
        raise ValueError(f"Unsupported function call: {ast.dump(node.func)}")
    elif isinstance(node, ast.Name):
        if node.id in FUNCTIONS:
            return FUNCTIONS[node.id]
        raise ValueError(f"Unknown variable: {node.id}")
    else:
        raise ValueError(f"Unsupported expression element: {type(node).__name__}")


@skill(
    name="calculator",
    description="Evaluate mathematical calculations. Supports arithmetic (+, -, *, /, %, **), functions (sqrt, sin, cos, round, abs, log), and constants (pi, e). Example: 'sqrt(144) + 15 * 2'",
)
def calculate(expression: str) -> str:
    """Safely calculate a mathematical expression."""
    clean_expr = expression.strip()
    try:
        parsed = ast.parse(clean_expr, mode="eval")
        result = _eval_node(parsed.body)
        return str(result)
    except Exception as e:
        return f"Calculation error: {e}"
