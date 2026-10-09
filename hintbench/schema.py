"""Domain model for the hint-economy harness.

All grading-relevant facts are dataclasses (see project conventions): tasks,
milestones, and the events recorded during an episode. The grader consumes only
these structures plus the spoil mapping carried by each milestone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HintSpec:
    """One purchasable information good on a task's hint ladder."""

    level: int  # 1..K, purchase order on the ladder
    kind: str  # env-specific payload type, e.g. "first_letter"
    cost: int = 1


@dataclass(frozen=True)
class MilestoneSpec:
    """A scorable checkpoint derived from the hint ladder.

    revealed_by is the spoil mapping: hint levels whose text directly hands the
    milestone to the solver. Achievements after such a purchase are not counted
    toward the unaided score.
    """

    milestone_id: str
    weight: float
    revealed_by: frozenset[int] = frozenset()
    # applicability lets an episode exclude a milestone from the denominator
    # (e.g. hint-consistency is undefined when no hint was purchased)
    requires_hint_purchase: bool = False


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    budget: int  # hint coins available in free play; protocol A ignores this
    hints: tuple[HintSpec, ...]
    milestones: tuple[MilestoneSpec, ...]

    @property
    def max_level(self) -> int:
        return max((h.level for h in self.hints), default=0)


@dataclass(frozen=True)
class PurchaseEvent:
    level: int
    turn: int  # logical clock stamped by the env, never by the agent


@dataclass(frozen=True)
class MilestoneEvent:
    milestone_id: str
    achieved: bool
    turn: int  # turn of first achievement; -1 when never achieved
    clean: bool  # achieved before every revealing hint purchase
    applicable: bool = True


@dataclass(frozen=True)
class EpisodeResult:
    reward: float  # terminal scalar for training
    s_complete: float
    s_unaided: float
    milestones: tuple[MilestoneEvent, ...]
    purchases: tuple[PurchaseEvent, ...]
    meta: dict[str, Any] = field(default_factory=dict)
