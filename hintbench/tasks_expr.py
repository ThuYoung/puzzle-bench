"""Track B3: self-contained expression-language evaluators with grammar traps.

The strongest residual failure mode of frontier models on single-file bugs is
spec-conformity checking against COUNTER-INTUITIVE rules: a model that "fixes"
by rewriting with standard-grammar idioms (right-associative power, Python
precedence tiers, chained comparisons) fails the hidden suite even when every
planted-fault line looks locally reasonable. Each task here:

  - documents a small expression language whose grammar VIOLATES common
    language conventions on exactly two points (the traps) — stated as a
    formal grammar plus abstract rules, with NO worked examples for the
    trap rules, so an implementation must be grounded in the formal spec
    rather than in example-checking,
  - plants TWO interacting faults that implement the conventional grammar
    instead of the documented one — symptoms mask each other, so a single
    shotgun rewrite rarely lands both,
  - keeps public tests free of traps (green on the buggy source), while the
    hidden suite probes each trap alone, both combined, plus documented rules
    the buggy source already honours (idiom-rewrite detectors).

Diagnosis metadata (fault_choices/fault_answer) feeds the post-solve
diagnosis probe: the true statement names BOTH planted faults, distractors
name only one or blame a rule the implementation gets right.
"""

from __future__ import annotations

from hintbench.mutate import changed_region
from hintbench.seeds_debug import _t
from hintbench.tasks_debug import DebugTask

# -- E1: Zolarith (integer arithmetic) ------------------------------------------

_ZOL_HEAD = '''"""Zolarith: a tiny integer expression language.

Grammar (loosest to tightest binding):
  expr   := term (('+' | '-') term)*
  term   := factor (('*' | '//' | '%') factor)*
  factor := power ('^' power)*
  power  := '-' power | atom
  atom   := INT | '(' expr ')'

'^' is LEFT-associative (unlike conventional arithmetic).
Unary '-' binds TIGHTER than '^' (unlike Python).
'//' floors toward negative infinity: -7 // 3 == -3.
'%' takes the sign of the DIVIDEND: -7 % 3 == -1 and 7 % -3 == 1.
A negative exponent raises ValueError; '//' or '%' by zero raises
ZeroDivisionError.
"""


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            out.append(text[i:j])
            i = j
        elif text.startswith("//", i):
            out.append("//")
            i += 2
        elif ch in "+-*%^()":
            out.append(ch)
            i += 1
        else:
            raise SyntaxError(f"bad character: {ch!r}")
    return out


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._t = tokens
        self._i = 0

    def _peek(self) -> str | None:
        return self._t[self._i] if self._i < len(self._t) else None

    def _eat(self, tok: str) -> None:
        if self._peek() != tok:
            raise SyntaxError(f"expected {tok!r}, got {self._peek()!r}")
        self._i += 1

    def parse(self) -> int:
        value = self._expr()
        if self._peek() is not None:
            raise SyntaxError("trailing input")
        return value

    def _expr(self) -> int:
        value = self._term()
        while self._peek() in ("+", "-"):
            op = self._t[self._i]
            self._i += 1
            rhs = self._term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _term(self) -> int:
        value = self._factor()
        while self._peek() in ("*", "//", "%"):
            op = self._t[self._i]
            self._i += 1
            rhs = self._factor()
            if op == "*":
                value = value * rhs
            elif op == "//":
                value = value // rhs
            else:
                rem = abs(value) % abs(rhs)
                value = rem if value >= 0 else -rem
        return value

'''

_ZOL_TAIL = '''
    def _atom(self) -> int:
        tok = self._peek()
        if tok == "(":
            self._eat("(")
            value = self._expr()
            self._eat(")")
            return value
        if tok is None or not tok.isdigit():
            raise SyntaxError(f"expected number, got {tok!r}")
        self._i += 1
        return int(tok)


def zolarith(text: str) -> int:
    """Evaluate a Zolarith expression (grammar in the module docstring)."""
    return _Parser(_tokens(text)).parse()
'''

# spec-conformant: left-associative '^' loop, unary minus below the power level
_ZOL_FACTOR_FIXED = '''    def _factor(self) -> int:
        value = self._power()
        while self._peek() == "^":
            self._i += 1
            rhs = self._power()
            if rhs < 0:
                raise ValueError("negative exponent")
            value = value ** rhs
        return value

    def _power(self) -> int:
        if self._peek() == "-":
            self._i += 1
            return -self._power()
        return self._atom()
'''

# planted pair: (b1) '^' recurses right, (b2) unary minus wraps the whole chain
_ZOL_FACTOR_BUGGY = '''    def _factor(self) -> int:
        if self._peek() == "-":
            self._i += 1
            return -self._factor()
        value = self._power()
        if self._peek() == "^":
            self._i += 1
            rhs = self._factor()
            if rhs < 0:
                raise ValueError("negative exponent")
            return value ** rhs
        return value

    def _power(self) -> int:
        return self._atom()
'''

# wrong variant: b1 repaired (left-associative loop), b2 alive
_ZOL_FACTOR_W1 = '''    def _factor(self) -> int:
        if self._peek() == "-":
            self._i += 1
            return -self._factor()
        value = self._power()
        while self._peek() == "^":
            self._i += 1
            rhs = self._power()
            if rhs < 0:
                raise ValueError("negative exponent")
            value = value ** rhs
        return value

    def _power(self) -> int:
        return self._atom()
'''

# wrong variant: b2 repaired (unary minus tight), b1 alive
_ZOL_FACTOR_W2 = '''    def _factor(self) -> int:
        value = self._power()
        if self._peek() == "^":
            self._i += 1
            rhs = self._factor()
            if rhs < 0:
                raise ValueError("negative exponent")
            return value ** rhs
        return value

    def _power(self) -> int:
        if self._peek() == "-":
            self._i += 1
            return -self._power()
        return self._atom()
'''

_ZOL_FIXED = _ZOL_HEAD + _ZOL_FACTOR_FIXED + _ZOL_TAIL
_ZOL_BUGGY = _ZOL_HEAD + _ZOL_FACTOR_BUGGY + _ZOL_TAIL
_ZOL_W1 = _ZOL_HEAD + _ZOL_FACTOR_W1 + _ZOL_TAIL
_ZOL_W2 = _ZOL_HEAD + _ZOL_FACTOR_W2 + _ZOL_TAIL
# wrong variant: conventional divisor-sign modulo on top of the planted pair
_ZOL_W3 = _ZOL_BUGGY.replace(
    "                rem = abs(value) % abs(rhs)\n"
    "                value = rem if value >= 0 else -rem",
    "                value = value % rhs",
)
assert _ZOL_W3 != _ZOL_BUGGY

_ZOL_TESTS = (
    _t("test_add_mul",
       "    assert solution.zolarith(\"10 + 2 * 3\") == 16"),
    _t("test_parens",
       "    assert solution.zolarith(\"(2 + 3) * 4\") == 20"),
    _t("test_sub_left",
       "    assert solution.zolarith(\"10 - 3 - 2\") == 5"),
    _t("test_power_single",
       "    assert solution.zolarith(\"2 ^ 10\") == 1024"),
    _t("test_power_chain_left",
       "    got = solution.zolarith(\"2 ^ 3 ^ 2\")\n"
       "    assert got == 64, f\"expected 64 (left-assoc), got {got}\""),
    _t("test_unary_minus_tight",
       "    got = solution.zolarith(\"-2 ^ 2\")\n"
       "    assert got == 4, f\"expected 4 (unary binds tighter), got {got}\""),
    _t("test_unary_and_chain",
       "    got = solution.zolarith(\"-2 ^ 3 ^ 2\")\n"
       "    assert got == 64, f\"expected 64, got {got}\""),
    _t("test_minus_squared_chain",
       "    got = solution.zolarith(\"-3 ^ 2 ^ 2\")\n"
       "    assert got == 81, f\"expected 81, got {got}\""),
    _t("test_mod_dividend_sign",
       "    got = solution.zolarith(\"-7 % 3\")\n"
       "    assert got == -1, f\"expected -1 (dividend sign), got {got}\""),
    _t("test_mod_negative_rhs",
       "    got = solution.zolarith(\"7 % -3\")\n"
       "    assert got == 1, f\"expected 1 (dividend sign), got {got}\""),
    _t("test_floor_div_negative",
       "    assert solution.zolarith(\"-7 // 3\") == -3"),
    _t("test_negative_exponent",
       "    try:\n"
       "        solution.zolarith(\"2 ^ -3\")\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError for negative exponent\")"),
    _t("test_unary_alone",
       "    assert solution.zolarith(\"-5\") == -5"),
)

_ZOL_PUBLIC = (
    _t("test_public_example",
       "    got = solution.zolarith(\"2 + 3 * 4\")\n"
       "    assert got == 14, f\"expected 14, got {got}\""),
    _t("test_public_power",
       "    assert solution.zolarith(\"2 ^ 3\") == 8"),
)

_ZOL_SKETCH = (
    "Two grammar faults in the power level: the '^' branch recurses into "
    "_factor (making '^' right-associative), and unary minus is parsed in "
    "_factor ABOVE the power chain (so it wraps the whole chain). Per the "
    "docstring '^' is left-associative and unary minus binds tighter than '^'."
)

_ZOL_CHOICES = (
    "'^' is parsed right-associative; unary '-' follows the spec.",
    "Unary '-' is bound looser than '^'; '^' associativity follows the spec.",
    "'%' takes the sign of the divisor; both '^' and unary '-' follow the spec.",
    "Two planted faults: '^' is parsed right-associative, and unary '-' is bound looser than '^'.",
)

# -- E2: Zoologic (logic over integers) -----------------------------------------

_ZOO_HEAD = '''"""Zoologic: a tiny logic language over integers.

Grammar:
  expr  := unary (BINOP unary)*
  unary := 'not' unary | atom
  atom  := INT | '(' expr ')'

Every binary operator (and, or, ==, !=, <, <=, >, >=) binds EQUALLY: an
expression is evaluated strictly LEFT to right (comparisons therefore do
NOT chain). 'not' binds TIGHTER than every binary operator.

Truth: 0 is false, anything else is true. Every operator yields 1 or 0.
"""

import re

_TOKEN = re.compile(r"\\s*(and|or|not|==|!=|<=|>=|\\d+|<|>|\\(|\\))")

_BINOPS = ("and", "or", "==", "!=", "<", "<=", ">", ">=")


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    end = len(text.rstrip())
    while i < end:
        m = _TOKEN.match(text, i)
        if m is None:
            raise SyntaxError(f"bad token at {text[i:]!r}")
        out.append(m.group(1))
        i = m.end()
    return out


def _apply(op: str, a: int, b: int) -> int:
    if op == "and":
        return 1 if a and b else 0
    if op == "or":
        return 1 if a or b else 0
    if op == "==":
        return 1 if a == b else 0
    if op == "!=":
        return 1 if a != b else 0
    if op == "<":
        return 1 if a < b else 0
    if op == "<=":
        return 1 if a <= b else 0
    if op == ">":
        return 1 if a > b else 0
    if op == ">=":
        return 1 if a >= b else 0
    raise SyntaxError(f"unknown operator {op!r}")


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._t = tokens
        self._i = 0

    def _peek(self) -> str | None:
        return self._t[self._i] if self._i < len(self._t) else None

    def _eat(self, tok: str) -> None:
        if self._peek() != tok:
            raise SyntaxError(f"expected {tok!r}, got {self._peek()!r}")
        self._i += 1

    def parse(self) -> int:
        value = self._expr()
        if self._peek() is not None:
            raise SyntaxError("trailing input")
        return value

'''

_ZOO_TAIL = '''
    def _atom(self) -> int:
        tok = self._peek()
        if tok == "(":
            self._eat("(")
            value = self._expr()
            self._eat(")")
            return value
        if tok is None or not tok.isdigit():
            raise SyntaxError(f"expected number, got {tok!r}")
        self._i += 1
        return int(tok)


def zoologic(text: str) -> int:
    """Evaluate a Zoologic expression (grammar in the module docstring)."""
    return _Parser(_tokens(text)).parse()
'''

# spec-conformant: one flat left-to-right binary level, tight unary 'not'
_ZOO_METHODS_FIXED = '''    def _expr(self) -> int:
        value = self._unary()
        while self._peek() in _BINOPS:
            op = self._t[self._i]
            self._i += 1
            rhs = self._unary()
            value = _apply(op, value, rhs)
        return value

    def _unary(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._unary() else 1
        return self._atom()
'''

# planted pair: (b1) conventional or/and/comparison precedence tiers,
# (b2) 'not' hoisted above the whole expression
_ZOO_METHODS_BUGGY = '''    def _expr(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._expr() else 1
        value = self._and_expr()
        while self._peek() == "or":
            self._i += 1
            rhs = self._and_expr()
            value = _apply("or", value, rhs)
        return value

    def _and_expr(self) -> int:
        value = self._cmp_expr()
        while self._peek() == "and":
            self._i += 1
            rhs = self._cmp_expr()
            value = _apply("and", value, rhs)
        return value

    def _cmp_expr(self) -> int:
        value = self._unary()
        while self._peek() in ("==", "!=", "<", "<=", ">", ">="):
            op = self._t[self._i]
            self._i += 1
            rhs = self._unary()
            value = _apply(op, value, rhs)
        return value

    def _unary(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._unary() else 1
        return self._atom()
'''

# wrong variant: b1 repaired (flat binary level), b2 alive
_ZOO_METHODS_W1 = '''    def _expr(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._expr() else 1
        value = self._unary()
        while self._peek() in _BINOPS:
            op = self._t[self._i]
            self._i += 1
            rhs = self._unary()
            value = _apply(op, value, rhs)
        return value

    def _unary(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._unary() else 1
        return self._atom()
'''

# wrong variant: b2 repaired (tight unary not), b1 alive
_ZOO_METHODS_W2 = '''    def _expr(self) -> int:
        value = self._and_expr()
        while self._peek() == "or":
            self._i += 1
            rhs = self._and_expr()
            value = _apply("or", value, rhs)
        return value

    def _and_expr(self) -> int:
        value = self._cmp_expr()
        while self._peek() == "and":
            self._i += 1
            rhs = self._cmp_expr()
            value = _apply("and", value, rhs)
        return value

    def _cmp_expr(self) -> int:
        value = self._unary()
        while self._peek() in ("==", "!=", "<", "<=", ">", ">="):
            op = self._t[self._i]
            self._i += 1
            rhs = self._unary()
            value = _apply(op, value, rhs)
        return value

    def _unary(self) -> int:
        if self._peek() == "not":
            self._i += 1
            return 0 if self._unary() else 1
        return self._atom()
'''

_ZOO_FIXED = _ZOO_HEAD + _ZOO_METHODS_FIXED + _ZOO_TAIL
_ZOO_BUGGY = _ZOO_HEAD + _ZOO_METHODS_BUGGY + _ZOO_TAIL
_ZOO_W1 = _ZOO_HEAD + _ZOO_METHODS_W1 + _ZOO_TAIL
_ZOO_W2 = _ZOO_HEAD + _ZOO_METHODS_W2 + _ZOO_TAIL
# wrong variant: Python-style value semantics for 'and' over the planted pair
_ZOO_W3 = _ZOO_BUGGY.replace(
    "        return 1 if a and b else 0",
    "        return a and b",
)
assert _ZOO_W3 != _ZOO_BUGGY

_ZOO_TESTS = (
    _t("test_and_basic",
       "    assert solution.zoologic(\"1 and 1\") == 1"),
    _t("test_or_basic",
       "    assert solution.zoologic(\"0 or 1\") == 1"),
    _t("test_flat_or_and",
       "    got = solution.zoologic(\"1 or 0 and 0\")\n"
       "    assert got == 0, f\"expected 0 (left-to-right), got {got}\""),
    _t("test_flat_or_and_two",
       "    got = solution.zoologic(\"1 or 1 and 0\")\n"
       "    assert got == 0, f\"expected 0 (left-to-right), got {got}\""),
    _t("test_not_tight_eq",
       "    got = solution.zoologic(\"not 1 == 2\")\n"
       "    assert got == 0, f\"expected 0 ((not 1) == 2), got {got}\""),
    _t("test_not_tight_lt",
       "    got = solution.zoologic(\"not 1 < 2\")\n"
       "    assert got == 1, f\"expected 1 ((not 1) < 2), got {got}\""),
    _t("test_no_chain",
       "    got = solution.zoologic(\"3 > 2 > 1\")\n"
       "    assert got == 0, f\"expected 0 (no chaining), got {got}\""),
    _t("test_chain_left",
       "    assert solution.zoologic(\"1 < 2 < 3\") == 1"),
    _t("test_not_not",
       "    assert solution.zoologic(\"not not 0\") == 0"),
    _t("test_parens",
       "    assert solution.zoologic(\"(1 or 0) and 0\") == 0"),
    _t("test_value_normalized",
       "    got = solution.zoologic(\"5 and 3\")\n"
       "    assert got == 1, f\"expected 1 (operators yield 1/0), got {got}\""),
    _t("test_mixed_flat",
       "    assert solution.zoologic(\"0 and 1 or 1\") == 1"),
    _t("test_not_after_op",
       "    assert solution.zoologic(\"1 or not 1\") == 1"),
)

_ZOO_PUBLIC = (
    _t("test_public_example",
       "    got = solution.zoologic(\"1 and 0\")\n"
       "    assert got == 0, f\"expected 0, got {got}\""),
    _t("test_public_not",
       "    assert solution.zoologic(\"not 0\") == 1"),
)

_ZOO_SKETCH = (
    "Two grammar faults: the flat left-to-right binary level was split into "
    "conventional precedence tiers ('and' above 'or', comparisons above "
    "that), and 'not' is hoisted to the top of _expr instead of binding as a "
    "tight unary. Per the docstring every binary operator binds equally and "
    "'not' binds tightest."
)

_ZOO_CHOICES = (
    "'and' is parsed above 'or'; 'not' follows the spec.",
    "Two planted faults: 'and' is parsed at a higher precedence than 'or', and 'not' is bound looser than the comparisons.",
    "'not' is bound looser than the comparisons; 'and'/'or' precedence follows the spec.",
    "Comparisons chain (a < b < c means a < b and b < c); every other rule follows the spec.",
)

# -- assembly -------------------------------------------------------------------


def _task(
    task_id: str,
    title: str,
    fixed: str,
    buggy: str,
    tests,
    public,
    sketch: str,
    wrong: tuple[str, ...],
    choices: tuple[str, ...],
    answer: int,
) -> DebugTask:
    from hintbench.envs.debug import run_tests

    assert buggy != fixed, task_id
    # real F2P/P2P partition from executing the buggy source; import-time so a
    # bad plant fails loudly instead of producing a mislabeled task
    outcomes = run_tests(buggy, tuple(tests))
    f2p = tuple(n for n, o in outcomes.items() if not o["passed"])
    p2p = tuple(n for n, o in outcomes.items() if o["passed"])
    assert f2p and p2p, f"{task_id}: f2p={f2p} p2p={p2p}"
    public_bad = [n for n, o in run_tests(buggy, tuple(public)).items() if not o["passed"]]
    assert not public_bad, f"{task_id}: public tests must be green on buggy, got {public_bad}"
    assert 1 <= answer <= len(choices), task_id
    return DebugTask(
        task_id=task_id,
        title=title,
        buggy_source=buggy,
        fixed_source=fixed,
        wrong_variants=wrong,
        public_tests=tuple(public),
        hidden_tests=tuple(tests),
        f2p=f2p,
        p2p=p2p,
        fault_region=changed_region(fixed, buggy),
        fix_sketch=sketch,
        fault_choices=choices,
        fault_answer=answer,
    )


EXPR_TASKS: tuple[DebugTask, ...] = (
    _task(
        "dbg_expr_zolarith_grammar",
        "zolarith: two power-level grammar faults (associativity + unary binding)",
        _ZOL_FIXED,
        _ZOL_BUGGY,
        _ZOL_TESTS,
        _ZOL_PUBLIC,
        _ZOL_SKETCH,
        (_ZOL_W1, _ZOL_W2, _ZOL_W3),
        _ZOL_CHOICES,
        4,
    ),
    _task(
        "dbg_expr_zoologic_grammar",
        "zoologic: two precedence faults (operator tiers + hoisted not)",
        _ZOO_FIXED,
        _ZOO_BUGGY,
        _ZOO_TESTS,
        _ZOO_PUBLIC,
        _ZOO_SKETCH,
        (_ZOO_W1, _ZOO_W2, _ZOO_W3),
        _ZOO_CHOICES,
        2,
    ),
)
