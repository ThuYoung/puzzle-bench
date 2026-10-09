"""Track B4: multi-file packages with cross-module planted faults.

Single-file spec-conformity checking is solved by frontier models (Track B3
pilot: two interacting counter-idiom faults located and surgically repaired
in one turn). The remaining result-layer lever is SCALE: the fault lives in
one module, the symptom surfaces through another, and the contract that
settles which side is wrong spans the interface. Each task here:

  - splits a small system over 3 modules (lexer/parser/evaluator and
    store/logic/facade), shown to the agent as separate files,
  - plants TWO faults in TWO DIFFERENT modules — both must be found; a fix
    in only one file leaves the hidden suite red,
  - documents the violated rules precisely in the module docstrings, while
    public tests stay green on the buggy package.

Module names are task-unique (zlex/zparse/zeval, ledstore/ledlogic/ledapi)
so the sandbox worker's sys.modules never collides across tasks; the entry
module is LAST in the files tuple (tests reach it as `solution`).
"""

from __future__ import annotations

from hintbench.mutate import changed_region
from hintbench.seeds_debug import _t
from hintbench.tasks_debug import DebugTask

# -- MF1: zelang (lexer / parser / evaluator) -----------------------------------

_ZLEX = '''"""zelang lexer: integer tokens and operators."""


def tokenize(text: str) -> list[str]:
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
'''

_ZPARSE_FIXED = '''"""zelang parser: recursive descent over lexer tokens.

Grammar (loosest to tightest binding):
  expr   := term (('+' | '-') term)*
  term   := factor (('*' | '//' | '%') factor)*
  factor := power ('^' power)*        # '^' is LEFT-associative
  power  := '-' power | atom          # unary '-' binds TIGHTER than '^'
  atom   := INT | '(' expr ')'

Trees: ("num", value), ("neg", child), ("bin", op, left, right).
"""

import zlex


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

    def parse(self):
        node = self._expr()
        if self._peek() is not None:
            raise SyntaxError("trailing input")
        return node

    def _expr(self):
        node = self._term()
        while self._peek() in ("+", "-"):
            op = self._t[self._i]
            self._i += 1
            rhs = self._term()
            node = ("bin", op, node, rhs)
        return node

    def _term(self):
        node = self._factor()
        while self._peek() in ("*", "//", "%"):
            op = self._t[self._i]
            self._i += 1
            rhs = self._factor()
            node = ("bin", op, node, rhs)
        return node

    def _factor(self):
        node = self._power()
        while self._peek() == "^":
            self._i += 1
            rhs = self._power()
            node = ("bin", "^", node, rhs)
        return node

    def _power(self):
        if self._peek() == "-":
            self._i += 1
            return ("neg", self._power())
        return self._atom()

    def _atom(self):
        tok = self._peek()
        if tok == "(":
            self._eat("(")
            node = self._expr()
            self._eat(")")
            return node
        if tok is None or not tok.isdigit():
            raise SyntaxError(f"expected number, got {tok!r}")
        self._i += 1
        return ("num", int(tok))


def parse(text: str):
    return _Parser(zlex.tokenize(text)).parse()
'''

# planted in zparse: '^' recurses right (conventional idiom), against the
# grammar's left-associativity; unary minus stays spec-correct (tight)
_ZPARSE_BUGGY = _ZPARSE_FIXED.replace(
    """    def _factor(self):
        node = self._power()
        while self._peek() == "^":
            self._i += 1
            rhs = self._power()
            node = ("bin", "^", node, rhs)
        return node
""",
    """    def _factor(self):
        base = self._power()
        if self._peek() == "^":
            self._i += 1
            exp = self._factor()
            return ("bin", "^", base, exp)
        return base
""",
)
assert _ZPARSE_BUGGY != _ZPARSE_FIXED

_ZEVAL_FIXED = '''"""zelang evaluator: walks the parse tree from zparse.

Language rules:
- '^' is LEFT-associative (unlike conventional arithmetic).
- Unary '-' binds TIGHTER than '^' (unlike Python).
- '//' floors toward negative infinity.
- '%' takes the sign of the DIVIDEND: -7 % 3 == -1 and 7 % -3 == 1.
A negative exponent raises ValueError; '//' or '%' by zero raises
ZeroDivisionError.
"""

import zparse


def _eval(node) -> int:
    tag = node[0]
    if tag == "num":
        return node[1]
    if tag == "neg":
        return -_eval(node[1])
    _, op, left, right = node
    a = _eval(left)
    b = _eval(right)
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "//":
        return a // b
    if op == "%":
        rem = abs(a) % abs(b)
        return rem if a >= 0 else -rem
    if op == "^":
        if b < 0:
            raise ValueError("negative exponent")
        return a ** b
    raise SyntaxError(f"unknown operator {op!r}")


def run(text: str) -> int:
    """Evaluate a zelang expression (grammar in zparse, rules above)."""
    return _eval(zparse.parse(text))
'''

# planted in zeval: Python divisor-sign '%' (the idiom), against the
# documented dividend-sign rule
_ZEVAL_BUGGY = _ZEVAL_FIXED.replace(
    """    if op == "%":
        rem = abs(a) % abs(b)
        return rem if a >= 0 else -rem
""",
    """    if op == "%":
        return a % b
""",
)
assert _ZEVAL_BUGGY != _ZEVAL_FIXED

_ZEL_FILES_FIXED = (("zlex", _ZLEX), ("zparse", _ZPARSE_FIXED), ("zeval", _ZEVAL_FIXED))
_ZEL_FILES_BUGGY = (("zlex", _ZLEX), ("zparse", _ZPARSE_BUGGY), ("zeval", _ZEVAL_BUGGY))

_ZEL_TESTS = (
    _t("test_add_mul",
       "    assert solution.run(\"10 + 2 * 3\") == 16"),
    _t("test_parens",
       "    assert solution.run(\"(2 + 3) * 4\") == 20"),
    _t("test_power_chain_left",
       "    got = solution.run(\"2 ^ 3 ^ 2\")\n"
       "    assert got == 64, f\"expected 64 (left-assoc), got {got}\""),
    _t("test_power_chain_other",
       "    got = solution.run(\"2 ^ 2 ^ 3\")\n"
       "    assert got == 64, f\"expected 64 (left-assoc), got {got}\""),
    _t("test_mod_dividend_sign",
       "    got = solution.run(\"-7 % 3\")\n"
       "    assert got == -1, f\"expected -1 (dividend sign), got {got}\""),
    _t("test_mod_negative_rhs",
       "    got = solution.run(\"7 % -3\")\n"
       "    assert got == 1, f\"expected 1 (dividend sign), got {got}\""),
    _t("test_unary_minus_tight",
       "    got = solution.run(\"-2 ^ 2\")\n"
       "    assert got == 4, f\"expected 4 (unary binds tighter), got {got}\""),
    _t("test_unary_and_chain",
       "    got = solution.run(\"-2 ^ 3 ^ 2\")\n"
       "    assert got == 64, f\"expected 64, got {got}\""),
    _t("test_floor_div",
       "    assert solution.run(\"-7 // 3\") == -3"),
    _t("test_negative_exponent",
       "    try:\n"
       "        solution.run(\"2 ^ -3\")\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError for negative exponent\")"),
    _t("test_sub_left",
       "    assert solution.run(\"10 - 3 - 2\") == 5"),
    _t("test_mod_both_negative",
       "    assert solution.run(\"-7 % -3\") == -1"),
)

_ZEL_PUBLIC = (
    _t("test_public_example",
       "    got = solution.run(\"2 + 3 * 4\")\n"
       "    assert got == 14, f\"expected 14, got {got}\""),
    _t("test_public_power",
       "    assert solution.run(\"2 ^ 3\") == 8"),
)

_ZEL_SKETCH = (
    "Two faults across the package: zparse._factor recurses into itself for "
    "'^' (making it right-associative; the grammar says left-associative), "
    "and zeval._eval applies Python's divisor-sign '%' (the documented rule "
    "is dividend sign: -7 % 3 == -1)."
)

_ZEL_CHOICES = (
    "'^' is parsed right-associative in zparse.py; the evaluator follows the spec.",
    "'%' in zeval.py follows the divisor's sign; the parser follows the spec.",
    "Two planted faults: '^' is parsed right-associative in zparse.py, and '%' in zeval.py follows the divisor's sign instead of the dividend's.",
    "Unary '-' is parsed looser than '^' in zparse.py; every other rule follows the spec.",
)

# -- MF2: ledgerd (store / logic / facade) --------------------------------------

_LEDSTORE_FIXED = '''"""ledgerd store: account rows and holds."""


class Store:
    """Balance rows plus frozen (held) amounts.

    row() hands callers a COPY: mutating the returned dict must never
    change what is stored.
    """

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, int]] = {}
        self._holds: dict[str, int] = {}

    def open(self, account: str, balance: int) -> None:
        self._rows[account] = {"balance": balance}

    def row(self, account: str) -> dict[str, int]:
        return dict(self._rows[account])

    def available(self, account: str) -> int:
        return self._rows[account]["balance"] - self._holds.get(account, 0)

    def adjust(self, account: str, delta: int) -> None:
        self._rows[account]["balance"] += delta

    def set_hold(self, account: str, amount: int) -> None:
        self._holds[account] = amount

    def clear_hold(self, account: str) -> None:
        del self._holds[account]

    def hold_of(self, account: str) -> int:
        return self._holds.get(account, 0)
'''

# planted in ledstore: row() hands out the live row dict (callers alias
# mutable state), against the documented copy contract
_LEDSTORE_BUGGY = _LEDSTORE_FIXED.replace(
    "        return dict(self._rows[account])",
    "        return self._rows[account]",
)
assert _LEDSTORE_BUGGY != _LEDSTORE_FIXED

_LEDLOGIC_FIXED = '''"""ledgerd logic: transfers and holds.

Rules:
- transfer(store, src, dst, amount) moves amount; it raises ValueError when
  the AVAILABLE funds of src are insufficient.
- hold(store, account, amount) freezes amount (available drops, the balance
  itself does not change).
- release(store, account) drops the hold. The balance NEVER changes on
  release: a cancelled hold simply vanishes (no credit, no debit).
"""


def transfer(store, src: str, dst: str, amount: int) -> None:
    if amount > store.available(src):
        raise ValueError("insufficient funds")
    store.adjust(src, -amount)
    store.adjust(dst, amount)


def hold(store, account: str, amount: int) -> None:
    if amount > store.available(account):
        raise ValueError("insufficient funds")
    store.set_hold(account, amount)


def release(store, account: str) -> None:
    amount = store.hold_of(account)
    if amount == 0:
        raise ValueError("nothing on hold")
    store.clear_hold(account)
'''

# planted in ledlogic: release() credits the balance (common instinct),
# against the documented never-credit rule
_LEDLOGIC_BUGGY = _LEDLOGIC_FIXED.replace(
    """    if amount == 0:
        raise ValueError("nothing on hold")
    store.clear_hold(account)
""",
    """    if amount == 0:
        raise ValueError("nothing on hold")
    store.clear_hold(account)
    store.adjust(account, amount)
""",
)
assert _LEDLOGIC_BUGGY != _LEDLOGIC_FIXED

_LEDAPI = '''"""ledgerd facade: accounts and the audit trail.

Facade rules:
- open_account / transfer / hold / release delegate to ledlogic.
- balance(account) is the CURRENT balance; available(account) subtracts holds.
- audit(account) returns the balance snapshots recorded after every
  operation on that account, oldest first. Snapshots are immutable: later
  operations must NEVER change an earlier audit entry.
"""

import ledlogic
import ledstore


class Api:
    def __init__(self, store: ledstore.Store) -> None:
        self._store = store
        self._audit: dict[str, list[dict[str, int]]] = {}

    def open_account(self, account: str, balance: int) -> None:
        self._store.open(account, balance)
        self._audit[account] = [self._store.row(account)]

    def transfer(self, src: str, dst: str, amount: int) -> None:
        ledlogic.transfer(self._store, src, dst, amount)
        for account in (src, dst):
            self._audit[account].append(self._store.row(account))

    def hold(self, account: str, amount: int) -> None:
        ledlogic.hold(self._store, account, amount)
        self._audit[account].append(self._store.row(account))

    def release(self, account: str) -> None:
        ledlogic.release(self._store, account)
        self._audit[account].append(self._store.row(account))

    def balance(self, account: str) -> int:
        return self._store.row(account)["balance"]

    def available(self, account: str) -> int:
        return self._store.available(account)

    def audit(self, account: str) -> list[int]:
        return [row["balance"] for row in self._audit[account]]


def make_api() -> Api:
    return Api(ledstore.Store())
'''

_LED_FILES_FIXED = (
    ("ledstore", _LEDSTORE_FIXED),
    ("ledlogic", _LEDLOGIC_FIXED),
    ("ledapi", _LEDAPI),
)
_LED_FILES_BUGGY = (
    ("ledstore", _LEDSTORE_BUGGY),
    ("ledlogic", _LEDLOGIC_BUGGY),
    ("ledapi", _LEDAPI),
)

_LED_TESTS = (
    _t("test_audit_immutable",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.transfer(\"a\", \"b\", 30)\n"
       "    got = api.audit(\"a\")\n"
       "    assert got == [100, 70], f\"audit entries must be immutable snapshots, got {got}\""),
    _t("test_audit_second_account",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.transfer(\"a\", \"b\", 30)\n"
       "    got = api.audit(\"b\")\n"
       "    assert got == [0, 30], f\"expected [0, 30], got {got}\""),
    _t("test_release_never_credits",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.hold(\"a\", 40)\n"
       "    api.release(\"a\")\n"
       "    got = api.balance(\"a\")\n"
       "    assert got == 100, f\"release must not credit, got {got}\""),
    _t("test_available_after_release",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.hold(\"a\", 40)\n"
       "    api.release(\"a\")\n"
       "    got = api.available(\"a\")\n"
       "    assert got == 100, f\"expected 100 after release, got {got}\""),
    _t("test_audit_full_sequence",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.hold(\"a\", 40)\n"
       "    api.release(\"a\")\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.transfer(\"a\", \"b\", 20)\n"
       "    got = api.audit(\"a\")\n"
       "    assert got == [100, 100, 100, 80], f\"expected [100, 100, 100, 80], got {got}\""),
    _t("test_available_during_hold",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.hold(\"a\", 40)\n"
       "    assert api.available(\"a\") == 60"),
    _t("test_insufficient_transfer",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    try:\n"
       "        api.transfer(\"a\", \"b\", 150)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
    _t("test_transfer_basic",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.transfer(\"a\", \"b\", 30)\n"
       "    assert api.balance(\"a\") == 70 and api.balance(\"b\") == 30"),
    _t("test_release_without_hold",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    try:\n"
       "        api.release(\"a\")\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
    _t("test_hold_blocks_transfer",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.hold(\"a\", 40)\n"
       "    try:\n"
       "        api.transfer(\"a\", \"b\", 70)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
)

_LED_PUBLIC = (
    _t("test_public_example",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.open_account(\"b\", 0)\n"
       "    api.transfer(\"a\", \"b\", 30)\n"
       "    got = api.balance(\"a\")\n"
       "    assert got == 70, f\"expected 70, got {got}\""),
    _t("test_public_hold",
       "    api = solution.make_api()\n"
       "    api.open_account(\"a\", 100)\n"
       "    api.hold(\"a\", 40)\n"
       "    assert api.available(\"a\") == 60"),
)

_LED_SKETCH = (
    "Two faults across the package: ledstore.Store.row() returns the live "
    "row dict instead of a copy, so audit snapshots alias mutable state and "
    "earlier entries change retroactively; and ledlogic.release() credits "
    "the held amount back to the balance — the spec says a released hold "
    "simply vanishes."
)

_LED_CHOICES = (
    "release() in ledlogic.py forgets to drop the hold, so released amounts stay locked.",
    "Two planted faults: row() in ledstore.py hands out the internal row dict (callers alias live state), and release() in ledlogic.py credits the balance on release.",
    "row() in ledstore.py returns an internal reference; release() follows the spec.",
    "transfer() in ledlogic.py allows overdrawing by the held amount.",
)

# -- assembly -------------------------------------------------------------------


def _task(
    task_id: str,
    title: str,
    fixed_files,
    buggy_files,
    tests,
    public,
    sketch: str,
    choices: tuple[str, ...],
    answer: int,
) -> DebugTask:
    from hintbench.envs.debug import run_tests

    fixed_map = dict(fixed_files)
    buggy_map = dict(buggy_files)
    assert buggy_map != fixed_map, task_id
    # real F2P/P2P partition from executing the buggy package; import-time so
    # a bad plant fails loudly instead of producing a mislabeled task
    outcomes = run_tests(buggy_map, tuple(tests))
    f2p = tuple(n for n, o in outcomes.items() if not o["passed"])
    p2p = tuple(n for n, o in outcomes.items() if o["passed"])
    assert f2p and p2p, f"{task_id}: f2p={f2p} p2p={p2p}"
    public_bad = [n for n, o in run_tests(buggy_map, tuple(public)).items() if not o["passed"]]
    assert not public_bad, f"{task_id}: public tests must be green on buggy, got {public_bad}"
    assert 1 <= answer <= len(choices), task_id
    # one region per planted file, computed from that file's fixed/buggy diff
    regions = tuple(
        (mod, *changed_region(fixed_map[mod], src))
        for mod, src in buggy_files
        if fixed_map[mod] != src
    )
    assert len(regions) >= 2, f"{task_id}: faults must span modules, got {regions}"
    entry = buggy_files[-1][0]
    return DebugTask(
        task_id=task_id,
        title=title,
        buggy_source=buggy_map[entry],
        fixed_source=fixed_map[entry],
        wrong_variants=(),
        public_tests=tuple(public),
        hidden_tests=tuple(tests),
        f2p=f2p,
        p2p=p2p,
        fault_region=(regions[0][1], regions[0][2]),  # compat; regions authoritative
        fix_sketch=sketch,
        fault_choices=choices,
        fault_answer=answer,
        files=tuple(buggy_files),
        fixed_files=tuple(fixed_files),
        fault_regions=regions,
    )


MULTI_TASKS: tuple[DebugTask, ...] = (
    _task(
        "dbg_multi_zelang_grammar",
        "zelang: grammar fault in the parser + arithmetic fault in the evaluator",
        _ZEL_FILES_FIXED,
        _ZEL_FILES_BUGGY,
        _ZEL_TESTS,
        _ZEL_PUBLIC,
        _ZEL_SKETCH,
        _ZEL_CHOICES,
        3,
    ),
    _task(
        "dbg_multi_ledgerd_alias_credit",
        "ledgerd: store aliasing + logic crediting, symptoms at the facade",
        _LED_FILES_FIXED,
        _LED_FILES_BUGGY,
        _LED_TESTS,
        _LED_PUBLIC,
        _LED_SKETCH,
        _LED_CHOICES,
        2,
    ),
)
