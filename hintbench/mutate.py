"""SWE-smith-style mutation pipeline for Track B (spec section 10).

Operators locate edit sites with AST but splice SOURCE TEXT (seed formatting
survives untouched). The between-operands trick replaces the exact source span
between two subexpressions, so operator symbols are found structurally, never
by text search.

Execution filter: every candidate runs the seed's full suite in a SUBPROCESS
with a timeout — a mutant may loop forever (condition inversion), and the
harness process must never hang on it. Keep a mutant iff it fails >= 1 test
(F2P material) and keeps >= 1 green (regression-guard material). Equivalent
mutants (all green) are discarded as tasks but kept as plausible wrong
variants for scripted agents.

CLI: uv run python -m hintbench.mutate --per-seed 2 --hom-per-seed 1
"""

from __future__ import annotations

import argparse
import ast
import difflib
import random
from dataclasses import dataclass

from hintbench.seeds_debug import SEEDS, Seed
from hintbench.tasks_debug import DebugTask


@dataclass(frozen=True)
class Mutation:
    buggy_source: str
    region: tuple[int, int]  # 1-based inclusive lines in buggy_source
    sketch: str
    operator: str


# -- source splicing ----------------------------------------------------------


def _apply_edits(source: str, edits: list[tuple[int, int, int, int, str]]) -> str:
    """Apply (start_line, start_col, end_line, end_col, text) splices.

    Lines are 1-based, cols 0-based (AST convention). Edits must be disjoint;
    they are applied in reverse position order so coordinates stay valid.
    """
    lines = source.splitlines(keepends=True)
    for sl, sc, el, ec, text in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        replacement = lines[sl - 1][:sc] + text + lines[el - 1][ec:]
        lines[sl - 1 : el] = [replacement]
    return "".join(lines)


def _span(node: ast.AST) -> tuple[int, int, int, int]:
    return (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)  # type: ignore[attr-defined]


def _between(left: ast.AST, right: ast.AST) -> tuple[int, int, int, int]:
    """Source span strictly between two sibling expressions (the operator)."""
    return (left.end_lineno, left.end_col_offset, right.lineno, right.col_offset)  # type: ignore[attr-defined]


def changed_region(old: str, new: str) -> tuple[int, int]:
    """Smallest line span in NEW covering every changed line (buggy-side)."""
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines())
    lines: set[int] = set()
    for tag, _, _, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            lines.update(range(j1 + 1, j2 + 1))
        else:  # insert/delete: anchor at the position in new
            lines.add(j1 + 1)
    return (min(lines), max(lines)) if lines else (1, 1)


def _mutate(source: str, edits: list[tuple[int, int, int, int, str]], sketch: str, operator: str) -> Mutation:
    buggy = _apply_edits(source, edits)
    return Mutation(buggy_source=buggy, region=changed_region(source, buggy), sketch=sketch, operator=operator)


# -- operators -----------------------------------------------------------------

_CMP_FLIP = {
    ast.LtE: ("<=", "<"), ast.Lt: ("<", "<="),
    ast.GtE: (">=", ">"), ast.Gt: (">", ">="),
    ast.Eq: ("==", "!="), ast.NotEq: ("!=", "=="),
}
_BINOP_SWAP = {ast.Add: ("+", "-"), ast.Sub: ("-", "+"), ast.Mult: ("*", "+"), ast.FloorDiv: ("//", "/")}
_BOOL_SWAP = {ast.And: ("and", "or"), ast.Or: ("or", "and")}


def op_cmp_flip(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        for i, op in enumerate(node.ops):
            if type(op) not in _CMP_FLIP:
                continue
            old, new = _CMP_FLIP[type(op)]
            left = node.left if i == 0 else node.comparators[i - 1]
            out.append(_mutate(source, [(*_between(left, node.comparators[i]), f" {new} ")],
                               f"A comparison changed ('{old}' to '{new}').", "cmp_flip"))
    return out


def op_arith_swap(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
            old, new = _BINOP_SWAP[type(node.op)]
            out.append(_mutate(source, [(*_between(node.left, node.right), f" {new} ")],
                               f"An arithmetic operator changed ('{old}' to '{new}').", "arith_swap"))
        elif isinstance(node, ast.AugAssign) and type(node.op) in _BINOP_SWAP:
            old, new = _BINOP_SWAP[type(node.op)]
            out.append(_mutate(source, [(*_between(node.target, node.value), f" {new}= ")],
                               f"An in-place operator changed ('{old}=' to '{new}=').", "arith_swap"))
    return out


def op_bool_swap(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_SWAP:
            old, new = _BOOL_SWAP[type(node.op)]
            for i in range(len(node.values) - 1):
                out.append(_mutate(source, [(*_between(node.values[i], node.values[i + 1]), f" {new} ")],
                                   f"A boolean connective changed ('{old}' to '{new}').", "bool_swap"))
    return out


def op_const_bump(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            for new_val in (node.value + 1, node.value - 1):
                out.append(_mutate(source, [(*_span(node), str(new_val))],
                                   f"A constant changed ({node.value} to {new_val}).", "const_bump"))
    return out


def op_negate_condition(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.If, ast.While)):
            seg = ast.get_source_segment(source, node.test)
            out.append(_mutate(source, [(*_span(node.test), f"not ({seg})")],
                               "A branch condition is inverted.", "negate_condition"))
    return out


def _op_negate_condition_if_only(source: str) -> list[Mutation]:
    """If-only variant for HOM composition: inverting a WHILE test almost
    always loops forever, which the filter must reject at full timeout cost."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.If):
            seg = ast.get_source_segment(source, node.test)
            out.append(_mutate(source, [(*_span(node.test), f"not ({seg})")],
                               "A branch condition is inverted.", "negate_condition"))
    return out


def op_return_swap(source: str) -> list[Mutation]:
    returns = [
        n for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Return) and n.value is not None
    ]
    out = []
    segs = [ast.get_source_segment(source, n.value) for n in returns]
    for i in range(len(returns)):
        for j in range(i + 1, len(returns)):
            if segs[i] == segs[j]:
                continue
            edits = [(*_span(returns[i].value), segs[j]), (*_span(returns[j].value), segs[i])]
            out.append(_mutate(source, edits,
                               "Two branches return each other's values.", "return_swap"))
    return out


def op_range_bound(source: str) -> list[Mutation]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "range"):
            continue
        if not node.args:
            continue
        last = node.args[-1]
        seg = ast.get_source_segment(source, last)
        if isinstance(last, ast.BinOp) and isinstance(last.op, (ast.Add, ast.Sub)):
            # range(a, b + 1) -> range(a, b): drop the offset entirely
            inner = ast.get_source_segment(source, last.left)
            out.append(_mutate(source, [(*_span(last), inner)],
                               "The loop bound lost its offset.", "range_bound"))
        else:
            out.append(_mutate(source, [(*_span(last), f"({seg} - 1)")],
                               "The loop bound is off by one.", "range_bound"))
    return out


OPERATORS = (
    op_cmp_flip,
    op_arith_swap,
    op_bool_swap,
    op_const_bump,
    op_negate_condition,
    op_return_swap,
    op_range_bound,
)

# HOM composition pool: while-negation replaced by its if-only variant.
HOM_OPERATORS = tuple(_op_negate_condition_if_only if op is op_negate_condition else op for op in OPERATORS)

# HOM candidates are oversampled this many times per kept slot: most random
# compositions die in the filter (hangs, net-equivalents, kill-everything).
HOM_OVERSAMPLE = 6


# -- execution filter ----------------------------------------------------------

# Every candidate runs the seed's suite in the sandbox worker (process
# isolation + per-test timeout). Keep a mutant iff it fails >= 1 test (F2P
# material) and keeps >= 1 green (regression-guard material); hangs and
# crashes are rejected outright.


def filter_batch(
    candidates: list[str], tests: tuple[tuple[str, str], ...], *, timeout: float = 0.5
) -> list[dict[str, bool] | None]:
    """Per-candidate verdicts; None = rejected (hang/crash/sandbox failure)."""
    from hintbench.sandbox import SandboxRunner

    runner = SandboxRunner(timeout=timeout)  # dedicated: never perturbs the shared default
    try:
        verdicts: list[dict[str, bool] | None] = []
        for source in candidates:
            outcomes = runner.run_tests(source, tests)
            if any(o["kind"] in ("hang", "sandbox") for o in outcomes.values()):
                verdicts.append(None)
            else:
                verdicts.append({name: bool(o["passed"]) for name, o in outcomes.items()})
        return verdicts
    finally:
        runner.close()


def filter_outcomes(
    source: str, tests: tuple[tuple[str, str], ...], *, timeout: float = 0.5
) -> dict[str, bool] | None:
    """test name -> passed, or None when the mutant is rejected (hang/crash)."""
    return filter_batch([source], tests, timeout=timeout)[0]


# -- generation ----------------------------------------------------------------


def _none_variant(source: str) -> str:
    """Always-wrong fallback attempt: same signature, trivial body."""
    first_line = source.splitlines()[0]
    return f"{first_line}\n    return None\n"


def apply_hom(source: str, rng: random.Random, order: int = 2) -> Mutation | None:
    """Higher-order mutation: `order` operator hits composed sequentially.

    A later hit may revert an earlier one; the execution filter then bins the
    mutant as equivalent, so only genuinely multi-fault tasks are kept.
    """
    if order < 2:
        raise ValueError(f"HOM order must be >= 2, got {order}")
    current = source
    sketches: list[str] = []
    operators: list[str] = []
    for _ in range(order):
        hits = [m for op in HOM_OPERATORS for m in op(current)]
        if not hits:
            return None
        m = rng.choice(hits)
        current = m.buggy_source
        sketches.append(m.sketch)
        operators.append(m.operator)
    return Mutation(
        buggy_source=current,
        region=changed_region(source, current),
        sketch=f"{order} changes. " + " ".join(sketches),
        operator="hom:" + "+".join(operators),
    )


def generate_tasks(
    seeds: tuple[Seed, ...] = SEEDS,
    *,
    rng_seed: int = 0,
    per_seed: int = 2,
    hom_per_seed: int = 0,
    hom_order: int = 2,
    timeout: float = 0.5,
) -> list[DebugTask]:
    rng = random.Random(rng_seed)
    tasks: list[DebugTask] = []
    for seed in seeds:
        candidates = [m for op in OPERATORS for m in op(seed.source)]
        # dedupe identical mutant sources, then shuffle deterministically
        candidates = list({m.buggy_source: m for m in candidates}.values())
        rng.shuffle(candidates)
        if hom_per_seed:
            attempts = [
                m
                for m in (apply_hom(seed.source, rng, order=hom_order) for _ in range(hom_per_seed * HOM_OVERSAMPLE))
                if m
            ]
            candidates += list({m.buggy_source: m for m in attempts}.values())
        # one worker process per seed: batch-filter every candidate
        verdicts = filter_batch([m.buggy_source for m in candidates], seed.tests, timeout=timeout)
        kept: list[tuple[Mutation, tuple[str, ...], tuple[str, ...]]] = []
        single_kept = 0
        hom_kept = 0
        equivalents: list[Mutation] = []
        for m, res in zip(candidates, verdicts):
            is_hom = m.operator.startswith("hom:")
            if (is_hom and hom_kept >= hom_per_seed) or (not is_hom and single_kept >= per_seed):
                continue
            if res is None:
                continue  # hang or crash: rejected
            f2p = tuple(n for n, ok in res.items() if not ok)
            p2p = tuple(n for n, ok in res.items() if ok)
            if not f2p:
                equivalents.append(m)  # no behavioral change: not a bug, but a
                continue               # great "looks fixed, changes nothing" variant
            if not p2p:
                continue  # too blatant: leaves no regression-guard material
            kept.append((m, f2p, p2p))
            if is_hom:
                hom_kept += 1
            else:
                single_kept += 1
        test_map = dict(seed.tests)
        for k, (m, f2p, p2p) in enumerate(kept):
            variants = [e.buggy_source for e in equivalents[:2]]
            variants += [s.buggy_source for s, _, _ in kept if s is not m][:2]
            variants.append(_none_variant(seed.source))
            tasks.append(
                DebugTask(
                    task_id=f"dbg_mut_{seed.name}_{m.operator.replace(':', '_').replace('+', '_')}_{k}",
                    title=f"{seed.name}: synthetic mutant ({m.operator})",
                    buggy_source=m.buggy_source,
                    fixed_source=seed.source,
                    wrong_variants=tuple(variants[:4]),
                    public_tests=((f2p[0], test_map[f2p[0]]),),  # guaranteed red on the buggy source
                    hidden_tests=seed.tests,
                    f2p=f2p,
                    p2p=p2p,
                    fault_region=m.region,
                    fix_sketch=m.sketch,
                )
            )
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Track B mutant tasks.")
    parser.add_argument("--rng-seed", type=int, default=0)
    parser.add_argument("--per-seed", type=int, default=2)
    parser.add_argument("--hom-per-seed", type=int, default=0)
    parser.add_argument("--hom-order", type=int, default=2)
    args = parser.parse_args()
    tasks = generate_tasks(
        rng_seed=args.rng_seed, per_seed=args.per_seed,
        hom_per_seed=args.hom_per_seed, hom_order=args.hom_order,
    )
    for t in tasks:
        a, b = t.fault_region
        print(f"{t.task_id}: lines {a}-{b}, f2p={len(t.f2p)} p2p={len(t.p2p)}\n  sketch: {t.fix_sketch}")
    print(f"\n{len(tasks)} tasks")


if __name__ == "__main__":
    main()
