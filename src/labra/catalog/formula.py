"""A small, safe arithmetic language for calculated parameters, never `eval` (§1d).

A formula names other parameters of the same test by code, for example `TG / 5` or
`TC - HDL - TG / 5`. Allowed: numbers, parameter codes, `+ - * /`, `**`, brackets, unary minus,
and the functions in `FUNCTIONS`. A validity rule such as `TG < 400` may also use comparisons
and `and` / `or` / `not`. Anything else is refused when the formula is saved.
"""

import ast
from collections.abc import Callable, Mapping
from decimal import Decimal, DecimalException, localcontext
from typing import Any

# Arithmetic is decimal, so 64 / 1.6 ** 2 is exactly 25, as a calculator would show it.
FUNCTIONS: dict[str, Callable[..., Any]] = {
    "min": min,
    "max": max,
    "abs": abs,
    "ln": Decimal.ln,
    "log10": Decimal.log10,
}

_ONE_ARGUMENT = {"abs", "ln", "log10"}
_ARITH = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_COMPARE = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
_MAX_LENGTH = 200


class FormulaError(ValueError):
    """The formula can't be accepted; the message says why in words staff can act on."""


class NotCalculable(ArithmeticError):  # noqa: N818  reads as a result, not a failure
    """An input is missing or the arithmetic has no answer (division by zero and the like)."""


def _check(node: ast.AST, names: set[str], allow_logic: bool) -> None:
    match node:
        case ast.Expression(body=body):
            _check(body, names, allow_logic)
        case ast.Constant(value=v) if isinstance(v, int | float) and not isinstance(v, bool):
            pass
        case ast.Name(id=name) if name not in FUNCTIONS:
            names.add(name)
        case ast.BinOp(left=left, op=op, right=right) if isinstance(op, _ARITH):
            _check(left, names, allow_logic)
            _check(right, names, allow_logic)
        case ast.UnaryOp(op=ast.USub() | ast.UAdd(), operand=operand):
            _check(operand, names, allow_logic)
        case ast.UnaryOp(op=ast.Not(), operand=operand) if allow_logic:
            _check(operand, names, allow_logic)
        case ast.Call(func=ast.Name(id=fn), args=args, keywords=[]) if fn in FUNCTIONS and (
            len(args) == 1 if fn in _ONE_ARGUMENT else len(args) >= 2
        ):
            for a in args:
                _check(a, names, allow_logic)
        case ast.Compare(left=left, ops=ops, comparators=rest) if allow_logic and all(
            isinstance(o, _COMPARE) for o in ops
        ):
            for n in (left, *rest):
                _check(n, names, allow_logic)
        case ast.BoolOp(values=values) if allow_logic:
            for v in values:
                _check(v, names, allow_logic)
        case _:
            raise FormulaError(f"'{ast.unparse(node)}' isn't allowed in a formula.")


def parse(source: str, *, condition: bool = False) -> tuple[ast.Expression, set[str]]:
    """Parse and check a formula (or, with `condition`, a validity rule). Returns the tree and
    the parameter codes it uses."""
    if len(source) > _MAX_LENGTH:
        raise FormulaError(f"Keep a formula under {_MAX_LENGTH} characters.")
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError:
        raise FormulaError("The formula can't be read; check the brackets and operators.") from None
    names: set[str] = set()
    _check(tree, names, condition)
    return tree, names


def _arith(op: ast.operator, a: Decimal, b: Decimal) -> Decimal:
    match op:
        case ast.Add():
            return a + b
        case ast.Sub():
            return a - b
        case ast.Mult():
            return a * b
        case ast.Div():
            if b == 0:
                raise NotCalculable("division by zero")
            return a / b
        case _:
            if abs(b) > 10:
                raise NotCalculable("exponent too large")
            return a**b


_COMPARISONS: dict[type, Callable[[Decimal, Decimal], bool]] = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}


def _number(value: Decimal | bool) -> Decimal:
    return Decimal(value) if isinstance(value, bool) else value


def _eval(node: ast.AST, values: Mapping[str, Decimal | None]) -> Decimal | bool:
    match node:
        case ast.Expression(body=body):
            return _eval(body, values)
        case ast.Constant(value=int() | float() as v):
            return Decimal(str(v))
        case ast.Name(id=name):
            value = values.get(name)
            if value is None:
                raise NotCalculable(f"{name} has no value.")
            return value
        case ast.BinOp(left=left, op=op, right=right):
            return _arith(op, _number(_eval(left, values)), _number(_eval(right, values)))
        case ast.UnaryOp(op=ast.USub(), operand=operand):
            return -_number(_eval(operand, values))
        case ast.UnaryOp(op=ast.UAdd(), operand=operand):
            return _number(_eval(operand, values))
        case ast.UnaryOp(op=ast.Not(), operand=operand):
            return not _eval(operand, values)
        case ast.Call(func=ast.Name(id=fn), args=args):
            return FUNCTIONS[fn](*(_number(_eval(a, values)) for a in args))
        case ast.Compare(left=left, ops=ops, comparators=rest):
            terms = [_number(_eval(n, values)) for n in (left, *rest)]
            return all(
                _COMPARISONS[type(op)](a, b)
                for op, a, b in zip(ops, terms, terms[1:], strict=False)
            )
        case ast.BoolOp(op=ast.And(), values=parts):
            return all(_eval(p, values) for p in parts)
        case ast.BoolOp(values=parts):
            return any(_eval(p, values) for p in parts)
    raise FormulaError("unexpected formula")  # parse() refuses everything else


def _decimals(values: Mapping[str, Decimal | float | None]) -> dict[str, Decimal | None]:
    return {k: None if v is None else Decimal(str(v)) for k, v in values.items()}


def evaluate(source: str, values: Mapping[str, Decimal | float | None]) -> Decimal:
    """The formula's value. Raises NotCalculable when an input is missing or the arithmetic
    fails."""
    tree, _ = parse(source)
    try:
        with localcontext() as ctx:
            ctx.prec = 28
            result = _eval(tree, _decimals(values))
    except DecimalException:
        raise NotCalculable("the formula has no answer for these values") from None
    if isinstance(result, bool) or not result.is_finite():
        raise NotCalculable("the formula has no finite value")
    return result


def holds(source: str, values: Mapping[str, Decimal | float | None]) -> bool:
    """Whether a validity rule holds. An empty rule always holds; a rule whose inputs are
    missing doesn't."""
    if not source.strip():
        return True
    tree, _ = parse(source, condition=True)
    try:
        return bool(_eval(tree, _decimals(values)))
    except (NotCalculable, DecimalException):
        return False
