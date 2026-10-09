"""Deterministic grading: attribution, dual read-out, terminal scalar.

The grader is the only component allowed to decide scores, and it never talks
back to the agent during an episode (silent channel). Attribution is purely
temporal: a milestone is "clean" when its first achievement predates every
purchase of a hint that directly reveals it (the spoil mapping). This is what
makes the unaided/completion dual read-out well-defined without trusting any
model self-report.
"""

from __future__ import annotations

from hintbench.schema import (
    EpisodeResult,
    MilestoneEvent,
    MilestoneSpec,
    PurchaseEvent,
    TaskSpec,
)

DEFAULT_LAMBDA = 0.02  # tie-break only; never part of headline reporting


def attribute(
    achieved_turns: dict[str, int],
    purchases: list[PurchaseEvent],
    milestones: tuple[MilestoneSpec, ...],
    *,
    purchased_levels: set[int] | None = None,
    not_applicable: frozenset[str] = frozenset(),
) -> list[MilestoneEvent]:
    """Attach clean/applicable flags to first-achievement turns.

    achieved_turns maps milestone_id -> turn of first achievement (absent when
    never achieved). purchased_levels is the set of hint levels bought during
    the episode; milestones requiring a purchase are not applicable otherwise.
    not_applicable names milestones the episode could never define (e.g. a
    diagnosis probe on a task without fault choices); they exit both
    denominators entirely.
    """
    bought = {p.level for p in purchases} if purchased_levels is None else purchased_levels
    events: list[MilestoneEvent] = []
    for spec in milestones:
        applicable = (
            (not spec.requires_hint_purchase or bool(bought))
            and spec.milestone_id not in not_applicable
        )
        turn = achieved_turns.get(spec.milestone_id, -1)
        achieved = turn >= 0
        clean = False
        if achieved:
            revealing = [p.turn for p in purchases if p.level in spec.revealed_by]
            clean = not revealing or turn < min(revealing)
        events.append(
            MilestoneEvent(
                milestone_id=spec.milestone_id,
                achieved=achieved,
                turn=turn,
                clean=clean,
                applicable=applicable,
            )
        )
    return events


def dual_scores(
    events: list[MilestoneEvent], milestones: tuple[MilestoneSpec, ...]
) -> tuple[float, float]:
    """Completion counts every achievement; unaided counts clean ones only.

    Purchase-gated milestones (requires_hint_purchase) never enter the unaided
    read-out — neither numerator nor denominator — so buyers and non-buyers
    stay comparable on the independent-solving axis.
    """
    weights = {m.milestone_id: m.weight for m in milestones}
    gated = {m.milestone_id: m.requires_hint_purchase for m in milestones}
    app = [e for e in events if e.applicable]
    total_c = sum(weights[e.milestone_id] for e in app)
    total_u = sum(weights[e.milestone_id] for e in app if not gated[e.milestone_id])
    complete = sum(weights[e.milestone_id] for e in app if e.achieved)
    unaided = sum(
        weights[e.milestone_id]
        for e in app
        if e.achieved and e.clean and not gated[e.milestone_id]
    )
    return (
        complete / total_c if total_c > 0 else 0.0,
        unaided / total_u if total_u > 0 else 0.0,
    )


def terminal_reward(s_complete: float, n_purchases: int, n_levels: int, lam: float = DEFAULT_LAMBDA) -> float:
    """Training scalar: completion with a small hint-spend tie-break."""
    if n_levels <= 0:
        return s_complete
    return s_complete - lam * (n_purchases / n_levels)


def grade(
    task: TaskSpec,
    achieved_turns: dict[str, int],
    purchases: list[PurchaseEvent],
    *,
    lam: float = DEFAULT_LAMBDA,
    meta: dict | None = None,
    purchased_levels: set[int] | None = None,
    not_applicable: frozenset[str] = frozenset(),
) -> EpisodeResult:
    """Grade one episode.

    purchased_levels overrides the set derived from purchases when the env
    needs an applicability escape hatch (e.g. a purchase that yielded zero
    information because the episode ended before any use of it).
    not_applicable excludes milestones this episode could never define.
    Grants (turn == 0) are not spend and never count toward the tie-break.
    """
    events = attribute(
        achieved_turns,
        purchases,
        task.milestones,
        purchased_levels=purchased_levels,
        not_applicable=not_applicable,
    )
    s_complete, s_unaided = dual_scores(events, task.milestones)
    n_bought = sum(1 for p in purchases if p.turn > 0)
    reward = terminal_reward(s_complete, n_bought, len(task.hints), lam)
    meta = dict(meta or {})
    applicable_total = sum(
        m.weight for e, m in zip(events, task.milestones) if e.applicable
    )
    meta.setdefault("applicable_weight_total", applicable_total)
    if applicable_total <= 0:
        meta["empty_denominator"] = True  # scores defaulted to 0.0; check task config
    return EpisodeResult(
        reward=reward,
        s_complete=s_complete,
        s_unaided=s_unaided,
        milestones=tuple(events),
        purchases=tuple(purchases),
        meta=meta,
    )
