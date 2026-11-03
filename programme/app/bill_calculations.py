"""Bills: edit the examples/settings below; formulas themselves live in Owner layouts.

Use [Field label] references, + - * / and parentheses. Never use Python eval.
"""
import ast
import re
from decimal import Decimal, DecimalException, ROUND_HALF_UP

# EASY TO EDIT: examples to copy into a Calculated amount field in Owner.
FORMULA_EXAMPLES = {
    'Remaining': '[Amount] - [Paid]',
    'Shared bill': '[Amount] / [People]',
    'Annual cost': '[Monthly cost] * 12',
    'Discounted': '[Amount] * (1 - [Discount percent] / 100)',
}
DECIMAL_PLACES = 2
MAX_ABSOLUTE_AMOUNT = Decimal('1000000000000')


def parse(formula, fields):
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 500:
        raise ValueError('Enter a formula of up to 500 characters.')
    references = {}
    def ref(match):
        name = match.group(1)
        matches = [f for f in fields if f['id'] == name or f['label'] == name]
        if len(matches) != 1 or matches[0]['type'] not in ('number', 'formula'):
            raise ValueError('Formula references must identify one numeric field: ' + name)
        token = 'v' + str(len(references))
        references[token] = matches[0]['id']
        return token
    expression = re.sub(r'\[([^\]]+)\]', ref, formula)
    try:
        tree = ast.parse(expression, mode='eval')
    except (SyntaxError, RecursionError):
        raise ValueError('Use numbers, [Field labels], + - * / and parentheses.') from None
    nodes = list(ast.walk(tree))
    if len(nodes) > 150:
        raise ValueError('This formula is too complex.')
    for node in nodes:
        if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add,
                                 ast.Sub, ast.Mult, ast.Div, ast.UAdd, ast.USub,
                                 ast.Constant, ast.Name, ast.Load)):
            raise ValueError('Only arithmetic is allowed in formulas.')
        if isinstance(node, ast.Name) and node.id not in references:
            raise ValueError('Put field labels in square brackets.')
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float) or not Decimal(str(node.value)).is_finite()):
            raise ValueError('Formula constants must be finite numbers.')
    return tree.body, references


def validate(fields):
    dependencies = {}
    for f in fields:
        if f['type'] == 'formula':
            dependencies[f['id']] = set(parse(f.get('formula'), fields)[1].values())
    visited = set()
    def visit(key, trail):
        if key in trail:
            raise ValueError('Calculated fields cannot refer back to themselves.')
        if key in visited: return
        for child in dependencies.get(key, ()):
            visit(child, trail | {key})
        visited.add(key)
    for key in dependencies:
        visit(key, set())


def calculate(fields, values):
    result = dict(values)
    pending = {f['id']: f for f in fields if f['type'] == 'formula'}
    def amount(key):
        if key in pending:
            field = pending.pop(key)
            node, refs = parse(field['formula'], fields)
            def evaluate(n):
                if isinstance(n, ast.Name): return amount(refs[n.id])
                if isinstance(n, ast.Constant): return Decimal(str(n.value))
                if isinstance(n, ast.UnaryOp):
                    v = evaluate(n.operand)
                    return -v if isinstance(n.op, ast.USub) else v
                a, b = evaluate(n.left), evaluate(n.right)
                if isinstance(n.op, ast.Add): return a + b
                if isinstance(n.op, ast.Sub): return a - b
                if isinstance(n.op, ast.Mult): return a * b
                if b == 0: raise ValueError('Cannot divide by zero: ' + field['label'])
                return a / b
            value = evaluate(node)
            if not value.is_finite() or abs(value) > MAX_ABSOLUTE_AMOUNT:
                raise ValueError('Calculated amount is too large.')
            result[key] = float(value.quantize(Decimal(10) ** -DECIMAL_PLACES, rounding=ROUND_HALF_UP))
        value = result.get(key, '')
        if value in ('', None):
            raise ValueError('Fill in every numeric field used by a formula.')
        return Decimal(str(value))
    validate(fields)
    try:
        for key in list(pending): amount(key)
    except (DecimalException, OverflowError):
        raise ValueError('Invalid calculated amount.') from None
    return result
