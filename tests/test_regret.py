"""Regret oracle tests: DP correctness on hand-computable matrices."""

from hintbench.protocols import optimal_allocation, regret
from hintbench.schema import EpisodeResult


def stub(s_complete: float) -> EpisodeResult:
    return EpisodeResult(
        reward=s_complete,
        s_complete=s_complete,
        s_unaided=s_complete,
        milestones=(),
        purchases=(),
    )


TARGETS = ["p0", "p1"]
LEVELS = (0, 1)
COSTS = {1: 1}

MATRIX = {
    ("p0", 0): [stub(0.2)],
    ("p0", 1): [stub(0.9)],
    ("p1", 0): [stub(0.5)],
    ("p1", 1): [stub(0.6)],
}


def test_oracle_picks_best_single_coin():
    # budget 1: spend it on p0 (+0.7 lift) rather than p1 (+0.1)
    assert optimal_allocation(MATRIX, TARGETS, LEVELS, COSTS, 1) == 0.9 + 0.5


def test_oracle_zero_budget():
    assert optimal_allocation(MATRIX, TARGETS, LEVELS, COSTS, 0) == 0.2 + 0.5


def test_oracle_respects_level_costs():
    # level 1 costs 2 here, budget 1 -> no purchases possible
    assert optimal_allocation(MATRIX, TARGETS, LEVELS, {1: 2}, 1) == 0.2 + 0.5


def test_regret_sign():
    actual = {"p0": [stub(0.2)], "p1": [stub(0.5)]}  # played as if budget ignored
    r = regret(MATRIX, TARGETS, LEVELS, COSTS, 1, actual)
    assert abs(r - 0.7) < 1e-9


def test_missing_cell_floored_by_best_lower_level():
    # adaptive protocol-A stops leave holes; owning more hints cannot lower
    # capability, so an unmeasured level inherits the best measured lower one
    sparse = {("p0", 0): [stub(0.2)]}  # no measurement at level 1
    assert optimal_allocation(sparse, ["p0"], LEVELS, COSTS, 1) == 0.2
