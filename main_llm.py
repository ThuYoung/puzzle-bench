"""Multi-model pilot runner: evaluate every model in models.toml on Track B.

Fairness contract (spec sections 7-8): same bank, same budgets, same seeds for
every model; decoding at temperature 0; regret (with --protocol-a) uses each
model's OWN capability matrix — the oracle is individualized by design, so
cross-model regret comparison never punishes a weaker solver, only poor
allocation. Raw episode results land in results/ as JSONL (re-gradeable).

  uv run python main_llm.py                       # protocol B, all keyed models
  uv run python main_llm.py --only haiku-4.5      # just one
  uv run python main_llm.py --bank synth          # synthetic mutation bank (harder)
  uv run python main_llm.py --protocol-a --seeds 2  # + capability matrices & regret
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from puzzlebench.agents.llm import LLMDebugAgent, ModelSpec, load_models
from puzzlebench.config import get_settings
from puzzlebench.envs.debug import DebugEnv
from puzzlebench.logging import setup_logging
from puzzlebench.protocols import optimal_allocation, regret, run_protocol_a, run_protocol_b
from puzzlebench.tasks_debug import DEBUG_LADDER, DEBUG_TASKS

LADDER_LEVELS = tuple(h.level for h in DEBUG_LADDER)
LADDER_COSTS = {h.level: h.cost for h in DEBUG_LADDER}
ALL_LEVELS = (0,) + LADDER_LEVELS


def env_factory(target, wallet, grants):
    return DebugEnv(target, wallet=wallet, max_turns=8, preload_levels=grants)


def agent_factory(spec: ModelSpec):
    return lambda seed: LLMDebugAgent.for_model(spec)


def episode_row(r) -> dict:
    return {
        "task_id": r.meta["target"],
        "s_complete": round(r.s_complete, 4),
        "s_unaided": round(r.s_unaided, 4),
        "reward": round(r.reward, 4),
        "turns_used": r.meta["turns_used"],
        "purchases": [{"level": p.level, "turn": p.turn} for p in r.purchases],
        "probes": r.meta["probes"],
        "surgical_precision": r.meta["surgical"]["precision"],
    }


def load_bank(name: str):
    """hand: 4 handmade tasks. synth: classic seeds + hard tier, order-3 HOMs.
    novel: invented-spec seeds (out of training distribution).
    systems: Track B2 stateful systems with hand-planted non-local bugs
    (absence / alternative-semantics / state-flow) — built to defeat the
    full-file visual inspection that makes mutation bugs trivial.
    expr: Track B3 expression-language evaluators, two interacting grammar
    faults per task plus the post-solve diagnosis probe.
    multi: Track B4 multi-file packages, two faults planted in two different
    modules (fault in one file, symptom through another).
    big: Track B5 volume escalation, an 11-module toy database (~750 lines)
    with three cross-module contract faults.
    em: Track B6 emergent rule interactions — each rule stated alone, the
    joint behavior must be derived; the fault resolves it by instinct."""
    if name == "hand":
        return list(DEBUG_TASKS)
    if name == "systems":
        from puzzlebench.tasks_systems import SYSTEM_TASKS

        return list(SYSTEM_TASKS)
    if name == "expr":
        from puzzlebench.tasks_expr import EXPR_TASKS

        return list(EXPR_TASKS)
    if name == "multi":
        from puzzlebench.tasks_multifile import MULTI_TASKS

        return list(MULTI_TASKS)
    if name == "big":
        from puzzlebench.tasks_big import BIG_TASKS

        return list(BIG_TASKS)
    if name == "em":
        from puzzlebench.tasks_emergent import EMERGENT_TASKS

        return list(EMERGENT_TASKS)
    from puzzlebench.mutate import generate_tasks

    if name == "synth":
        from puzzlebench.seeds_debug import ALL_SEEDS

        return generate_tasks(ALL_SEEDS, rng_seed=1, per_seed=2, hom_per_seed=1, hom_order=3)
    from puzzlebench.seeds_novel import NOVEL_SEEDS

    return generate_tasks(NOVEL_SEEDS, rng_seed=1, per_seed=2, hom_per_seed=1, hom_order=3)


async def evaluate(
    spec: ModelSpec, *, targets, budget: int, seeds: int, protocol_a: bool, out_dir: Path
) -> dict:
    episodes = await run_protocol_b(env_factory, agent_factory(spec), targets, budget=budget, seeds=seeds)
    flat = [r for runs in episodes.values() for r in runs]
    row = {
        "label": spec.label,
        "model": spec.model,
        "bank": [t.task_id for t in targets],
        "budget": budget,
        "seeds": seeds,
        "episodes": [episode_row(r) for r in flat],
    }
    mean_c = sum(r.s_complete for r in flat) / len(flat)
    mean_u = sum(r.s_unaided for r in flat) / len(flat)
    spent = sum(LADDER_COSTS[p.level] for r in flat for p in r.purchases)
    row["means"] = {"complete": round(mean_c, 4), "unaided": round(mean_u, 4), "coins_spent": spent}

    print(f"\n== {spec.label} ({spec.model})  protocol B budget={budget} seeds={seeds}")
    for r in flat:
        bought = ", ".join(f"L{p.level}@t{p.turn}" for p in r.purchases) or "-"
        print(
            f"  {r.meta['target']:24s} complete={r.s_complete:.2f} unaided={r.s_unaided:.2f} "
            f"turns={r.meta['turns_used']} bought: {bought}"
        )
    print(f"  means: complete={mean_c:.2f} unaided={mean_u:.2f} coins={spent}")

    if protocol_a:
        matrix = await run_protocol_a(
            env_factory, agent_factory(spec), targets, ALL_LEVELS, ladder=LADDER_LEVELS, seeds=seeds
        )
        oracle = optimal_allocation(matrix, targets, ALL_LEVELS, LADDER_COSTS, budget)
        reg = regret(matrix, targets, ALL_LEVELS, LADDER_COSTS, budget, episodes)
        row["protocol_a"] = {
            "oracle": round(oracle, 4),
            "regret": round(reg, 4),
            "cells": {
                f"{t.task_id}|L{lv}": [round(r.s_complete, 4) for r in matrix[(t, lv)]]
                for t in targets for lv in ALL_LEVELS
            },
        }
        print(f"  regret={reg:+.2f} (own-matrix oracle={oracle:.2f})")

    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{spec.label}-{stamp}.json"
    path.write_text(json.dumps(row, indent=2, ensure_ascii=False))
    print(f"  raw results: {path}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="models.toml")
    parser.add_argument("--only", action="append", default=[], help="label filter (repeatable)")
    parser.add_argument("--bank", choices=["hand", "synth", "novel", "systems", "expr", "multi", "big", "em"], default="hand")
    parser.add_argument("--budget", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--protocol-a", action="store_true", help="also build capability matrices + regret")
    parser.add_argument("--out", default="results")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    specs = load_models(args.models)
    if args.only:
        specs = [s for s in specs if s.label in args.only]
    runnable, skipped = [], []
    for s in specs:
        (runnable if s.resolve_key() else skipped).append(s)
    for s in skipped:
        print(f"skip {s.label}: env var {s.key_env} is not set")
    if not runnable:
        print("no runnable models. Set a key, e.g.:")
        print("  export HINTBENCH_ANTHROPIC_API_KEY=sk-ant-...")
        return 0

    targets = load_bank(args.bank)
    print(f"bank={args.bank} ({len(targets)} tasks)")

    async def run_all() -> None:
        for spec in runnable:
            await evaluate(
                spec, targets=targets, budget=args.budget, seeds=args.seeds,
                protocol_a=args.protocol_a, out_dir=Path(args.out),
            )

    asyncio.run(run_all())
    print("\nfairness note: identical bank/budgets/seeds for every model; regret is")
    print("individualized (each model's own protocol-A matrix is its oracle).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
