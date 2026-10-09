"""Self-check entry point: wordle pipeline end-to-end with scripted agents.

Runs protocol A (forced hint levels -> capability matrix + solve-rate curve)
and protocol B (free play at several coin budgets) for three archetype agents,
then prints the triad (completion / unaided / regret) which should separate
them. All aggregate numbers come from puzzlebench.metrics.
"""

from __future__ import annotations

import asyncio

from puzzlebench import metrics
from puzzlebench.agents.scripted import ScriptedWordleAgent
from puzzlebench.config import get_settings
from puzzlebench.envs.wordle import ANSWERS, HINT_LADDER, WordleEnv
from puzzlebench.logging import setup_logging
from puzzlebench.protocols import optimal_allocation, regret, run_protocol_a, run_protocol_b

LADDER_LEVELS = tuple(h.level for h in HINT_LADDER)
LADDER_COSTS = {h.level: h.cost for h in HINT_LADDER}
ALL_LEVELS = (0,) + LADDER_LEVELS
BUDGET_TIERS = (0, 3, 7)  # spec: no-coins / partial / full-ladder coverage


def make_env(max_turns: int):
    return lambda target, wallet, grants: WordleEnv(
        target, wallet=wallet, max_turns=max_turns, preload_levels=grants
    )


def make_agent(policy: str, **kw):
    return lambda seed: ScriptedWordleAgent(seed, hint_policy=policy, **kw)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    env_factory = make_env(settings.wordle_max_turns)
    targets = [ANSWERS[(i * 37) % len(ANSWERS)] for i in range(4)]
    seeds = settings.default_seeds

    print(f"targets: {targets} | seeds/episode: {seeds} | budgets: {BUDGET_TIERS}\n")

    matrix = await run_protocol_a(
        env_factory,
        make_agent("smart", skill=0.3, consistency=0.8),
        targets,
        ALL_LEVELS,
        ladder=LADDER_LEVELS,
        seeds=seeds,
    )
    curve = metrics.sr_curve(matrix, targets, ALL_LEVELS)
    area = metrics.auc(curve, ALL_LEVELS)
    lo, hi = metrics.auc_bootstrap_ci(matrix, targets, ALL_LEVELS, seed=0)
    print("protocol A — SR(b) curve (theta = solved milestone):")
    for level in ALL_LEVELS:
        sr, se = curve[level]
        runs = [r for t in targets for r in matrix[(t, level)]]
        mean_c = sum(r.s_complete for r in runs) / len(runs)
        print(f"  level {level}: SR={sr:.2f} (se {se:.2f})  mean s_complete={mean_c:.2f}")
    print(f"  AUC={area:.2f}  bootstrap 95% CI [{lo:.2f}, {hi:.2f}]")
    util = metrics.hint_utilization(matrix, targets, LADDER_LEVELS)
    print("  utilization E_k: " + ", ".join(f"L{k} {v:+.2f}" for k, v in util.items()))

    print("\nprotocol B — archetype triads (regret uses each policy's own matrix):")
    for policy, kw in [
        ("never", dict(skill=0.9, consistency=1.0)),
        ("smart", dict(skill=0.7, consistency=0.9)),
        ("panic", dict(skill=0.4, consistency=0.6)),
    ]:
        own_matrix = await run_protocol_a(
            env_factory,
            make_agent(policy, **kw),
            targets,
            ALL_LEVELS,
            ladder=LADDER_LEVELS,
            seeds=seeds,
        )
        for tier in BUDGET_TIERS:
            oracle = optimal_allocation(own_matrix, targets, ALL_LEVELS, LADDER_COSTS, tier)
            episodes = await run_protocol_b(
                env_factory, make_agent(policy, **kw), targets, budget=tier, seeds=seeds
            )
            flat = [r for runs in episodes.values() for r in runs]
            mean_c = sum(r.s_complete for r in flat) / len(flat)
            mean_u = sum(r.s_unaided for r in flat) / len(flat)
            reg = regret(own_matrix, targets, ALL_LEVELS, LADDER_COSTS, tier, episodes)
            n_hints = sum(len(r.purchases) for r in flat) / len(flat)
            print(
                f"  {policy:6s} B={tier}: complete={mean_c:.2f} unaided={mean_u:.2f} "
                f"regret={reg:+.2f} oracle={oracle:.2f} hints/episode={n_hints:.1f}"
            )

    print("\nself-check reading guide:")
    print("  - SR(level) should be nondecreasing and reach ~1.0 at the answer hint")
    print("  - panic: buys the ladder when stuck; completion vs unaided diverges when it reaches L5")
    print("  - never: complete == unaided by construction")
    print("  - regret can go slightly negative: adaptive mid-game purchases (buy only")
    print("    when actually stuck) can beat the oracle's blind pre-committed allocation")
    print("  - B=0: nobody can buy; triads for all policies should look alike")
    print("  - wordle is easy for strong consistent players, so archetype separation")
    print("    here is a machinery check, not a discrimination result")


if __name__ == "__main__":
    asyncio.run(main())
