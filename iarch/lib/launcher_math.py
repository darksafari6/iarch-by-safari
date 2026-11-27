# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Bounded, non-evaluating calculator and offline unit conversions for the launcher."""
import ast
import re
from decimal import Decimal, DecimalException, localcontext

MAX_INPUT = 256
MAX_NODES = 80
MAX_MAGNITUDE = Decimal('1e100')


def calculate(expression):
    """Interpret arithmetic syntax, never execute Python or resolve identifiers.

    Supports decimal literals, parentheses, unary signs, + - * / % and integer
    powers (** or ^). Results and intermediate values are bounded.
    """
    if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_INPUT:
        raise ValueError('invalid expression length')
    source = expression.strip().replace('^', '**')
    # Ban Python numeric syntax (hex, complex, separators), comments and all names.
    if not re.fullmatch(r'[0-9eE+*/%().\s-]+', source):
        raise ValueError('unsupported expression')
    try:
        tree = ast.parse(source, mode='eval')
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise ValueError('invalid expression') from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError('expression too complex')

    def bounded(value):
        if not value.is_finite() or abs(value) > MAX_MAGNITUDE:
            raise ValueError('result out of range')
        return value

    def visit(node, depth=0):
        if depth > 24:
            raise ValueError('expression too deep')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            token = ast.get_source_segment(source, node)
            if not token or not re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', token):
                raise ValueError('unsupported number')
            return bounded(Decimal(token))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth + 1)
            return bounded(value if isinstance(node.op, ast.UAdd) else -value)
        if not isinstance(node, ast.BinOp):
            raise ValueError('unsupported operation')
        left = visit(node.left, depth + 1)
        right = visit(node.right, depth + 1)
        if isinstance(node.op, ast.Add): result = left + right
        elif isinstance(node.op, ast.Sub): result = left - right
        elif isinstance(node.op, ast.Mult): result = left * right
        elif isinstance(node.op, ast.Div): result = left / right
        elif isinstance(node.op, ast.Mod): result = left % right
        elif isinstance(node.op, ast.Pow):
            if right != right.to_integral_value() or abs(right) > 100:
                raise ValueError('power must be an integer between -100 and 100')
            result = left ** int(right)
        else:
            raise ValueError('unsupported operation')
        return bounded(result)

    try:
        with localcontext() as context:
            context.prec = 28
            context.Emax, context.Emin = 200, -200
            return visit(tree.body)
    except (DecimalException, OverflowError, RecursionError, ZeroDivisionError) as exc:
        raise ValueError('invalid arithmetic') from exc


# Factors relative to metres, grams, seconds, litres and bytes respectively.
_UNITS = {
    'length': {'mm': '0.001', 'cm': '0.01', 'm': '1', 'km': '1000', 'in': '0.0254', 'ft': '0.3048', 'mi': '1609.344'},
    'mass': {'mg': '0.001', 'g': '1', 'kg': '1000', 'oz': '28.349523125', 'lb': '453.59237'},
    'time': {'ms': '0.001', 's': '1', 'min': '60', 'h': '3600', 'day': '86400'},
    'volume': {'ml': '0.001', 'l': '1', 'gal': '3.785411784'},
    'data': {'b': '1', 'kb': '1000', 'mb': '1000000', 'gb': '1000000000', 'kib': '1024', 'mib': '1048576', 'gib': '1073741824'},
}
_TEMPERATURE = {'c', 'f', 'k'}


def convert(expression, source, target):
    """Convert an arithmetic value using fixed, offline unit tables."""
    if not isinstance(source, str) or not isinstance(target, str):
        raise ValueError('invalid unit')
    source, target = source.lower(), target.lower()
    value = calculate(expression)
    try:
        with localcontext() as context:
            context.prec = 28
            context.Emax, context.Emin = 200, -200
            if source in _TEMPERATURE and target in _TEMPERATURE:
                kelvin = value + Decimal('273.15') if source == 'c' else ((value - 32) * Decimal(5) / Decimal(9) + Decimal('273.15') if source == 'f' else value)
                if kelvin < 0:
                    raise ValueError('temperature below absolute zero')
                result = kelvin - Decimal('273.15') if target == 'c' else ((kelvin - Decimal('273.15')) * Decimal(9) / Decimal(5) + 32 if target == 'f' else kelvin)
            else:
                group = next((units for units in _UNITS.values() if source in units and target in units), None)
                if group is None:
                    raise ValueError('unknown or incompatible units')
                result = value * Decimal(group[source]) / Decimal(group[target])
            if not result.is_finite() or abs(result) > MAX_MAGNITUDE:
                raise ValueError('result out of range')
            return result
    except DecimalException as exc:
        raise ValueError('invalid conversion') from exc
