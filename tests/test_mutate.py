"""Mutation pipeline tests: operators, filter, determinism, task invariants."""

import pytest

from hintbench.envs.debug import run_tests
from hintbench.mutate import (
    changed_region,
    filter_outcomes,
    generate_tasks,
    op_cmp_flip,
    op_const_bump,
    op_range_bound,
    op_return_swap,
)
from hintbench.seeds_debug import SEED_MEDIAN3, SEED_SUMRANGE, SEEDS


@pytest.fixture(scope="module")
def bank():
    # one generation shared across the heavy tests (looping seeds make every
    # hanging mutant cost one filter timeout, so generate once)
    return generate_tasks(SEEDS[:4], rng_seed=1, per_seed=2, hom_per_seed=2)


def _lines_outside_region_identical(old: str, new: str, region: tuple[int, int]) -> bool:
    a, b = region
    old_lines, new_lines = old.splitlines(), new.splitlines()
    if len(old_lines) != len(new_lines):
        return False
    return all(
        old_lines[i] == new_lines[i]
        for i in range(len(old_lines))
        if not (a - 1 <= i <= b - 1)
    )


def test_cmp_flip_handles_chained_comparisons():
    mutants = op_cmp_flip(SEED_MEDIAN3.source)
    assert mutants, "chained compares must yield per-op sites"
    for m in mutants:
        assert _lines_outside_region_identical(SEED_MEDIAN3.source, m.buggy_source, m.region)


def test_return_swap_swaps_two_values():
    mutants = op_return_swap(SEED_MEDIAN3.source)
    assert mutants
    m = mutants[0]
    assert _lines_outside_region_identical(SEED_MEDIAN3.source, m.buggy_source, m.region)
    assert m.buggy_source != SEED_MEDIAN3.source


def test_range_bound_drops_offset():
    mutants = op_range_bound(SEED_SUMRANGE.source)
    dropped = [m for m in mutants if "range(a, b)" in m.buggy_source]
    assert dropped, "range(a, b + 1) should yield a range(a, b) mutant"


def test_const_bump_skips_booleans():
    src = "def f(x):\n    return x + True\n"
    assert op_const_bump(src) == []


def test_changed_region_single_line():
    old = "a = 1\nb = 2\nc = 3\n"
    new = "a = 1\nb = 99\nc = 3\n"
    assert changed_region(old, new) == (2, 2)


def test_filter_rejects_hanging_mutant():
    hanging = "def f(n):\n    while True:\n        pass\n"
    tests = (("test_f", "def test_f():\n    assert solution.f(1) is None\n"),)
    assert filter_outcomes(hanging, tests, timeout=1.0) is None


def test_filter_accepts_correct_source():
    res = filter_outcomes(SEED_SUMRANGE.source, SEED_SUMRANGE.tests, timeout=5.0)
    assert res is not None and all(res.values())


def test_generation_is_deterministic():
    # loop-free seeds: no hanging mutants, so this pair of runs stays cheap
    a = generate_tasks(SEEDS[:2], rng_seed=7, per_seed=1, hom_per_seed=1)
    b = generate_tasks(SEEDS[:2], rng_seed=7, per_seed=1, hom_per_seed=1)
    assert a == b


def test_generated_tasks_invariants(bank):
    assert bank, "small bank should generate"
    for t in bank:
        buggy = run_tests(t.buggy_source, t.hidden_tests)
        fixed = run_tests(t.fixed_source, t.hidden_tests)
        assert all(not buggy[n]["passed"] for n in t.f2p), t.task_id
        assert all(buggy[n]["passed"] for n in t.p2p), t.task_id
        assert all(o["passed"] for o in fixed.values()), t.task_id
        assert t.wrong_variants, t.task_id
        # public test is guaranteed red on the buggy source (agent gets a signal)
        pub = run_tests(t.buggy_source, t.public_tests)
        assert not all(o["passed"] for o in pub.values()), t.task_id
        # fault region text must actually differ from the fix there
        a, b = t.fault_region
        buggy_lines = t.buggy_source.splitlines()[a - 1 : b]
        fixed_lines = t.fixed_source.splitlines()[a - 1 : b]
        assert buggy_lines != fixed_lines, t.task_id


def test_hom_tasks_are_labeled(bank):
    homs = [t for t in bank if "hom_" in t.task_id]
    for t in homs:
        assert t.fix_sketch.startswith("2 changes.")
