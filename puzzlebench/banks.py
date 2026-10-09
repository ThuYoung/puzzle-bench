"""Bank registry: one loader shared by the model runner and the human-site
renderer, so both always see the same task lists.

hand: 4 handmade tasks. synth: classic seeds + hard tier, order-3 HOMs.
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
joint behavior must be derived; the fault resolves it by instinct.
"""

from __future__ import annotations

from puzzlebench.tasks_debug import DEBUG_TASKS

BANK_NAMES = ("hand", "systems", "expr", "multi", "big", "em", "synth", "novel")


def load_bank(name: str):
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
    if name == "novel":
        from puzzlebench.seeds_novel import NOVEL_SEEDS

        return generate_tasks(NOVEL_SEEDS, rng_seed=1, per_seed=2, hom_per_seed=1, hom_order=3)
    raise ValueError(f"unknown bank: {name} (choices: {', '.join(BANK_NAMES)})")
