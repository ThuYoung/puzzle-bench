"""Evaluation protocols and the individualized regret oracle.

Protocol A (controlled): each puzzle at each forced hint level, fresh context.
Its output matrix is both the solve-rate-vs-budget curve data and the input to
the regret oracle. Protocol B (free play): agents purchase within a budget.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from hintbench.schema import EpisodeResult

EnvFactory = Callable[[str, int, tuple[int, ...]], object]
AgentFactory = Callable[[int], object]


async def run_protocol_a(
    env_factory: Callable[..., object],
    agent_factory: Callable[[int], object],
    targets: list[str],
    levels: tuple[int, ...],
    *,
    ladder: tuple[int, ...],
    seeds: int,
    concurrency: int = 4,
) -> dict[tuple[str, int], list[EpisodeResult]]:
    """matrix[(target, level)] = per-seed results with ladder hints <= level granted.

    Cells carry a zero wallet: a controlled cell must measure capability at an
    exact forced level, so free purchases inside it would contaminate the
    matrix (and everything derived from it: SR curve, regret oracle).

    Concurrency is bounded: targets x levels x seeds cells fire API requests,
    and an unbounded gather trips provider rate limits.
    """
    gate = asyncio.Semaphore(concurrency)

    async def one(target: str, level: int, seed: int) -> tuple[tuple[str, int], EpisodeResult]:
        from hintbench.economy import Wallet

        grants = tuple(lv for lv in ladder if lv <= level)
        env = env_factory(target, Wallet(0), grants)
        agent = agent_factory(seed)
        async with gate:
            return (target, level), await agent.play(env)

    jobs = [one(t, b, s) for t in targets for b in levels for s in range(seeds)]
    matrix: dict[tuple[str, int], list[EpisodeResult]] = {}
    for key, result in await asyncio.gather(*jobs):
        matrix.setdefault(key, []).append(result)
    return matrix


async def run_protocol_b(
    env_factory: Callable[..., object],
    agent_factory: Callable[[int], object],
    targets: list[str],
    *,
    budget: int,
    seeds: int,
) -> dict[str, list[EpisodeResult]]:
    """Free play with ONE wallet per run, recharged per seed.

    Episodes within a run play sequentially so cross-puzzle allocation is a
    real decision; different seeds run concurrently.
    """
    from hintbench.economy import Wallet

    async def one_seed(seed: int) -> list[tuple[str, EpisodeResult]]:
        wallet = Wallet(budget)
        played = []
        for target in targets:
            env = env_factory(target, wallet, ())
            agent = agent_factory(seed * 1000 + len(played))
            played.append((target, await agent.play(env)))
        return played

    out: dict[str, list[EpisodeResult]] = {t: [] for t in targets}
    for played in await asyncio.gather(*[one_seed(s) for s in range(seeds)]):
        for target, result in played:
            out[target].append(result)
    return out


def level_costs(ladder_costs: dict[int, int], level: int) -> int:
    """Coins needed to own all hints 1..level on the ladder."""
    return sum(c for lv, c in ladder_costs.items() if lv <= level)


def optimal_allocation(
    matrix: dict[tuple[str, int], list[EpisodeResult]],
    targets: list[str],
    levels: tuple[int, ...],
    ladder_costs: dict[int, int],
    budget: int,
    *,
    score: str = "s_complete",
) -> float:
    """Best mean total score achievable with `budget` coins across puzzles.

    Computed on the model's OWN protocol-A matrix, so the oracle prices each
    puzzle with this model's measured capability, not an absolute standard.
    DP over puzzles (budgets and puzzle counts are small by design).
    """
    levels_sorted = tuple(sorted(levels))
    cost_of = {b: level_costs(ladder_costs, b) for b in levels_sorted}
    value: dict[tuple[str, int], float] = {}
    for t in targets:
        for b in levels_sorted:
            runs = matrix.get((t, b), [])
            if runs:
                value[(t, b)] = sum(getattr(r, score) for r in runs) / len(runs)
            else:
                # missing cell (e.g. adaptive protocol-A stop): SR is weakly
                # monotone in owned hints, so floor it with the best measured
                # lower level instead of treating it as zero capability
                value[(t, b)] = next(
                    (value[(t, lb)] for lb in reversed(levels_sorted[: levels_sorted.index(b)])),
                    0.0,
                )

    dp = [[0.0] * (budget + 1) for _ in range(len(targets) + 1)]
    for i, t in enumerate(targets, start=1):
        for c in range(budget + 1):
            best = dp[i - 1][c]
            for b in levels_sorted:
                cost = cost_of[b]
                if cost <= c:
                    best = max(best, dp[i - 1][c - cost] + value[(t, b)])
            dp[i][c] = best
    return dp[len(targets)][budget]


def regret(
    matrix: dict[tuple[str, int], list[EpisodeResult]],
    targets: list[str],
    levels: tuple[int, ...],
    ladder_costs: dict[int, int],
    budget: int,
    actual: dict[str, list[EpisodeResult]],
    *,
    score: str = "s_complete",
) -> float:
    """oracle (own-matrix optimal allocation) minus free-play actual."""
    oracle = optimal_allocation(matrix, targets, levels, ladder_costs, budget, score=score)
    actual_total = sum(
        sum(getattr(r, score) for r in runs) / len(runs) for runs in actual.values() if runs
    )
    return oracle - actual_total
