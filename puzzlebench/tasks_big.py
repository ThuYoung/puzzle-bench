"""Track B5: volume escalation — an 11-module toy database (~800 lines).

Seven bank generations up to 3 modules were absorbed in one turn by the
frontier pilot model; the chosen next lever is VOLUME: the same planted-fault
construct embedded in a package large enough that no single careful read
covers everything. minidb is a single-SELECT-dialect toy relational engine:

  dbtypes  — value types + the comparison contract (no coercion, NULL rules)
  dblexer  — tokenizer for the SELECT dialect
  dbparse  — recursive-descent parser producing select ASTs
  dbexpr   — WHERE expression evaluation (strict booleans)
  dbstore  — typed tables, rows, insertion ids
  dbindex  — per-column hash indexes
  dbagg    — aggregate functions (count/sum/avg/min/max) over groups
  dbserde  — pipe-format row dump/load with escaping rules
  dbquery  — planning/execution: scan or index, filter, group, sort, limit
  dbtxn    — write-buffered transactions
  dbapi    — the facade (entry module; tests drive everything through it)

Three faults are planted in three different modules, each violating a rule
documented in ANOTHER module's docstring (comparison contract in dbtypes vs
fault in dbtypes.compare used by dbexpr; visibility rule in dbapi vs fault in
dbtxn.read_rows; NULL ordering contract in dbstore vs fault in dbquery's
sort). Symptoms surface only end-to-end through dbapi.select. The aggregate
and serde machinery carries no fault: it exists as reading load and as
idiom-rewrite detectors (a fourth anti-instinct rule, tie order, is also
implemented CORRECTLY in the buggy package).
"""

from __future__ import annotations

import difflib

from puzzlebench.seeds_debug import _t
from puzzlebench.tasks_debug import DebugTask


def _span(fixed: str, buggy: str) -> tuple[int, int]:
    """Line span in BUGGY covering every changed line.

    mutate.changed_region anchors pure inserts at a single line; here the
    planted coercion block is a 12-line insert and surgical precision should
    credit a surgical deletion of the whole block, so inserts are spanned
    in full.
    """
    sm = difflib.SequenceMatcher(a=fixed.splitlines(), b=buggy.splitlines())
    lines: set[int] = set()
    for tag, _, _, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        lines.update(range(j1 + 1, max(j2, j1 + 1) + 1))
    return (min(lines), max(lines)) if lines else (1, 1)

# -- dbtypes --------------------------------------------------------------------

_TYPES_FIXED = '''"""minidb value types and the comparison contract.

Values are Python int (INT), str (TEXT), or None (NULL).

Comparison contract — every comparison and every sort in the package goes
through compare():
- INT compares with INT; TEXT compares with TEXT (lexicographic,
  case-SENSITIVE).
- INT vs TEXT is NEVER coerced: comparing them raises TypeError, even when
  the string looks numeric.
- NULL equals NULL; NULL against a non-NULL value raises TypeError.
"""

INT = "INT"
TEXT = "TEXT"


def validate(type_name: str, value) -> None:
    """Arity-checked by the caller; None passes every column type."""
    if value is None:
        return
    if type_name == INT and (isinstance(value, bool) or not isinstance(value, int)):
        raise TypeError(f"expected INT, got {value!r}")
    if type_name == TEXT and not isinstance(value, str):
        raise TypeError(f"expected TEXT, got {value!r}")


def compare(a, b) -> int:
    """Three-way comparison per the module contract. Returns -1, 0 or 1."""
    if a is None or b is None:
        if a is None and b is None:
            return 0
        raise TypeError("NULL is not comparable to a value")
    if isinstance(a, bool) or isinstance(b, bool):
        raise TypeError("booleans are not orderable")
    if isinstance(a, int) and isinstance(b, int):
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    raise TypeError(f"incomparable types: {type(a).__name__} vs {type(b).__name__}")
'''

# planted b1: SQLite-style coercion of numeric TEXT instead of TypeError
_TYPES_BUGGY = _TYPES_FIXED.replace(
    """    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    raise TypeError(f"incomparable types: {type(a).__name__} vs {type(b).__name__}")
""",
    """    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    if isinstance(a, int) and isinstance(b, str):
        try:
            b = int(b)
        except ValueError:
            raise TypeError(f"incomparable types: int vs str")
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, int):
        try:
            a = int(a)
        except ValueError:
            raise TypeError(f"incomparable types: str vs int")
        return (a > b) - (a < b)
    raise TypeError(f"incomparable types: {type(a).__name__} vs {type(b).__name__}")
""",
)
assert _TYPES_BUGGY != _TYPES_FIXED

# -- dblexer --------------------------------------------------------------------

_LEXER = '''"""minidb lexer: tokens for the SELECT dialect.

Keywords are case-insensitive and reserved. String literals are single-quoted
with NO escape syntax. Integer literals are unsigned digits.
"""

import re

_KEYWORDS = {
    "select", "from", "where", "group", "order", "by", "asc", "desc", "limit",
    "and", "or", "not", "null",
}
_TOKEN = re.compile(r"\\s*('[^']*'|\\d+|[A-Za-z_]\\w*|!=|<=|>=|=|<|>|,|\\(|\\)|\\*)")


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    end = len(text.rstrip())
    while i < end:
        m = _TOKEN.match(text, i)
        if m is None:
            raise SyntaxError(f"bad token at {text[i:]!r}")
        tok = m.group(1)
        if not tok.startswith("'") and tok.lower() in _KEYWORDS:
            out.append(tok.lower())
        else:
            out.append(tok)
        i = m.end()
    return out
'''

# -- dbparse --------------------------------------------------------------------

_PARSE = '''"""minidb parser: the SELECT dialect.

  select := 'select' (col (',' col)*) 'from' name
            ('where' expr)? ('group' 'by' name)?
            ('order' 'by' name ('asc' | 'desc')?)? ('limit' INT)?
  col    := '*' | name | agg
  agg    := ('count'|'sum'|'avg'|'min'|'max') '(' ('*' | name) ')'
  expr   := or_expr
  or_expr := and_expr ('or' and_expr)*      # 'and' binds tighter than 'or'
  and_expr := unary ('and' unary)*
  unary  := 'not' unary | cmp
  cmp    := primary (('='|'!='|'<'|'<='|'>'|'>=') primary)?   # non-chainable
  primary := '(' expr ')' | name | INT | string | 'null'

Aggregates appear only in the SELECT list, never inside WHERE. ORDER BY
names a plain output column (aggregate results are not orderable).

AST: ("select", cols, table, where, group_by, order, limit); cols is ["*"]
or a list of ("col", name) / ("agg", fname, target); group_by is a name or
None; order is (name, descending) or None. Expressions: ("lit", value),
("col", name), ("cmp", op, l, r), ("and", l, r), ("or", l, r), ("not", e).
"""

import dblexer

_AGG = {"count", "sum", "avg", "min", "max"}


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._t = tokens
        self._i = 0

    def _peek(self) -> str | None:
        return self._t[self._i] if self._i < len(self._t) else None

    def _eat(self, tok: str):
        if self._peek() != tok:
            raise SyntaxError(f"expected {tok!r}, got {self._peek()!r}")
        self._i += 1
        return tok

    def parse(self):
        self._eat("select")
        cols = self._columns()
        self._eat("from")
        table = self._name()
        where = None
        if self._peek() == "where":
            self._eat("where")
            where = self._expr()
        group_by = None
        if self._peek() == "group":
            self._eat("group")
            self._eat("by")
            group_by = self._name()
        order = None
        if self._peek() == "order":
            self._eat("order")
            self._eat("by")
            col = self._name()
            descending = False
            if self._peek() in ("asc", "desc"):
                descending = self._eat(self._peek()) == "desc"
            order = (col, descending)
        limit = None
        if self._peek() == "limit":
            self._eat("limit")
            tok = self._peek()
            if tok is None or not tok.isdigit():
                raise SyntaxError("limit expects an integer")
            limit = int(self._eat(tok))
        if self._peek() is not None:
            raise SyntaxError("trailing input")
        return ("select", cols, table, where, group_by, order, limit)

    def _columns(self) -> list:
        if self._peek() == "*":
            self._eat("*")
            return ["*"]
        cols = [self._col_item()]
        while self._peek() == ",":
            self._eat(",")
            cols.append(self._col_item())
        return cols

    def _col_item(self):
        tok = self._peek()
        if tok in _AGG and self._t[self._i + 1 : self._i + 2] == ["("]:
            self._eat(tok)
            self._eat("(")
            if self._peek() == "*":
                self._eat("*")
                target = "*"
            else:
                target = self._name()
            self._eat(")")
            return ("agg", tok, target)
        return ("col", self._name())

    def _name(self) -> str:
        tok = self._peek()
        if tok is None or not tok.isidentifier() or tok in (
            "select", "from", "where", "group", "order", "by", "asc", "desc",
            "limit", "and", "or", "not", "null",
        ):
            raise SyntaxError(f"expected name, got {tok!r}")
        return self._eat(tok)

    def _expr(self):
        node = self._and()
        while self._peek() == "or":
            self._eat("or")
            node = ("or", node, self._and())
        return node

    def _and(self):
        node = self._unary()
        while self._peek() == "and":
            self._eat("and")
            node = ("and", node, self._unary())
        return node

    def _unary(self):
        if self._peek() == "not":
            self._eat("not")
            return ("not", self._unary())
        return self._cmp()

    def _cmp(self):
        left = self._primary()
        if self._peek() in ("=", "!=", "<", "<=", ">", ">="):
            op = self._eat(self._peek())
            return ("cmp", op, left, self._primary())
        return left

    def _primary(self):
        tok = self._peek()
        if tok == "(":
            self._eat("(")
            node = self._expr()
            self._eat(")")
            return node
        if tok == "null":
            self._eat("null")
            return ("lit", None)
        if tok is None:
            raise SyntaxError("unexpected end of input")
        if tok.startswith("'"):
            self._eat(tok)
            return ("lit", tok[1:-1])
        if tok.isdigit():
            self._eat(tok)
            return ("lit", int(tok))
        return ("col", self._name())


def parse(text: str):
    return _Parser(dblexer.tokenize(text)).parse()
'''

# -- dbexpr ---------------------------------------------------------------------

_EXPR = '''"""minidb expression evaluation over row dicts.

A WHERE expression must evaluate to a bool; anything else raises TypeError.
All comparisons delegate to dbtypes.compare, whose contract decides what is
comparable (no coercion ever happens here).
"""

import dbtypes


def evaluate(node, row: dict):
    tag = node[0]
    if tag == "lit":
        return node[1]
    if tag == "col":
        name = node[1]
        if name not in row:
            raise ValueError(f"no such column: {name}")
        return row[name]
    if tag == "and":
        return _bool(evaluate(node[1], row)) and _bool(evaluate(node[2], row))
    if tag == "or":
        return _bool(evaluate(node[1], row)) or _bool(evaluate(node[2], row))
    if tag == "not":
        return not _bool(evaluate(node[1], row))
    _, op, left, right = node
    a = evaluate(left, row)
    b = evaluate(right, row)
    c = dbtypes.compare(a, b)
    if op == "=":
        return c == 0
    if op == "!=":
        return c != 0
    if op == "<":
        return c < 0
    if op == "<=":
        return c <= 0
    if op == ">":
        return c > 0
    if op == ">=":
        return c >= 0
    raise SyntaxError(f"unknown operator {op!r}")


def _bool(value) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"WHERE expression must be boolean, got {value!r}")
    return value
'''

# -- dbstore --------------------------------------------------------------------

_STORE = '''"""minidb store: typed tables and insertion-ordered rows.

NULL ordering contract (consumed by every sort in dbquery): NULL sorts FIRST
in ascending order and LAST in descending order.
"""

import dbtypes


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, _Table] = {}

    def create_table(self, name: str, columns: list[tuple[str, str]]) -> None:
        if name in self._tables:
            raise ValueError(f"table exists: {name}")
        self._tables[name] = _Table(columns)

    def insert(self, table: str, values: tuple) -> int:
        t = self._table(table)
        self.validate_row(table, values)
        t.rows.append(tuple(values))
        return len(t.rows) - 1  # insertion id doubles as the tie-break key

    def validate_row(self, table: str, values: tuple) -> None:
        t = self._table(table)
        if len(values) != len(t.columns):
            raise ValueError(f"expected {len(t.columns)} values, got {len(values)}")
        for (_, type_name), value in zip(t.columns, values):
            dbtypes.validate(type_name, value)

    def rows(self, table: str) -> list[tuple[int, tuple]]:
        return list(enumerate(self._table(table).rows))

    def columns(self, table: str) -> list[tuple[str, str]]:
        return list(self._table(table).columns)

    def column_index(self, table: str, name: str) -> int:
        for i, (col, _) in enumerate(self._table(table).columns):
            if col == name:
                return i
        raise ValueError(f"no such column: {name}")

    def _table(self, name: str) -> "_Table":
        if name not in self._tables:
            raise ValueError(f"no such table: {name}")
        return self._tables[name]


class _Table:
    def __init__(self, columns: list[tuple[str, str]]) -> None:
        self.columns = list(columns)
        self.rows: list[tuple] = []
'''

# -- dbindex --------------------------------------------------------------------

_INDEX = '''"""minidb hash index: one column, value -> insertion ids.

Indexes are maintained by dbapi on every committed insert; a stale index is
never consulted for reads (dbquery checks row counts before using one).
"""


class Index:
    def __init__(self, column: str) -> None:
        self.column = column
        self._map: dict = {}

    def add(self, row_id: int, value) -> None:
        if value is None:
            return  # NULLs are not indexed
        self._map.setdefault(value, []).append(row_id)

    def lookup(self, value) -> list[int]:
        return sorted(self._map.get(value, []))

    def row_count(self) -> int:
        return sum(len(ids) for ids in self._map.values())


def build(store, table: str, column: str) -> Index:
    idx = Index(column)
    pos = store.column_index(table, column)
    for row_id, values in store.rows(table):
        idx.add(row_id, values[pos])
    return idx
'''

# -- dbagg ----------------------------------------------------------------------

_AGG_MOD = '''"""minidb aggregates: count / sum / avg / min / max over row groups.

Aggregate rules:
- count(*) counts every row of the group; count(col) skips NULLs.
- sum / avg / min / max skip NULLs; over an all-NULL group sum is 0 and
  avg / min / max are NULL.
- avg returns an INT, truncating toward zero (-5/2 is -2, not -3).
- sum / avg require INT values and raise TypeError on TEXT.
- min / max accept TEXT too (lexicographic, per the dbtypes contract).
"""

import dbtypes

FUNCS = ("count", "sum", "avg", "min", "max")


def apply(fname: str, target: str, rows: list[dict]):
    if fname == "count":
        if target == "*":
            return len(rows)
        return sum(1 for r in rows if r[target] is not None)
    values = [r[target] for r in rows if r[target] is not None]
    if fname == "sum":
        return _sum(values)
    if fname == "avg":
        if not values:
            return None
        total = _sum(values)
        q = abs(total) // len(values)
        return -q if total < 0 else q  # truncate toward zero
    if fname in ("min", "max"):
        if not values:
            return None
        best = values[0]
        for v in values[1:]:
            c = dbtypes.compare(v, best)
            if (fname == "min" and c < 0) or (fname == "max" and c > 0):
                best = v
        return best
    raise ValueError(f"unknown aggregate: {fname}")


def _sum(values: list) -> int:
    total = 0
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int):
            raise TypeError(f"SUM/AVG require INT, got {v!r}")
        total += v
    return total
'''

# -- dbserde --------------------------------------------------------------------

_SERDE = '''"""minidb row (de)serialization: one pipe-joined line per row.

Format: a header line "name:TYPE,name:TYPE", then one line per row with
values pipe-joined. In TEXT fields a backslash doubles and a pipe takes a
backslash prefix; the two-character field backslash-N is NULL. INT fields
are bare digits.
"""

import dbstore


def dump_table(store: "dbstore.Store", table: str) -> str:
    cols = store.columns(table)
    lines = [",".join(f"{name}:{type_name}" for name, type_name in cols)]
    for _, values in store.rows(table):
        lines.append("|".join(_encode(v) for v in values))
    return "\\n".join(lines) + "\\n"


def load_table(store: "dbstore.Store", name: str, text: str) -> None:
    lines = text.splitlines()
    if not lines:
        raise ValueError("empty dump")
    cols = []
    for part in lines[0].split(","):
        col, _, type_name = part.partition(":")
        cols.append((col, type_name))
    store.create_table(name, cols)
    for line in lines[1:]:
        fields = _split(line)
        if len(fields) != len(cols):
            raise ValueError(f"bad row: {line!r}")
        values = tuple(
            None if f is None else int(f) if t == "INT" else f
            for f, (_, t) in zip(fields, cols)
        )
        store.insert(name, values)


def _encode(value) -> str:
    if value is None:
        return "\\\\N"
    if isinstance(value, int):
        return str(value)
    return value.replace("\\\\", "\\\\\\\\").replace("|", "\\\\|")


def _split(line: str) -> list[str | None]:
    """Split on unescaped pipes, keeping escape pairs raw so the NULL
    sentinel (backslash-N as a whole field) is recognised before
    unescaping turns it into a plain N."""
    raw: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\\\":
            if i + 1 >= len(line):
                raise ValueError(f"dangling escape in {line!r}")
            buf.append(line[i : i + 2])
            i += 2
        elif ch == "|":
            raw.append("".join(buf))
            buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    raw.append("".join(buf))
    return [None if f == "\\\\N" else _unescape(f) for f in raw]


def _unescape(field: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(field):
        if field[i] == "\\\\":
            out.append(field[i + 1])
            i += 2
        else:
            out.append(field[i])
            i += 1
    return "".join(out)
'''

# -- dbquery --------------------------------------------------------------------

_QUERY_FIXED = '''"""minidb query execution: scan or index, filter, (group and) sort, limit.

Sort rules (the NULL contract itself lives in dbstore):
- ascending is the default; 'desc' reverses key order only.
- ties are ALWAYS broken by listing the LATER insertion first, in both
  sort directions (there is no stable-order guarantee). For grouped output
  the group that appeared LATER in the input counts as later.

Grouping: aggregates in the SELECT list without GROUP BY treat the whole
result as one group; a plain column may then only name the group column.
Grouped rows come out in first-appearance order unless ORDER BY says so.
"""

from functools import cmp_to_key

import dbagg
import dbexpr
import dbtypes


def execute(store, indexes: dict, ast, txn=None) -> list[dict]:
    _, cols, table, where, group_by, order, limit = ast
    rows = _candidate_rows(store, indexes, table, where, txn)
    kept = []
    for row_id, values in rows:
        row = _row_dict(store, table, values)
        if where is not None:
            keep = dbexpr.evaluate(where, row)
            if not isinstance(keep, bool):
                raise TypeError("WHERE must evaluate to a boolean")
            if not keep:
                continue
        kept.append((row_id, row))
    grouped = group_by is not None or (cols != ["*"] and any(c[0] == "agg" for c in cols))
    out = _aggregate(store, table, cols, group_by, kept) if grouped else kept
    if order is not None:
        col, descending = order
        if grouped:
            if out and col not in out[0][1]:
                raise ValueError(f"ORDER BY names an output column, got {col!r}")
            out = _sort(out, lambda r: r[1][col], descending)
        else:
            idx = store.column_index(table, col)
            out = _sort(out, lambda r: r[1]["__values__"][idx], descending)
    if limit is not None:
        out = out[:limit]
    if grouped:
        return [row for _, row in out]
    return [_project(row, cols) for _, row in out]


def _candidate_rows(store, indexes, table, where, txn):
    if txn is not None:
        visible = txn.read_rows(store, table)
    else:
        visible = store.rows(table)
    # index narrows candidates only for a same-type equality on its column;
    # anything else falls back to the scan (identical results either way)
    if indexes.get(table) is not None and where is not None and where[0] == "cmp":
        _, op, left, right = where
        if op == "=" and left[0] == "col" and right[0] == "lit":
            idx = indexes[table]
            if left[1] == idx.column and right[1] is not None:
                if idx.row_count() != len(store.rows(table)):
                    return visible  # stale index: scan (same results)
                col_type = dict(store.columns(table))[idx.column]
                try:
                    dbtypes.validate(col_type, right[1])
                except TypeError:
                    return visible  # scan raises via compare, as documented
                hits = set(idx.lookup(right[1]))
                return [(i, v) for i, v in visible if i in hits]
    return visible


def _aggregate(store, table, cols, group_by, rows):
    if cols == ["*"]:
        raise SyntaxError("GROUP BY and aggregates do not combine with '*'")
    plain = [c[1] for c in cols if c[0] == "col"]
    aggs = [(f, t) for c in cols if c[0] == "agg" for f, t in [c[1:]]]
    if group_by is not None:
        store.column_index(table, group_by)  # unknown column -> ValueError
    for name in plain:
        if name != group_by:
            raise ValueError(f"plain column {name!r} must be the GROUP BY column")
    for _, target in aggs:
        if target != "*":
            store.column_index(table, target)  # validates the target exists
    groups: list[tuple[tuple, list]] = []
    seen: dict[tuple, int] = {}
    for _, row in rows:
        key = (row[group_by],) if group_by is not None else ()
        if key not in seen:
            seen[key] = len(groups)
            groups.append((key, []))
        groups[seen[key]][1].append(row)
    out = []
    for seq, (key, members) in enumerate(groups):
        orow = {name: key[0] for name in plain}
        for fname, target in aggs:
            orow[f"{fname}({target})"] = dbagg.apply(fname, target, members)
        out.append((seq, orow))
    return out


def _sort(rows: list, key_of, descending: bool):
    """rows carry a tie id at [0]; the LATER tie id comes first on ties."""

    def key_cmp(x, y):
        a = key_of(x)
        b = key_of(y)
        if a is None and b is None:
            pass
        elif a is None:
            return 1 if descending else -1  # NULL first ascending, last descending
        elif b is None:
            return -1 if descending else 1
        else:
            c = dbtypes.compare(a, b)
            if c:
                return -c if descending else c
        # ties: the LATER insertion comes first, in both directions
        return (y[0] > x[0]) - (y[0] < x[0])

    return sorted(rows, key=cmp_to_key(key_cmp))


def _row_dict(store, table, values) -> dict:
    row = {name: value for (name, _), value in zip(store.columns(table), values)}
    row["__values__"] = values
    return row


def _project(row: dict, cols: list) -> dict:
    if cols == ["*"]:
        return {k: v for k, v in row.items() if k != "__values__"}
    return {c[1]: row[c[1]] for c in cols}
'''

# planted b3: NULLs always sort last (the Python workaround idiom), against
# the dbstore contract (first ascending, last descending)
_QUERY_BUGGY = _QUERY_FIXED.replace(
    """        elif a is None:
            return 1 if descending else -1  # NULL first ascending, last descending
        elif b is None:
            return -1 if descending else 1
""",
    """        elif a is None:
            return 1  # NULLs last
        elif b is None:
            return -1
""",
)
assert _QUERY_BUGGY != _QUERY_FIXED

# -- dbtxn ----------------------------------------------------------------------

_TXN_FIXED = '''"""minidb transactions: write-buffered begin/commit/rollback.

Inserts inside an open transaction are STAGED in a buffer and validated at
once; commit applies them to the store, rollback drops them.
"""


class Txn:
    def __init__(self) -> None:
        self._staged: dict[str, list[tuple]] = {}
        self._seq = 0

    def stage_insert(self, table: str, values: tuple) -> None:
        self._staged.setdefault(table, []).append(tuple(values))

    def read_rows(self, store, table: str):
        return store.rows(table)

    def commit(self, store) -> list[tuple[str, int]]:
        applied = []
        for table, staged in self._staged.items():
            for values in staged:
                applied.append((table, store.insert(table, values)))
        self._staged.clear()
        return applied

    def rollback(self) -> None:
        self._staged.clear()
'''

# planted b2: read-your-writes (the instinct), against the visibility rule
# documented in dbapi (reads see committed state only until commit)
_TXN_BUGGY = _TXN_FIXED.replace(
    """    def read_rows(self, store, table: str):
        return store.rows(table)
""",
    """    def read_rows(self, store, table: str):
        rows = store.rows(table)
        for values in self._staged.get(table, []):
            self._seq += 1
            rows.append((1_000_000 + self._seq, values))
        return rows
""",
)
assert _TXN_BUGGY != _TXN_FIXED

# -- dbapi ----------------------------------------------------------------------

_API = '''"""minidb facade: tables, indexes, transactions, SELECT.

Usage: create_table / insert / create_index are Python calls; queries are
SQL SELECT strings (see dbparse for the dialect).

Transaction visibility rule: while a transaction is open, its staged writes
are NOT visible to reads — every read sees committed state only. A staged
write becomes visible at commit and vanishes at rollback.
"""

import dbindex
import dbparse
import dbquery
import dbserde
import dbstore
import dbtxn


class MiniDB:
    def __init__(self) -> None:
        self._store = dbstore.Store()
        self._indexes: dict[str, object] = {}
        self._txn: dbtxn.Txn | None = None

    def create_table(self, name: str, columns: list[tuple[str, str]]) -> None:
        self._store.create_table(name, columns)

    def create_index(self, table: str, column: str) -> None:
        self._indexes[table] = dbindex.build(self._store, table, column)

    def insert(self, table: str, *values) -> None:
        self._store.validate_row(table, values)
        if self._txn is not None:
            self._txn.stage_insert(table, values)
            return
        row_id = self._store.insert(table, values)
        self._index_row(table, row_id, values)

    def select(self, sql: str) -> list[dict]:
        ast = dbparse.parse(sql)
        return dbquery.execute(self._store, self._indexes, ast, self._txn)

    def dump(self, table: str) -> str:
        """Snapshot one table in the dbserde pipe format."""
        return dbserde.dump_table(self._store, table)

    def load(self, name: str, text: str) -> None:
        """Load a dump into a NEW table. Indexes are not maintained by
        load; create them after loading (a stale index is never consulted)."""
        dbserde.load_table(self._store, name, text)

    def begin(self) -> None:
        if self._txn is not None:
            raise ValueError("transaction already open")
        self._txn = dbtxn.Txn()

    def commit(self) -> None:
        if self._txn is None:
            raise ValueError("no open transaction")
        for table, row_id in self._txn.commit(self._store):
            self._index_row(table, row_id, self._store.rows(table)[row_id][1])
        self._txn = None

    def rollback(self) -> None:
        if self._txn is None:
            raise ValueError("no open transaction")
        self._txn.rollback()
        self._txn = None

    def _index_row(self, table: str, row_id: int, values: tuple) -> None:
        idx = self._indexes.get(table)
        if idx is not None:
            pos = self._store.column_index(table, idx.column)
            idx.add(row_id, values[pos])


def make_db() -> MiniDB:
    return MiniDB()
'''

_DB_FILES_FIXED = (
    ("dbtypes", _TYPES_FIXED),
    ("dblexer", _LEXER),
    ("dbparse", _PARSE),
    ("dbexpr", _EXPR),
    ("dbstore", _STORE),
    ("dbindex", _INDEX),
    ("dbagg", _AGG_MOD),
    ("dbserde", _SERDE),
    ("dbquery", _QUERY_FIXED),
    ("dbtxn", _TXN_FIXED),
    ("dbapi", _API),
)
_DB_FILES_BUGGY = (
    ("dbtypes", _TYPES_BUGGY),
    ("dblexer", _LEXER),
    ("dbparse", _PARSE),
    ("dbexpr", _EXPR),
    ("dbstore", _STORE),
    ("dbindex", _INDEX),
    ("dbagg", _AGG_MOD),
    ("dbserde", _SERDE),
    ("dbquery", _QUERY_BUGGY),
    ("dbtxn", _TXN_BUGGY),
    ("dbapi", _API),
)

_SETUP = (
    "    db = solution.make_db()\n"
    "    db.create_table(\"users\", [(\"age\", \"INT\"), (\"name\", \"TEXT\")])\n"
)

_DB_TESTS = (
    _t("test_text_int_comparison_raises",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select * from users where age < '30'\")\n"
       "    except TypeError:\n"
       "        return\n"
       "    raise AssertionError(\"INT vs TEXT must raise TypeError (no coercion)\")"),
    _t("test_eq_coercion",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select * from users where age = '30'\")\n"
       "    except TypeError:\n"
       "        return\n"
       "    raise AssertionError(\"INT vs TEXT must raise TypeError (no coercion)\")"),
    _t("test_nonnumeric_text_raises",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select * from users where age < 'x'\")\n"
       "    except TypeError:\n"
       "        return\n"
       "    raise AssertionError(\"expected TypeError\")"),
    _t("test_null_order_asc",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users order by age asc\")]\n"
       "    assert got == [\"bob\", \"cid\", \"alice\"], f\"NULL must sort first ascending, got {got}\""),
    _t("test_null_order_desc",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users order by age desc\")]\n"
       "    assert got == [\"alice\", \"cid\", \"bob\"], f\"NULL must sort last descending, got {got}\""),
    _t("test_order_ties_later_first",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 30, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users order by age asc\")]\n"
       "    assert got == [\"cid\", \"bob\", \"alice\"], f\"ties must list the later insertion first, got {got}\""),
    _t("test_order_desc_ties_later_first",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 30, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users order by age desc\")]\n"
       "    assert got == [\"bob\", \"alice\", \"cid\"], f\"desc ties must still list the later insertion first, got {got}\""),
    _t("test_txn_uncommitted_invisible",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.begin()\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    got = db.select(\"select * from users\")\n"
       "    db.rollback()\n"
       "    assert len(got) == 1, f\"staged writes must not be visible before commit, got {got}\""),
    _t("test_txn_commit_then_visible",
       _SETUP +
       "    db.begin()\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    db.commit()\n"
       "    got = db.select(\"select * from users\")\n"
       "    assert len(got) == 1 and got[0][\"name\"] == \"bob\""),
    _t("test_txn_rollback_drops",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.begin()\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    db.rollback()\n"
       "    assert db.select(\"select * from users\") == [{\"age\": 30, \"name\": \"alice\"}]"),
    _t("test_txn_null_order_combined",
       _SETUP +
       "    db.begin()\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    inside = db.select(\"select * from users\")\n"
       "    db.commit()\n"
       "    after = [r[\"name\"] for r in db.select(\"select name from users order by age asc\")]\n"
       "    assert inside == [], f\"staged writes must be invisible, got {inside}\"\n"
       "    assert after == [\"bob\", \"cid\"], f\"NULL must sort first, got {after}\""),
    _t("test_where_must_be_boolean",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select * from users where age\")\n"
       "    except TypeError:\n"
       "        return\n"
       "    raise AssertionError(\"non-boolean WHERE must raise TypeError\")"),
    _t("test_case_sensitive_text",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    got = db.select(\"select * from users where name = 'ALICE'\")\n"
       "    assert got == [], f\"TEXT comparison is case-sensitive, got {got}\""),
    _t("test_index_stays_consistent",
       _SETUP +
       "    db.create_index(\"users\", \"age\")\n"
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    db.insert(\"users\", 30, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users where age = 30\")]\n"
       "    assert got == [\"alice\", \"cid\"], f\"no ORDER BY means insertion order, got {got}\""),
    _t("test_null_eq_null",
       _SETUP +
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", None, \"cid\")\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from users where age = null\")]\n"
       "    assert got == [\"bob\", \"cid\"], f\"NULL equals NULL, got {got}\""),
    _t("test_unknown_column_raises",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select * from users where height > 1\")\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"unknown column must raise ValueError\")"),
    _t("test_count_star",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = db.select(\"select count(*) from users\")\n"
       "    assert got == [{\"count(*)\": 3}], f\"count(*) counts NULL rows too, got {got}\""),
    _t("test_count_col_skips_null",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = db.select(\"select count(age) from users\")\n"
       "    assert got == [{\"count(age)\": 2}], f\"count(col) skips NULLs, got {got}\""),
    _t("test_sum_skips_null",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = db.select(\"select sum(age) from users\")\n"
       "    assert got == [{\"sum(age)\": 55}], f\"sum skips NULLs, got {got}\""),
    _t("test_avg_truncates_toward_zero",
       _SETUP +
       "    db.insert(\"users\", -30, \"alice\")\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    got = db.select(\"select avg(age) from users\")\n"
       "    assert got == [{\"avg(age)\": -2}], f\"avg truncates toward zero, got {got}\""),
    _t("test_min_text_lexicographic",
       _SETUP +
       "    db.insert(\"users\", 30, \"bob\")\n"
       "    db.insert(\"users\", 25, \"alice\")\n"
       "    got = db.select(\"select min(name), max(name) from users\")\n"
       "    assert got == [{\"min(name)\": \"alice\", \"max(name)\": \"bob\"}], f\"got {got}\""),
    _t("test_group_by_first_appearance",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 30, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = db.select(\"select age, count(*) from users group by age\")\n"
       "    assert got == [{\"age\": 30, \"count(*)\": 2}, {\"age\": 25, \"count(*)\": 1}], f\"got {got}\""),
    _t("test_group_by_null_key",
       _SETUP +
       "    db.insert(\"users\", None, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.insert(\"users\", 25, \"cid\")\n"
       "    got = db.select(\"select age, count(*) from users group by age\")\n"
       "    assert got == [{\"age\": None, \"count(*)\": 2}, {\"age\": 25, \"count(*)\": 1}], f\"NULLs form one group, got {got}\""),
    _t("test_group_order_null_first",
       _SETUP +
       "    db.insert(\"users\", None, \"alice\")\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    got = db.select(\"select age, count(*) from users group by age order by age asc\")\n"
       "    assert got == [{\"age\": None, \"count(*)\": 1}, {\"age\": 25, \"count(*)\": 1}], f\"NULL group sorts first ascending, got {got}\""),
    _t("test_plain_col_outside_group_raises",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    try:\n"
       "        db.select(\"select name, count(*) from users group by age\")\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"plain column outside the group must raise ValueError\")"),
    _t("test_serde_roundtrip",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", None, \"bob\")\n"
       "    db.load(\"copy\", db.dump(\"users\"))\n"
       "    assert db.select(\"select * from copy\") == db.select(\"select * from users\")"),
    _t("test_serde_escapes",
       _SETUP +
       "    db.insert(\"users\", 30, \"a|b\\\\c\")\n"
       "    db.insert(\"users\", 25, \"N\")\n"
       "    db.load(\"copy\", db.dump(\"users\"))\n"
       "    got = [r[\"name\"] for r in db.select(\"select name from copy\")]\n"
       "    assert got == [\"a|b\\\\c\", \"N\"], f\"escapes must round-trip, got {got}\""),
)

_DB_PUBLIC = (
    _t("test_public_select_all",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    got = db.select(\"select * from users\")\n"
       "    assert got == [{\"age\": 30, \"name\": \"alice\"}, {\"age\": 25, \"name\": \"bob\"}], f\"got {got}\""),
    _t("test_public_where_limit",
       _SETUP +
       "    db.insert(\"users\", 30, \"alice\")\n"
       "    db.insert(\"users\", 25, \"bob\")\n"
       "    got = db.select(\"select name from users where age >= 25 order by name asc limit 1\")\n"
       "    assert got == [{\"name\": \"alice\"}], f\"got {got}\""),
)

_DB_SKETCH = (
    "Three faults in three modules: dbtypes.compare coerces numeric TEXT into "
    "INT instead of raising TypeError (the contract says never coerce); "
    "dbtxn.Txn.read_rows appends staged writes (read-your-writes) although "
    "dbapi documents that reads see committed state only until commit; and "
    "dbquery._sort puts NULLs last in every direction although dbstore "
    "documents NULL first ascending / last descending."
)

_DB_CHOICES = (
    "Two faults: dbtypes.compare coerces numeric TEXT to INT, and dbquery sorts NULLs last in ascending order.",
    "dbtxn.read_rows merges staged writes into reads (read-your-writes); every other rule follows the spec.",
    "Three planted faults: dbtypes.compare coerces numeric TEXT instead of raising TypeError, dbtxn.read_rows makes staged writes visible before commit, and dbquery sorts NULLs last in ascending order.",
    "Three planted faults: comparisons raise TypeError too eagerly, committed writes stay invisible, and NULLs sort first in every direction.",
)


def _task() -> DebugTask:
    from puzzlebench.envs.debug import run_tests

    fixed_map = dict(_DB_FILES_FIXED)
    buggy_map = dict(_DB_FILES_BUGGY)
    # real F2P/P2P partition from executing the buggy package; import-time so
    # a bad plant fails loudly instead of producing a mislabeled task
    outcomes = run_tests(buggy_map, _DB_TESTS)
    f2p = tuple(n for n, o in outcomes.items() if not o["passed"])
    p2p = tuple(n for n, o in outcomes.items() if o["passed"])
    assert f2p and p2p, f"f2p={f2p} p2p={p2p}"
    public_bad = [n for n, o in run_tests(buggy_map, _DB_PUBLIC).items() if not o["passed"]]
    assert not public_bad, f"public tests must be green on buggy, got {public_bad}"
    regions = tuple(
        (mod, *_span(fixed_map[mod], src))
        for mod, src in _DB_FILES_BUGGY
        if fixed_map[mod] != src
    )
    assert len(regions) == 3, regions
    entry = _DB_FILES_BUGGY[-1][0]
    return DebugTask(
        task_id="dbg_big_minidb_contracts",
        title="minidb: three cross-module contract faults in a 9-module toy database",
        buggy_source=buggy_map[entry],
        fixed_source=fixed_map[entry],
        wrong_variants=(),
        public_tests=_DB_PUBLIC,
        hidden_tests=_DB_TESTS,
        f2p=f2p,
        p2p=p2p,
        fault_region=(regions[0][1], regions[0][2]),  # compat; regions authoritative
        fix_sketch=_DB_SKETCH,
        fault_choices=_DB_CHOICES,
        fault_answer=3,
        files=_DB_FILES_BUGGY,
        fixed_files=_DB_FILES_FIXED,
        fault_regions=regions,
    )


BIG_TASKS: tuple[DebugTask, ...] = (_task(),)
