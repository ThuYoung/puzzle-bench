"""Novel-spec seeds: invented mechanics that are NOT in training data.

Classic seeds (seeds_debug.py) fail at the frontier because the model
rewrites the function from memory instead of debugging it. These seeds carry
invented rule sets — the docstring is the only source of truth — so a correct
fix requires reading the spec, and each spec hides 2-3 trap clauses that a
skimming model misses (documented, so hidden tests stay fair).

Same Seed contract as seeds_debug: correct reference implementation plus a
test suite; the mutation pipeline (mutate.py) breaks them procedurally.
"""

from __future__ import annotations

from hintbench.seeds_debug import Seed, _t

# -- N1: Echo-planet calendar ---------------------------------------------------

_ECHO_SRC = '''def day_to_date(n: int) -> tuple[int, int, int]:
    """Echo-planet date conversion. A year has 4 months of 40, 39, 40, 39
    days (158 total). Years divisible by 9 are echo years: their third month
    has 41 days instead of 40. Years divisible by 81 are NEVER echo years.
    Day numbers start at 0, which is year 0, month 1, day 1.
    Return (year, month, day) with 1-based month and day."""
    months = (40, 39, 40, 39)

    def is_echo(y: int) -> bool:
        return y % 9 == 0 and y % 81 != 0

    def year_len(y: int) -> int:
        return sum(months) + (1 if is_echo(y) else 0)

    y = 0
    while n >= year_len(y):
        n -= year_len(y)
        y += 1
    lengths = list(months)
    if is_echo(y):
        lengths[2] += 1
    m = 0
    while n >= lengths[m]:
        n -= lengths[m]
        m += 1
    return (y, m + 1, n + 1)
'''

SEED_ECHO = Seed(
    name="echo_calendar",
    source=_ECHO_SRC,
    tests=(
        _t("test_origin", "    assert solution.day_to_date(0) == (0, 1, 1)"),
        _t("test_month_two_start", "    got = solution.day_to_date(40)\n    assert got == (0, 2, 1), f\"got {got}\""),
        _t("test_year_boundary", "    got = solution.day_to_date(158)\n    assert got == (1, 1, 1), f\"got {got}  (year 0 is divisible by 81, so NOT echo)\""),
        _t("test_first_echo_year", "    got = solution.day_to_date(1422)\n    assert got == (9, 1, 1), f\"got {got}\""),
        _t("test_echo_day", "    got = solution.day_to_date(1541)\n    assert got == (9, 3, 41), f\"got {got}  (year 9 month 3 has a 41st day)\""),
        _t("test_81_never_echo", "    got = solution.day_to_date(12924)\n    assert got == (81, 3, 40), f\"got {got}  (year 81 month 3 stops at 40)\""),
    ),
    public=(
        _t("test_public_example", "    got = solution.day_to_date(40)\n    assert got == (0, 2, 1), f\"got {got}\""),
    ),
)

# -- N2: Tide encoding ----------------------------------------------------------

_TIDE_SRC = '''def tide_encode(s: str) -> str:
    """Tide-encode a string. Group maximal runs of identical characters.
    Render each group as the character once, followed by the run length when
    it exceeds 1. Groups alternate case: even-indexed groups (0, 2, ...) render
    letters lowercase, odd-indexed groups uppercase; non-letters are unaffected
    by case. The input's own casing is irrelevant. Empty input renders as ''."""
    out = []
    i = 0
    group = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        ch = s[i].upper() if group % 2 == 1 else s[i].lower()
        out.append(ch)
        if j - i > 1:
            out.append(str(j - i))
        group += 1
        i = j
    return "".join(out)
'''

SEED_TIDE = Seed(
    name="tide_encode",
    source=_TIDE_SRC,
    tests=(
        _t("test_basic", "    got = solution.tide_encode('aaabb')\n    assert got == 'a3B2', f\"got {got!r}\""),
        _t("test_case_irrelevant", "    got = solution.tide_encode('AAAbb')\n    assert got == 'a3B2', f\"got {got!r}  (input casing must not matter)\""),
        _t("test_singles_alternate", "    got = solution.tide_encode('abc')\n    assert got == 'aBc', f\"got {got!r}\""),
        _t("test_long_run", "    assert solution.tide_encode('aaaaaaaaaa') == 'a10'"),
        _t("test_digit_groups", "    got = solution.tide_encode('112')\n    assert got == '122', f\"got {got!r}  ('11' -> '12', then '2' -> '2')\""),
        _t("test_empty", "    assert solution.tide_encode('') == ''"),
    ),
    public=(
        _t("test_public_example", "    got = solution.tide_encode('aaabb')\n    assert got == 'a3B2', f\"got {got!r}\""),
    ),
)

# -- N3: Mirror walk ------------------------------------------------------------

_WALK_SRC = '''def mirror_walk(grid: list[str], k: int) -> int:
    """Simulate k steps of a walk on a toroidal grid ('.' open, '#' wall).
    Start at (0, 0) facing right. Each step: look one move ahead (both edges
    wrap around); if that cell is a wall, rotate 90 degrees clockwise in place
    instead of moving, and try again; if all four directions are blocked, the
    step ends with no movement. The starting cell counts as visited.
    Return the number of distinct cells visited after k steps."""
    rows, cols = len(grid), len(grid[0])
    r = c = 0
    dr, dc = 0, 1
    visited = {(0, 0)}
    for _ in range(k):
        moved = False
        for _ in range(4):
            nr, nc = (r + dr) % rows, (c + dc) % cols
            if grid[nr][nc] != "#":
                r, c = nr, nc
                visited.add((r, c))
                moved = True
                break
            dr, dc = dc, -dr
        if not moved:
            continue
    return len(visited)
'''

SEED_WALK = Seed(
    name="mirror_walk",
    source=_WALK_SRC,
    tests=(
        _t("test_basic", "    got = solution.mirror_walk(['..#', '...', '...'], 4)\n    assert got == 4, f\"got {got}\""),
        _t("test_immediate_wall", "    got = solution.mirror_walk(['.#', '..'], 1)\n    assert got == 2, f\"got {got}  (rotate first, then move down)\""),
        _t("test_single_cell", "    assert solution.mirror_walk(['.'], 5) == 1"),
        _t("test_fully_blocked", "    got = solution.mirror_walk(['.#', '##'], 3)\n    assert got == 1, f\"got {got}  (all four directions blocked: stay)\""),
        _t("test_wrap_row", "    got = solution.mirror_walk(['...'], 3)\n    assert got == 3, f\"got {got}\""),
    ),
    public=(
        _t("test_public_example", "    got = solution.mirror_walk(['..#', '...', '...'], 4)\n    assert got == 4, f\"got {got}\""),
    ),
)

# -- N4: Balanced ternary --------------------------------------------------------

_BT_SRC = '''def to_balanced_ternary(n: int) -> str:
    """Balanced-ternary representation of n: base 3 with digits '+' (1),
    '0' (0) and '-' (-1), most significant digit first, no leading '0'.
    Zero renders as '0'. Negative n works too (its digits are the negation)."""
    if n == 0:
        return "0"
    digits = []
    x = n
    while x != 0:
        r = x % 3
        if r == 2:
            r = -1
            x += 1
        digits.append({0: "0", 1: "+", -1: "-"}[r])
        x = (x - r) // 3
    return "".join(reversed(digits))
'''

SEED_BT = Seed(
    name="balanced_ternary",
    source=_BT_SRC,
    tests=(
        _t("test_zero", "    assert solution.to_balanced_ternary(0) == '0'"),
        _t("test_two", "    got = solution.to_balanced_ternary(2)\n    assert got == '+-', f\"got {got!r}  (3 - 1)\""),
        _t("test_five", "    got = solution.to_balanced_ternary(5)\n    assert got == '+--', f\"got {got!r}  (9 - 3 - 1)\""),
        _t("test_negative", "    got = solution.to_balanced_ternary(-2)\n    assert got == '-+', f\"got {got!r}  (-3 + 1)\""),
        _t("test_borrow_chain", "    got = solution.to_balanced_ternary(8)\n    assert got == '+0-', f\"got {got!r}  (9 + 0 - 1)\""),
        _t("test_thirteen", "    assert solution.to_balanced_ternary(13) == '+++'"),
    ),
    public=(
        _t("test_public_example", "    got = solution.to_balanced_ternary(5)\n    assert got == '+--', f\"got {got!r}\""),
    ),
)

# -- N5: Skip queue --------------------------------------------------------------

_QUEUE_SRC = '''class SkipQueue:
    """A queue that skips. enqueue(x) appends x. pop() removes and returns
    the item with the highest score, where an item's score is its value minus
    its current 0-based position in the queue; ties go to the earliest
    position. pop() on an empty queue returns None. Positions re-index after
    every pop."""

    def __init__(self) -> None:
        self._items: list[int] = []

    def enqueue(self, x: int) -> None:
        self._items.append(x)

    def pop(self) -> int | None:
        if not self._items:
            return None
        best_i = 0
        best_score = self._items[0]
        for i in range(1, len(self._items)):
            score = self._items[i] - i
            if score > best_score:
                best_i = i
                best_score = score
        return self._items.pop(best_i)
'''

_QUEUE_BODY = (
    "    q = solution.SkipQueue()\n"
    "    for x in [5, 0, 10]:\n"
    "        q.enqueue(x)\n"
    "    got = q.pop()\n"
    "    assert got == 10, f\"got {got}  (scores: 5, -1, 8)\""
)

SEED_QUEUE = Seed(
    name="skip_queue",
    source=_QUEUE_SRC,
    tests=(
        _t("test_score_wins", _QUEUE_BODY),
        _t("test_ties_earliest",
           "    q = solution.SkipQueue()\n"
           "    for x in [1, 2, 3]:\n"
           "        q.enqueue(x)\n"
           "    got = [q.pop(), q.pop(), q.pop()]\n"
           "    assert got == [1, 2, 3], f\"got {got}  (all scores tie; earliest position wins)\""),
        _t("test_position_shift",
           "    q = solution.SkipQueue()\n"
           "    for x in [10, 0, 0]:\n"
           "        q.enqueue(x)\n"
           "    first = q.pop()\n"
           "    second = q.pop()\n"
           "    assert (first, second) == (10, 0), f\"got {(first, second)}\""),
        _t("test_negative_values",
           "    q = solution.SkipQueue()\n"
           "    q.enqueue(-1)\n"
           "    q.enqueue(-2)\n"
           "    got = q.pop()\n"
           "    assert got == -1, f\"got {got}\""),
        _t("test_empty_pop", "    assert solution.SkipQueue().pop() is None"),
    ),
    public=(
        _t("test_public_example", _QUEUE_BODY),
    ),
)

# -- N6: Stutter merge -----------------------------------------------------------

_STUTTER_SRC = '''def stutter_merge(a: list[int], b: list[int]) -> list[int]:
    """Stutter-merge two sorted lists into one. Normally take the smaller
    head value (ties take from a); if one side is empty, take from the other.
    Stutter rule: whenever the value just taken equals the value taken on the
    previous step, the next take is FORCED to come from the same side as this
    take, unless that side is empty. Return the merged list."""
    out = []
    i = j = 0
    last = None
    forced = None
    while i < len(a) or j < len(b):
        if forced == "a" and i < len(a):
            side = "a"
        elif forced == "b" and j < len(b):
            side = "b"
        elif i >= len(a):
            side = "b"
        elif j >= len(b):
            side = "a"
        else:
            side = "a" if a[i] <= b[j] else "b"
        v = a[i] if side == "a" else b[j]
        if side == "a":
            i += 1
        else:
            j += 1
        forced = side if v == last else None
        last = v
        out.append(v)
    return out
'''

SEED_STUTTER = Seed(
    name="stutter_merge",
    source=_STUTTER_SRC,
    tests=(
        _t("test_basic", "    got = solution.stutter_merge([1, 1, 2], [1, 3])\n    assert got == [1, 1, 2, 1, 3], f\"got {got}\""),
        _t("test_no_stutter", "    got = solution.stutter_merge([1, 3], [2, 4])\n    assert got == [1, 2, 3, 4], f\"got {got}\""),
        _t("test_stutter_chain", "    got = solution.stutter_merge([1, 1, 1], [])\n    assert got == [1, 1, 1], f\"got {got}  (stutter forces same side repeatedly)\""),
        _t("test_tie_takes_a", "    got = solution.stutter_merge([1], [1])\n    assert got == [1, 1], f\"got {got}\""),
        _t("test_forced_side_empty", "    got = solution.stutter_merge([2, 2], [1, 3])\n    assert got == [1, 2, 2, 3], f\"got {got}  (forced side empty: fall back)\""),
    ),
    public=(
        _t("test_public_example", "    got = solution.stutter_merge([1, 1, 2], [1, 3])\n    assert got == [1, 1, 2, 1, 3], f\"got {got}\""),
    ),
)

NOVEL_SEEDS: tuple[Seed, ...] = (
    SEED_ECHO,
    SEED_TIDE,
    SEED_WALK,
    SEED_BT,
    SEED_QUEUE,
    SEED_STUTTER,
)
