"""Debug-economy task bank (Track B prototype).

Handcrafted small bugs with hidden test suites. Each task defines the buggy
source the agent starts from, the canonical fix, plausible wrong variants
(used by scripted agents to simulate failed attempts), and the metadata the
hint ladder is built from: failing-test names, assertion messages, trimmed
tracebacks, fault region, and a fix sketch.

Freshness tier: handmade original (see spec section 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from hintbench.schema import HintSpec, MilestoneSpec, TaskSpec

# Track B standard ladder (spec section 4): cumulative full-ladder cost is 9.
DEBUG_LADDER: tuple[HintSpec, ...] = (
    HintSpec(level=1, kind="failing_test_names", cost=1),
    HintSpec(level=2, kind="assertion_details", cost=1),
    HintSpec(level=3, kind="stack_trace", cost=2),
    HintSpec(level=4, kind="fault_region", cost=2),
    HintSpec(level=5, kind="fix_sketch", cost=3),
)

# Region-revealing levels: the hint-consistency milestone only makes sense
# once the agent has been told WHERE the fault lives.
REGION_LEVELS = frozenset({4, 5})

DEBUG_MILESTONES: tuple[MilestoneSpec, ...] = (
    MilestoneSpec("format_ok", weight=0.05),
    MilestoneSpec("first_f2p_pass", weight=0.20, revealed_by=frozenset({5})),
    MilestoneSpec("all_f2p_pass", weight=0.25, revealed_by=frozenset({5})),
    MilestoneSpec("regression_guard", weight=0.10),
    MilestoneSpec("hint_consistent", weight=0.10, requires_hint_purchase=True),
    MilestoneSpec("solved", weight=0.20, revealed_by=frozenset({5})),
    # diagnosis separates "patched until green" from "understood the fault":
    # the agent names the planted fault from a multiple-choice list. L5 states
    # the fault outright, so an answer after L5 is never clean.
    MilestoneSpec("diagnosis", weight=0.10, revealed_by=frozenset({5})),
)


@dataclass(frozen=True)
class DebugTask:
    task_id: str
    title: str
    buggy_source: str
    fixed_source: str
    wrong_variants: tuple[str, ...]
    public_tests: tuple[tuple[str, str], ...]
    hidden_tests: tuple[tuple[str, str], ...]
    f2p: tuple[str, ...]  # fail on the buggy source, pass on the fix
    p2p: tuple[str, ...]  # pass on both; regression guard material
    fault_region: tuple[int, int]  # 1-based inclusive lines in buggy_source
    fix_sketch: str
    # diagnosis probe: mutually exclusive fault descriptions, exactly one true;
    # empty disables the probe (milestone then exits every denominator)
    fault_choices: tuple[str, ...] = ()
    fault_answer: int = -1  # 1-based index into fault_choices
    # multi-file mode: files/fixed_files hold ((module_name, source), ...) with
    # the entry module LAST; empty means the classic single solution.py task.
    # fault_regions names (module, first, last) for every planted-fault site;
    # empty derives the single region from fault_region.
    files: tuple[tuple[str, str], ...] = ()
    fixed_files: tuple[tuple[str, str], ...] = ()
    fault_regions: tuple[tuple[str, int, int], ...] = ()


def make_debug_spec(task: DebugTask, budget: int) -> TaskSpec:
    return TaskSpec(
        task_id=task.task_id, budget=budget, hints=DEBUG_LADDER, milestones=DEBUG_MILESTONES
    )


_SUM_BUGGY = '''def sum_up_to(n: int) -> int:
    """Return 1 + 2 + ... + n for n >= 0."""
    total = 0
    for i in range(1, n):
        total += i
    return total
'''

_SUM_FIXED = '''def sum_up_to(n: int) -> int:
    """Return 1 + 2 + ... + n for n >= 0."""
    total = 0
    for i in range(1, n + 1):
        total += i
    return total
'''

TASK_SUM = DebugTask(
    task_id="dbg_hand_sum_up_to",
    title="sum_up_to: off-by-one upper bound",
    buggy_source=_SUM_BUGGY,
    fixed_source=_SUM_FIXED,
    wrong_variants=(
        _SUM_BUGGY.replace("range(1, n)", "range(0, n)"),  # same behavior, subtle non-fix
        _SUM_BUGGY.replace("total += i", "total += 1"),  # wrong accumulator
        _SUM_BUGGY.replace("range(1, n)", "range(1, n + 2)"),  # overshoot; breaks n=0
    ),
    public_tests=(
        ("test_public_example",
         "def test_public_example():\n"
         "    got = solution.sum_up_to(3)\n"
         "    assert got == 6, f\"expected 6, got {got}\"\n"),
    ),
    hidden_tests=(
        ("test_sum_three",
         "def test_sum_three():\n"
         "    got = solution.sum_up_to(3)\n"
         "    assert got == 6, f\"expected 6, got {got}\"\n"),
        ("test_sum_ten",
         "def test_sum_ten():\n"
         "    got = solution.sum_up_to(10)\n"
         "    assert got == 55, f\"expected 55, got {got}\"\n"),
        ("test_sum_one",
         "def test_sum_one():\n"
         "    got = solution.sum_up_to(1)\n"
         "    assert got == 1, f\"expected 1, got {got}\"\n"),
        ("test_sum_zero",
         "def test_sum_zero():\n"
         "    assert solution.sum_up_to(0) == 0\n"),
        ("test_returns_int",
         "def test_returns_int():\n"
         "    assert isinstance(solution.sum_up_to(4), int)\n"),
    ),
    f2p=("test_sum_three", "test_sum_ten", "test_sum_one"),
    p2p=("test_sum_zero", "test_returns_int"),
    fault_region=(4, 5),
    fix_sketch="The loop stops one short: range(1, n) excludes n itself. Make the upper bound inclusive.",
)

_CLAMP_BUGGY = '''def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x into the inclusive range [lo, hi]."""
    if x < lo:
        return lo
    if x > hi:
        return lo
    return x
'''

_CLAMP_FIXED = '''def clamp(x: float, lo: float, hi: float) -> float:
    """Clamp x into the inclusive range [lo, hi]."""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
'''

TASK_CLAMP = DebugTask(
    task_id="dbg_hand_clamp",
    title="clamp: upper branch returns the wrong bound",
    buggy_source=_CLAMP_BUGGY,
    fixed_source=_CLAMP_FIXED,
    wrong_variants=(
        _CLAMP_BUGGY.replace("    if x > hi:\n        return lo", "    if x > hi:\n        return x"),
        _CLAMP_BUGGY.replace("    if x < lo:\n        return lo", "    if x < lo:\n        return hi"),
    ),
    public_tests=(
        ("test_public_example",
         "def test_public_example():\n"
         "    got = solution.clamp(5, 0, 3)\n"
         "    assert got == 3, f\"expected 3, got {got}\"\n"),
    ),
    hidden_tests=(
        ("test_above",
         "def test_above():\n"
         "    got = solution.clamp(5, 0, 3)\n"
         "    assert got == 3, f\"expected 3, got {got}\"\n"),
        ("test_far_above",
         "def test_far_above():\n"
         "    got = solution.clamp(100, 0, 1)\n"
         "    assert got == 1, f\"expected 1, got {got}\"\n"),
        ("test_below",
         "def test_below():\n"
         "    assert solution.clamp(-5, 0, 3) == 0\n"),
        ("test_inside",
         "def test_inside():\n"
         "    assert solution.clamp(2, 0, 3) == 2\n"),
        ("test_at_bounds",
         "def test_at_bounds():\n"
         "    assert solution.clamp(0, 0, 3) == 0\n"
         "    assert solution.clamp(3, 0, 3) == 3\n"),
    ),
    f2p=("test_above", "test_far_above"),
    p2p=("test_below", "test_inside", "test_at_bounds"),
    fault_region=(5, 6),
    fix_sketch="The upper-limit branch returns the lower bound. Above hi, the answer should be hi.",
)

_PAL_BUGGY = '''def is_palindrome(text: str) -> bool:
    """Case-insensitive palindrome check over ASCII letters only."""
    cleaned = text
    return cleaned == cleaned[::-1]
'''

_PAL_FIXED = '''def is_palindrome(text: str) -> bool:
    """Case-insensitive palindrome check over ASCII letters only."""
    cleaned = "".join(ch.lower() for ch in text if ch.isalpha())
    return cleaned == cleaned[::-1]
'''

TASK_PALINDROME = DebugTask(
    task_id="dbg_hand_palindrome",
    title="is_palindrome: missing normalization",
    buggy_source=_PAL_BUGGY,
    fixed_source=_PAL_FIXED,
    wrong_variants=(
        _PAL_BUGGY.replace("cleaned = text", "cleaned = text.lower()"),  # case only, not punctuation
        _PAL_BUGGY.replace("return cleaned == cleaned[::-1]",
                           "return text == text[::-1].lower()"),  # edits outside the fault region
        _PAL_BUGGY.replace("cleaned = text", "cleaned = text.strip()"),
    ),
    public_tests=(
        ("test_public_example",
         "def test_public_example():\n"
         "    assert solution.is_palindrome(\"Level\") is True, \"expected True for 'Level'\"\n"),
    ),
    hidden_tests=(
        ("test_mixed_case",
         "def test_mixed_case():\n"
         "    assert solution.is_palindrome(\"Level\") is True, \"expected True for 'Level'\"\n"),
        ("test_with_spaces",
         "def test_with_spaces():\n"
         "    assert solution.is_palindrome(\"A Toyota\") is True, \"expected True for 'A Toyota'\"\n"),
        ("test_with_punct",
         "def test_with_punct():\n"
         "    got = solution.is_palindrome(\"Was it a rat I saw?\")\n"
         "    assert got is True, f\"expected True, got {got}\"\n"),
        ("test_simple",
         "def test_simple():\n"
         "    assert solution.is_palindrome(\"aba\") is True\n"),
        ("test_non",
         "def test_non():\n"
         "    assert solution.is_palindrome(\"abc\") is False\n"),
    ),
    f2p=("test_mixed_case", "test_with_spaces", "test_with_punct"),
    p2p=("test_simple", "test_non"),
    fault_region=(3, 3),
    fix_sketch="The input is never normalized: lowercase it and drop non-letters before the mirror compare.",
)

_FIZZ_BUGGY = '''def fizzbuzz(n: int) -> str:
    """Fizz for multiples of 3, Buzz for 5, FizzBuzz for 15."""
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    if n % 15 == 0:
        return "FizzBuzz"
    return str(n)
'''

_FIZZ_FIXED = '''def fizzbuzz(n: int) -> str:
    """Fizz for multiples of 3, Buzz for 5, FizzBuzz for 15."""
    if n % 15 == 0:
        return "FizzBuzz"
    if n % 3 == 0:
        return "Fizz"
    if n % 5 == 0:
        return "Buzz"
    return str(n)
'''

TASK_FIZZBUZZ = DebugTask(
    task_id="dbg_hand_fizzbuzz",
    title="fizzbuzz: combined branch shadowed by the 3-branch",
    buggy_source=_FIZZ_BUGGY,
    fixed_source=_FIZZ_FIXED,
    wrong_variants=(
        _FIZZ_BUGGY.replace('if n % 15 == 0:\n        return "FizzBuzz"',
                            'if n % 3 == 0 and n % 5 == 0:\n        return "FizzBuzz"'),
        _FIZZ_BUGGY.replace('if n % 15 == 0:', 'if n % 7 == 0:'),
    ),
    public_tests=(
        ("test_public_example",
         "def test_public_example():\n"
         "    got = solution.fizzbuzz(15)\n"
         "    assert got == \"FizzBuzz\", f\"expected FizzBuzz, got {got}\"\n"),
    ),
    hidden_tests=(
        ("test_fifteen",
         "def test_fifteen():\n"
         "    got = solution.fizzbuzz(15)\n"
         "    assert got == \"FizzBuzz\", f\"expected FizzBuzz, got {got}\"\n"),
        ("test_thirty",
         "def test_thirty():\n"
         "    got = solution.fizzbuzz(30)\n"
         "    assert got == \"FizzBuzz\", f\"expected FizzBuzz, got {got}\"\n"),
        ("test_fortyfive",
         "def test_fortyfive():\n"
         "    got = solution.fizzbuzz(45)\n"
         "    assert got == \"FizzBuzz\", f\"expected FizzBuzz, got {got}\"\n"),
        ("test_three",
         "def test_three():\n"
         "    assert solution.fizzbuzz(3) == \"Fizz\"\n"),
        ("test_five",
         "def test_five():\n"
         "    assert solution.fizzbuzz(5) == \"Buzz\"\n"),
        ("test_plain",
         "def test_plain():\n"
         "    assert solution.fizzbuzz(7) == \"7\"\n"),
    ),
    f2p=("test_fifteen", "test_thirty", "test_fortyfive"),
    p2p=("test_three", "test_five", "test_plain"),
    fault_region=(3, 8),
    fix_sketch="The 15-branch is unreachable: every multiple of 15 exits through the 3-branch first. Test the combined case before the single ones.",
)

DEBUG_TASKS: tuple[DebugTask, ...] = (TASK_SUM, TASK_CLAMP, TASK_PALINDROME, TASK_FIZZBUZZ)
