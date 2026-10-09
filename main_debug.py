"""Track B debug-economy demo: protocols A/B over handcrafted and mutant banks.

Mirrors main.py (wordle): protocol A builds the SR(b) curve, protocol B runs
the three archetypes at budget tiers, and the triad (completion / unaided /
regret) should separate a careful non-buyer, an economical buyer, and a
ladder-climbing panicker. The synthetic bank comes from the mutation pipeline
(mutate.py), subsampled to keep the demo quick.
"""

from __future__ import annotations

import asyncio

from hintbench import metrics
from hintbench.agents.debug_scripted import ScriptedDebugAgent
from hintbench.config import get_settings
from hintbench.envs.debug import DebugEnv
from hintbench.logging import setup_logging
from hintbench.mutate import generate_tasks
from hintbench.protocols import optimal_allocation, regret, run_protocol_a, run_protocol_b
from hintbench.tasks_debug import DEBUG_LADDER, DEBUG_TASKS, DebugTask

LADDER_LEVELS = tuple(h.level for h in DEBUG_LADDER)
LADDER_COSTS = {h.level: h.cost for h in DEBUG_LADDER}
ALL_LEVELS = (0,) + LADDER_LEVELS
BUDGET_TIERS = (0, 5, 9)  # none / up-to-L4 minus change / full ladder


def make_env(max_turns: int):
    return lambda target, wallet, grants: DebugEnv(
        target, wallet=wallet, max_turns=max_turns, preload_levels=grants
    )


def make_agent(policy: str, **kw):
    return lambda seed: ScriptedDebugAgent(seed, hint_policy=policy, **kw)


async def run_bank(label: str, targets: list[DebugTask], *, seeds: int, max_turns: int = 8) -> None:
    env_factory = make_env(max_turns)
    print(f"=== {label}: {len(targets)} tasks, {seeds} seeds/episode, budgets {BUDGET_TIERS}\n")

    matrix = await run_protocol_a(
        env_factory, make_agent("smart", skill=0.3), targets, ALL_LEVELS,
        ladder=LADDER_LEVELS, seeds=seeds,
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
        ("never", dict(skill=0.95)),
        ("smart", dict(skill=0.35)),
        ("panic", dict(skill=0.1)),
    ]:
        own_matrix = await run_protocol_a(
            env_factory, make_agent(policy, **kw), targets, ALL_LEVELS,
            ladder=LADDER_LEVELS, seeds=seeds,
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
    print()


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    await run_bank("handcrafted bank", list(DEBUG_TASKS), seeds=settings.default_seeds)

    mutants = generate_tasks(per_seed=2, hom_per_seed=1)
    subsample = mutants[::2]  # deterministic subsample for demo speed
    await run_bank("synthetic bank (subsample)", subsample, seeds=2)

    print("reading guide:")
    print("  - SR(level) should climb with the ladder and pin at 1.0 once the sketch is granted")
    print("  - panic at B=9 buys the whole ladder: complete diverges from unaided (sketch taint)")
    print("  - never: complete == unaided by construction")
    print("  - smart: economical L1/L2 buys; hint_consistent keeps it honest on region hints")
    print("  - both banks exist to check the machinery, not to discriminate real models")


if __name__ == "__main__":
    asyncio.run(main())
