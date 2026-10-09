"""Aggregate metrics over episode results.

Single source of truth for headline numbers so main.py, tests, and the spec
all read the same definitions:
- SR(b, theta): solve rate at forced level b. Headline theta is the "solved"
  milestone; theta as a float reads s_complete >= theta instead.
- AUC over the SR(b) curve with a bootstrap CI.
- hint_utilization E_k: mean s_complete gain from owning level k vs the
  previous ladder level.
"""

from __future__ import annotations

import math
import random

from hintbench.schema import EpisodeResult

Matrix = dict[tuple[str, int], list[EpisodeResult]]


def _cell_runs(matrix: Matrix, targets: list[str], level: int) -> list[EpisodeResult]:
    return [r for t in targets for r in matrix.get((t, level), [])]


def solve_rate(matrix: Matrix, targets: list[str], level: int, theta: str | float = "solved") -> float:
    runs = _cell_runs(matrix, targets, level)
    if not runs:
        return 0.0
    if theta == "solved":
        hit = lambda r: any(e.milestone_id == "solved" and e.achieved for e in r.milestones)
    else:
        hit = lambda r: r.s_complete >= float(theta)
    return sum(1 for r in runs if hit(r)) / len(runs)


def binomial_se(p: float, n: int) -> float:
    return math.sqrt(p * (1 - p) / n) if n > 0 else 0.0


def sr_curve(
    matrix: Matrix, targets: list[str], levels: tuple[int, ...], theta: str | float = "solved"
) -> dict[int, tuple[float, float]]:
    """level -> (SR, binomial SE). Levels must include 0."""
    return {
        b: (sr := solve_rate(matrix, targets, b, theta),
            binomial_se(sr, len(_cell_runs(matrix, targets, b))))
        for b in levels
    }


def auc(curve: dict[int, tuple[float, float]], levels: tuple[int, ...]) -> float:
    """Trapezoid area under SR(b), normalized by the level span."""
    ordered = [curve[b][0] for b in sorted(levels)]
    area = sum((ordered[i] + ordered[i + 1]) / 2 for i in range(len(ordered) - 1))
    return area / (len(ordered) - 1) if len(ordered) > 1 else 0.0


def auc_bootstrap_ci(
    matrix: Matrix,
    targets: list[str],
    levels: tuple[int, ...],
    *,
    n_boot: int = 500,
    seed: int = 0,
    theta: str | float = "solved",
) -> tuple[float, float]:
    """CI by resampling per-cell runs with replacement, then re-reading the curve."""
    rng = random.Random(seed)
    cells = [(t, b) for t in targets for b in levels]
    pools = {c: matrix.get(c, []) for c in cells}
    estimates = []
    for _ in range(n_boot):
        sample: Matrix = {
            c: [rng.choice(pool) for _ in pool] for c, pool in pools.items() if pool
        }
        curve = {b: (solve_rate(sample, targets, b, theta), 0.0) for b in levels}
        estimates.append(auc(curve, levels))
    estimates.sort()
    lo = estimates[int(0.025 * n_boot)]
    hi = estimates[min(int(0.975 * n_boot), n_boot - 1)]
    return lo, hi


def hint_utilization(matrix: Matrix, targets: list[str], ladder: tuple[int, ...]) -> dict[int, float]:
    """E_k = mean s_complete at level k minus at the previous ladder level."""
    out: dict[int, float] = {}
    prev_level = 0
    for level in sorted(ladder):
        prev = _cell_runs(matrix, targets, prev_level)
        cur = _cell_runs(matrix, targets, level)
        if prev and cur:
            mean = lambda runs: sum(r.s_complete for r in runs) / len(runs)
            out[level] = mean(cur) - mean(prev)
        prev_level = level
    return out
