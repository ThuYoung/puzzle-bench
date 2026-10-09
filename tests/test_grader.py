"""Grader unit tests: attribution timing, dual read-out, denominator exclusion."""

from puzzlebench.grader import attribute, dual_scores, grade, terminal_reward
from puzzlebench.schema import HintSpec, MilestoneSpec, PurchaseEvent, TaskSpec

MILESTONES = (
    MilestoneSpec("setup", weight=0.2),
    MilestoneSpec("mechanism", weight=0.3, revealed_by=frozenset({2})),
    MilestoneSpec("answer", weight=0.5, revealed_by=frozenset({2, 3})),
    MilestoneSpec("hint_use", weight=0.1, requires_hint_purchase=True),
)


def test_achievement_before_revealing_hint_is_clean():
    events = attribute({"mechanism": 3}, [PurchaseEvent(2, 5)], MILESTONES)
    mech = next(e for e in events if e.milestone_id == "mechanism")
    assert mech.achieved and mech.clean


def test_achievement_after_revealing_hint_is_not_clean():
    events = attribute({"mechanism": 5}, [PurchaseEvent(2, 3)], MILESTONES)
    mech = next(e for e in events if e.milestone_id == "mechanism")
    assert mech.achieved and not mech.clean


def test_same_turn_purchase_taints():
    # effective-turn stamping: hint bought between turns t and t+1 stamps t+1,
    # so an achievement at t+1 used the hint
    events = attribute({"answer": 4}, [PurchaseEvent(3, 4)], MILESTONES)
    ans = next(e for e in events if e.milestone_id == "answer")
    assert ans.achieved and not ans.clean


def test_unrelated_hint_does_not_taint():
    events = attribute({"setup": 6}, [PurchaseEvent(3, 1)], MILESTONES)
    setup = next(e for e in events if e.milestone_id == "setup")
    assert setup.achieved and setup.clean


def test_dual_scores_normalize_over_applicable_only():
    # no purchases: hint_use leaves the denominator entirely (0.2+0.3+0.5)
    events = attribute({"setup": 1, "mechanism": 2}, [], MILESTONES)
    complete, unaided = dual_scores(events, MILESTONES)
    assert abs(complete - 0.5) < 1e-9
    assert complete == unaided


def test_hint_required_milestone_enters_denominator_after_purchase():
    events = attribute(
        {"setup": 1, "mechanism": 2, "hint_use": 3}, [PurchaseEvent(1, 2)], MILESTONES
    )
    complete, _ = dual_scores(events, MILESTONES)
    assert abs(complete - 0.6 / 1.1) < 1e-9


def test_terminal_reward_tiebreak():
    assert terminal_reward(1.0, 0, 5) == 1.0
    r = terminal_reward(1.0, 5, 5, lam=0.02)
    assert abs(r - 0.98) < 1e-9


def test_unaided_excludes_purchase_gated_milestones():
    # a parrot that bought its way to everything still scores 1.0 complete, but
    # the gated 0.1 weight leaves the unaided read-out entirely
    events = attribute(
        {"setup": 1, "mechanism": 2, "answer": 3, "hint_use": 3},
        [PurchaseEvent(2, 1)],
        MILESTONES,
    )
    complete, unaided = dual_scores(events, MILESTONES)
    assert abs(complete - 1.0) < 1e-9
    assert abs(unaided - 0.2) < 1e-9  # only setup is clean; denominator 0.2+0.3+0.5


def _task(hints: int = 4) -> TaskSpec:
    return TaskSpec(
        task_id="t",
        budget=0,
        hints=tuple(HintSpec(level=i + 1, kind="k", cost=1) for i in range(hints)),
        milestones=MILESTONES,
    )


def test_grants_do_not_count_as_spend():
    # turn-0 grants are protocol A instrumentation, not agent decisions
    result = grade(
        _task(),
        {"setup": 1, "mechanism": 2, "answer": 3, "hint_use": 3},
        [PurchaseEvent(1, 0), PurchaseEvent(2, 0)],
    )
    assert result.reward == result.s_complete


def test_empty_denominator_is_flagged():
    # task whose only milestone is purchase-gated + no purchase: both scores
    # default to 0.0, and meta must say the denominator was empty
    task = TaskSpec(task_id="t", budget=0, hints=(), milestones=(MILESTONES[3],))
    result = grade(task, {"hint_use": 1}, [], meta={})
    assert result.s_complete == 0.0 and result.s_unaided == 0.0
    assert result.meta["empty_denominator"] is True
    assert result.meta["applicable_weight_total"] == 0.0
