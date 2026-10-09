"""Seed programs for the mutation pipeline (Track B task generation).

Each seed is a CORRECT, deliberately plain implementation plus a test suite.
Mutation operators (mutate.py) break them procedurally; the execution filter
keeps only mutants that fail at least one test and keep at least one green.
Seeds are written so every operator family has sites somewhere in the bank.

Freshness tier: synthetic (spec section 3) — generated instances are new even
when the seed patterns are classic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Seed:
    name: str
    source: str
    tests: tuple[tuple[str, str], ...]
    public: tuple[tuple[str, str], ...]


def _t(name: str, body: str) -> tuple[str, str]:
    return (name, f"def {name}():\n{body}\n")


_MEDIAN3_SRC = '''def median3(a: int, b: int, c: int) -> int:
    """Return the median of the three values."""
    if a <= b <= c:
        return b
    if c <= b <= a:
        return b
    if b <= a <= c:
        return a
    return c
'''

SEED_MEDIAN3 = Seed(
    name="median3",
    source=_MEDIAN3_SRC,
    tests=(
        _t("test_sorted", "    got = solution.median3(1, 2, 3)\n    assert got == 2, f\"expected 2, got {got}\""),
        _t("test_reverse", "    got = solution.median3(3, 2, 1)\n    assert got == 2, f\"expected 2, got {got}\""),
        _t("test_mixed", "    got = solution.median3(5, 1, 3)\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_ties", "    assert solution.median3(2, 2, 1) == 2\n    assert solution.median3(4, 4, 4) == 4"),
        _t("test_negatives", "    assert solution.median3(-1, -5, -3) == -3"),
    ),
    public=(
        _t("test_public_example", "    got = solution.median3(1, 2, 3)\n    assert got == 2, f\"expected 2, got {got}\""),
    ),
)

_VOWELS_SRC = '''def count_vowels(s: str) -> int:
    """Count ASCII vowels (aeiou), case-insensitive."""
    count = 0
    for ch in s.lower():
        if ch in "aeiou":
            count += 1
    return count
'''

SEED_VOWELS = Seed(
    name="count_vowels",
    source=_VOWELS_SRC,
    tests=(
        _t("test_basic", "    got = solution.count_vowels('banana')\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_upper", "    got = solution.count_vowels('AEIOU')\n    assert got == 5, f\"expected 5, got {got}\""),
        _t("test_none", "    assert solution.count_vowels('xyz') == 0"),
        _t("test_empty", "    assert solution.count_vowels('') == 0"),
        _t("test_mixed", "    assert solution.count_vowels('Hello World') == 3"),
    ),
    public=(
        _t("test_public_example", "    got = solution.count_vowels('banana')\n    assert got == 3, f\"expected 3, got {got}\""),
    ),
)

_BSEARCH_SRC = '''def binary_search(xs: list[int], v: int) -> int:
    """Index of v in sorted xs, or -1 when absent."""
    lo, hi = 0, len(xs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if xs[mid] == v:
            return mid
        if xs[mid] < v:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
'''

SEED_BSEARCH = Seed(
    name="binary_search",
    source=_BSEARCH_SRC,
    tests=(
        _t("test_hit", "    got = solution.binary_search([1, 3, 5, 7], 5)\n    assert got == 2, f\"expected 2, got {got}\""),
        _t("test_first", "    assert solution.binary_search([1, 3, 5, 7], 1) == 0"),
        _t("test_last", "    got = solution.binary_search([1, 3, 5, 7], 7)\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_absent", "    assert solution.binary_search([1, 3, 5, 7], 4) == -1"),
        _t("test_empty", "    assert solution.binary_search([], 1) == -1"),
        _t("test_single", "    assert solution.binary_search([9], 9) == 0"),
    ),
    public=(
        _t("test_public_example", "    got = solution.binary_search([1, 3, 5, 7], 5)\n    assert got == 2, f\"expected 2, got {got}\""),
    ),
)

_COLLATZ_SRC = '''def collatz_steps(n: int) -> int:
    """Number of Collatz steps to reach 1 (n >= 1)."""
    steps = 0
    while n != 1:
        if n % 2 == 0:
            n = n // 2
        else:
            n = 3 * n + 1
        steps += 1
    return steps
'''

SEED_COLLATZ = Seed(
    name="collatz_steps",
    source=_COLLATZ_SRC,
    tests=(
        _t("test_one", "    assert solution.collatz_steps(1) == 0"),
        _t("test_two", "    got = solution.collatz_steps(2)\n    assert got == 1, f\"expected 1, got {got}\""),
        _t("test_six", "    got = solution.collatz_steps(6)\n    assert got == 8, f\"expected 8, got {got}\""),
        _t("test_power_of_two", "    assert solution.collatz_steps(16) == 4"),
        _t("test_three", "    assert solution.collatz_steps(3) == 7"),
    ),
    public=(
        _t("test_public_example", "    got = solution.collatz_steps(6)\n    assert got == 8, f\"expected 8, got {got}\""),
    ),
)

_TITLE_SRC = '''def title_case(s: str) -> str:
    """Uppercase each word's first letter, lowercase the rest."""
    words = s.split(" ")
    out = []
    for w in words:
        if len(w) > 0:
            out.append(w[0].upper() + w[1:].lower())
        else:
            out.append(w)
    return " ".join(out)
'''

SEED_TITLE = Seed(
    name="title_case",
    source=_TITLE_SRC,
    tests=(
        _t("test_basic", "    got = solution.title_case('hello world')\n    assert got == 'Hello World', f\"got {got!r}\""),
        _t("test_shouting", "    got = solution.title_case('LOUD NOISES')\n    assert got == 'Loud Noises', f\"got {got!r}\""),
        _t("test_single", "    assert solution.title_case('word') == 'Word'"),
        _t("test_empty", "    assert solution.title_case('') == ''"),
        _t("test_double_space", "    assert solution.title_case('a  b') == 'A  B'"),
    ),
    public=(
        _t("test_public_example", "    got = solution.title_case('hello world')\n    assert got == 'Hello World', f\"got {got!r}\""),
    ),
)

_RUNMAX_SRC = '''def running_max(xs: list[int]) -> list[int]:
    """Prefix maximums; empty input gives empty output."""
    out = []
    best = None
    for x in xs:
        if best is None or x > best:
            best = x
        out.append(best)
    return out
'''

SEED_RUNMAX = Seed(
    name="running_max",
    source=_RUNMAX_SRC,
    tests=(
        _t("test_basic", "    got = solution.running_max([1, 3, 2, 5, 4])\n    assert got == [1, 3, 3, 5, 5], f\"got {got}\""),
        _t("test_descending", "    got = solution.running_max([5, 4, 3])\n    assert got == [5, 5, 5], f\"got {got}\""),
        _t("test_empty", "    assert solution.running_max([]) == []"),
        _t("test_single", "    assert solution.running_max([7]) == [7]"),
        _t("test_negatives", "    assert solution.running_max([-2, -5, -1]) == [-2, -2, -1]"),
    ),
    public=(
        _t("test_public_example", "    got = solution.running_max([1, 3, 2, 5, 4])\n    assert got == [1, 3, 3, 5, 5], f\"got {got}\""),
    ),
)

_GCD_SRC = '''def gcd(a: int, b: int) -> int:
    """Greatest common divisor of non-negative a and b (not both zero)."""
    while b != 0:
        a, b = b, a % b
    return a
'''

SEED_GCD = Seed(
    name="gcd",
    source=_GCD_SRC,
    tests=(
        _t("test_basic", "    got = solution.gcd(12, 18)\n    assert got == 6, f\"expected 6, got {got}\""),
        _t("test_coprime", "    assert solution.gcd(7, 13) == 1"),
        _t("test_with_zero", "    assert solution.gcd(5, 0) == 5\n    assert solution.gcd(0, 8) == 8"),
        _t("test_same", "    assert solution.gcd(9, 9) == 9"),
        _t("test_big", "    got = solution.gcd(1071, 462)\n    assert got == 21, f\"expected 21, got {got}\""),
    ),
    public=(
        _t("test_public_example", "    got = solution.gcd(12, 18)\n    assert got == 6, f\"expected 6, got {got}\""),
    ),
)

_WORDCOUNT_SRC = '''def word_count(s: str) -> int:
    """Number of space-separated words (runs of non-space characters)."""
    count = 0
    in_word = False
    for ch in s:
        if ch != " " and not in_word:
            count += 1
            in_word = True
        if ch == " ":
            in_word = False
    return count
'''

SEED_WORDCOUNT = Seed(
    name="word_count",
    source=_WORDCOUNT_SRC,
    tests=(
        _t("test_basic", "    got = solution.word_count('the quick fox')\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_single", "    assert solution.word_count('hello') == 1"),
        _t("test_empty", "    assert solution.word_count('') == 0"),
        _t("test_multi_space", "    got = solution.word_count('a  b   c')\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_edges", "    assert solution.word_count(' hi ') == 1"),
    ),
    public=(
        _t("test_public_example", "    got = solution.word_count('the quick fox')\n    assert got == 3, f\"expected 3, got {got}\""),
    ),
)

_SUMRANGE_SRC = '''def sum_range(a: int, b: int) -> int:
    """Sum of the integers a..b inclusive (a <= b)."""
    total = 0
    for i in range(a, b + 1):
        total += i
    return total
'''

SEED_SUMRANGE = Seed(
    name="sum_range",
    source=_SUMRANGE_SRC,
    tests=(
        _t("test_basic", "    got = solution.sum_range(1, 4)\n    assert got == 10, f\"expected 10, got {got}\""),
        _t("test_single", "    assert solution.sum_range(3, 3) == 3"),
        _t("test_zero_span", "    assert solution.sum_range(0, 0) == 0"),
        _t("test_negative", "    got = solution.sum_range(-2, 2)\n    assert got == 0, f\"expected 0, got {got}\""),
        _t("test_large", "    assert solution.sum_range(1, 100) == 5050"),
    ),
    public=(
        _t("test_public_example", "    got = solution.sum_range(1, 4)\n    assert got == 10, f\"expected 10, got {got}\""),
    ),
)

SEEDS: tuple[Seed, ...] = (
    SEED_MEDIAN3,
    SEED_VOWELS,
    SEED_BSEARCH,
    SEED_COLLATZ,
    SEED_TITLE,
    SEED_RUNMAX,
    SEED_GCD,
    SEED_WORDCOUNT,
    SEED_SUMRANGE,
)

# -- harder tier ---------------------------------------------------------------
# Subtler invariants and denser edge cases: nested branches, chained
# comparisons, wrap-around indexing, multi-loop carries. Written so every
# operator family still has sites, but single-hit mutants need real reasoning
# to locate and HOM mutants interact.

_MERGE_SRC = '''def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    """Merge overlapping or touching [start, end] intervals (inclusive)."""
    if not intervals:
        return []
    ordered = sorted(intervals)
    merged = [ordered[0].copy()]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged
'''

SEED_MERGE = Seed(
    name="merge_intervals",
    source=_MERGE_SRC,
    tests=(
        _t("test_basic", "    got = solution.merge_intervals([[1, 3], [2, 4], [8, 9]])\n    assert got == [[1, 4], [8, 9]], f\"got {got}\""),
        _t("test_touching", "    got = solution.merge_intervals([[1, 2], [2, 3]])\n    assert got == [[1, 3]], f\"got {got}\""),
        _t("test_nested", "    assert solution.merge_intervals([[1, 5], [2, 3]]) == [[1, 5]]"),
        _t("test_disjoint", "    assert solution.merge_intervals([[1, 2], [4, 5]]) == [[1, 2], [4, 5]]"),
        _t("test_empty", "    assert solution.merge_intervals([]) == []"),
        _t("test_unsorted", "    got = solution.merge_intervals([[5, 7], [1, 2]])\n    assert got == [[1, 2], [5, 7]], f\"got {got}\""),
    ),
    public=(
        _t("test_public_example", "    got = solution.merge_intervals([[1, 3], [2, 4], [8, 9]])\n    assert got == [[1, 4], [8, 9]], f\"got {got}\""),
    ),
)

_ROTATED_SRC = '''def rotated_search(xs: list[int], v: int) -> int:
    """Index of v in a rotated sorted list of unique values, or -1."""
    lo, hi = 0, len(xs) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if xs[mid] == v:
            return mid
        if xs[lo] <= xs[mid]:
            if xs[lo] <= v < xs[mid]:
                hi = mid - 1
            else:
                lo = mid + 1
        else:
            if xs[mid] < v <= xs[hi]:
                lo = mid + 1
            else:
                hi = mid - 1
    return -1
'''

SEED_ROTATED = Seed(
    name="rotated_search",
    source=_ROTATED_SRC,
    tests=(
        _t("test_hit_rotated", "    got = solution.rotated_search([4, 5, 6, 7, 0, 1, 2], 0)\n    assert got == 4, f\"expected 4, got {got}\""),
        _t("test_absent", "    assert solution.rotated_search([4, 5, 6, 7, 0, 1, 2], 3) == -1"),
        _t("test_first", "    got = solution.rotated_search([6, 7, 1, 2, 3, 4, 5], 6)\n    assert got == 0, f\"expected 0, got {got}\""),
        _t("test_pivot_neighbor", "    assert solution.rotated_search([2, 1], 1) == 1"),
        _t("test_empty", "    assert solution.rotated_search([], 1) == -1"),
        _t("test_single_hit", "    assert solution.rotated_search([1], 1) == 0"),
    ),
    public=(
        _t("test_public_example", "    got = solution.rotated_search([4, 5, 6, 7, 0, 1, 2], 0)\n    assert got == 4, f\"expected 4, got {got}\""),
    ),
)

_NESTING_SRC = '''def max_nesting(s: str) -> int:
    """Deepest '(' nesting level in s; -1 when the brackets are unbalanced."""
    depth = 0
    best = 0
    for ch in s:
        if ch == "(":
            depth += 1
            if depth > best:
                best = depth
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return -1
    if depth != 0:
        return -1
    return best
'''

SEED_NESTING = Seed(
    name="max_nesting",
    source=_NESTING_SRC,
    tests=(
        _t("test_basic", "    got = solution.max_nesting('(a(b)c)')\n    assert got == 2, f\"expected 2, got {got}\""),
        _t("test_unclosed", "    assert solution.max_nesting('(()') == -1"),
        _t("test_extra_close", "    assert solution.max_nesting('())') == -1"),
        _t("test_flat", "    assert solution.max_nesting('abc') == 0"),
        _t("test_separate", "    got = solution.max_nesting('()(())')\n    assert got == 2, f\"expected 2, got {got}\""),
        _t("test_empty", "    assert solution.max_nesting('') == 0"),
    ),
    public=(
        _t("test_public_example", "    got = solution.max_nesting('(a(b)c)')\n    assert got == 2, f\"expected 2, got {got}\""),
    ),
)

_RLE_SRC = '''def rle_encode(s: str) -> str:
    """Run-length encode: 'aaabb' -> 'a3b2'; single runs keep no count."""
    out = []
    i = 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        run = j - i
        out.append(s[i] if run == 1 else f"{s[i]}{run}")
        i = j
    return "".join(out)
'''

SEED_RLE = Seed(
    name="rle_encode",
    source=_RLE_SRC,
    tests=(
        _t("test_basic", "    got = solution.rle_encode('aaabb')\n    assert got == 'a3b2', f\"got {got!r}\""),
        _t("test_singles", "    got = solution.rle_encode('abc')\n    assert got == 'abc', f\"got {got!r}\""),
        _t("test_empty", "    assert solution.rle_encode('') == ''"),
        _t("test_one_run", "    assert solution.rle_encode('aaaa') == 'a4'"),
        _t("test_alternating", "    assert solution.rle_encode('aabbaa') == 'a2b2a2'"),
    ),
    public=(
        _t("test_public_example", "    got = solution.rle_encode('aaabb')\n    assert got == 'a3b2', f\"got {got!r}\""),
    ),
)

_CIRC_SRC = '''def circular_window_max(xs: list[int], k: int) -> int:
    """Max sum of k consecutive elements, wrapping around (1 <= k <= len(xs))."""
    n = len(xs)
    best = None
    for start in range(n):
        total = 0
        for step in range(k):
            total += xs[(start + step) % n]
        if best is None or total > best:
            best = total
    return best
'''

SEED_CIRC = Seed(
    name="circular_window_max",
    source=_CIRC_SRC,
    tests=(
        _t("test_basic", "    got = solution.circular_window_max([1, 2, 3, 4], 2)\n    assert got == 7, f\"expected 7, got {got}\""),
        _t("test_wrap_wins", "    got = solution.circular_window_max([5, 1, 1, 5], 2)\n    assert got == 10, f\"expected 10, got {got}\""),
        _t("test_k_one", "    assert solution.circular_window_max([3, 9, 4], 1) == 9"),
        _t("test_k_full", "    assert solution.circular_window_max([1, 2, 3], 3) == 6"),
        _t("test_single", "    assert solution.circular_window_max([7], 1) == 7"),
    ),
    public=(
        _t("test_public_example", "    got = solution.circular_window_max([1, 2, 3, 4], 2)\n    assert got == 7, f\"expected 7, got {got}\""),
    ),
)

_PLATEAU_SRC = '''def longest_plateau(xs: list[int]) -> int:
    """Length of the longest run of equal adjacent values; 0 for empty input."""
    best = 0
    run = 0
    prev = None
    for x in xs:
        if run > 0 and x == prev:
            run += 1
        else:
            run = 1
        prev = x
        if run > best:
            best = run
    return best
'''

SEED_PLATEAU = Seed(
    name="longest_plateau",
    source=_PLATEAU_SRC,
    tests=(
        _t("test_basic", "    got = solution.longest_plateau([1, 1, 2, 2, 2, 3])\n    assert got == 3, f\"expected 3, got {got}\""),
        _t("test_empty", "    assert solution.longest_plateau([]) == 0"),
        _t("test_single", "    assert solution.longest_plateau([5]) == 1"),
        _t("test_all_distinct", "    assert solution.longest_plateau([1, 2, 3]) == 1"),
        _t("test_all_same", "    got = solution.longest_plateau([4, 4, 4, 4])\n    assert got == 4, f\"expected 4, got {got}\""),
        _t("test_tie_runs", "    assert solution.longest_plateau([1, 1, 2, 2]) == 2"),
    ),
    public=(
        _t("test_public_example", "    got = solution.longest_plateau([1, 1, 2, 2, 2, 3])\n    assert got == 3, f\"expected 3, got {got}\""),
    ),
)

HARD_SEEDS: tuple[Seed, ...] = (
    SEED_MERGE,
    SEED_ROTATED,
    SEED_NESTING,
    SEED_RLE,
    SEED_CIRC,
    SEED_PLATEAU,
)

ALL_SEEDS: tuple[Seed, ...] = SEEDS + HARD_SEEDS
