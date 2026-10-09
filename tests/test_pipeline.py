"""End-to-end pipeline self-check with scripted archetype agents.

The assertions encode the benchmark's reason to exist: the triad must separate
"buys a lot and converts" from "never buys" from "panics and buys the answer".
Scripted RNG is seeded, so results are deterministic.
"""

from puzzlebench.agents.scripted import ScriptedWordleAgent
from puzzlebench.envs.wordle import ANSWERS, HINT_LADDER, WordleEnv
from puzzlebench.protocols import optimal_allocation, regret, run_protocol_a, run_protocol_b

LADDER = tuple(h.level for h in HINT_LADDER)
COSTS = {h.level: h.cost for h in HINT_LADDER}
LEVELS = (0,) + LADDER
TARGETS = [ANSWERS[3], ANSWERS[100]]
BUDGET = 7
SEEDS = 2


def env_factory(target, wallet, grants):
    return WordleEnv(target, wallet=wallet, max_turns=8, preload_levels=grants)


def agent_factory(policy, **kw):
    return lambda seed: ScriptedWordleAgent(seed, hint_policy=policy, **kw)


async def protocol_a_for(policy, **kw):
    return await run_protocol_a(
        env_factory, agent_factory(policy, **kw), TARGETS, LEVELS, ladder=LADDER, seeds=SEEDS
    )


async def test_solve_rate_monotone_in_forced_level():
    matrix = await protocol_a_for("smart", skill=0.8, consistency=1.0)

    def sr(level):
        runs = [r for t in TARGETS for r in matrix[(t, level)]]
        return sum(r.s_complete >= 0.999 for r in runs) / len(runs)

    assert sr(0) <= sr(2) <= sr(5)
    assert sr(5) == 1.0  # the answer hint must always unlock full completion


async def test_archetype_economy_and_attribution():
    out = {}
    for policy, kw in [
        ("never", dict(skill=0.9, consistency=1.0)),
        ("smart", dict(skill=0.45, consistency=0.95)),
        ("panic", dict(skill=0.35, consistency=0.5)),
    ]:
        matrix = await protocol_a_for(policy, **kw)
        oracle = optimal_allocation(matrix, TARGETS, LEVELS, COSTS, BUDGET)
        episodes = await run_protocol_b(
            env_factory, agent_factory(policy, **kw), TARGETS, budget=BUDGET, seeds=SEEDS
        )
        flat = [r for runs in episodes.values() for r in runs]
        out[policy] = dict(
            complete=sum(r.s_complete for r in flat) / len(flat),
            unaided=sum(r.s_unaided for r in flat) / len(flat),
            regret=regret(matrix, TARGETS, LEVELS, COSTS, BUDGET, episodes),
            oracle=oracle,
            spent=[sum(COSTS[p.level] for p in r.purchases) for r in flat],
        )

    never, smart, panic = out["never"], out["smart"], out["panic"]

    # never-buyer: everything achieved is clean by construction, and it spends nothing
    assert never["complete"] == never["unaided"]
    assert all(s == 0 for s in never["spent"])
    # panic-buyer: completion bought with the answer hint must show as tainted
    assert panic["unaided"] < panic["complete"]
    # shared wallet: no run may overspend, and the panicker's ladder-climb to
    # the answer (cost 7) must starve the rest of its run
    for out_ in out.values():
        per_run = out_["spent"]
        assert all(s <= BUDGET for s in per_run)
    assert max(panic["spent"]) == 7 and min(panic["spent"]) == 0
    # regret is finite for every archetype (cross-archetype comparison is a
    # pilot question with real models, not a scripted-agent property)
    for out_ in out.values():
        assert abs(out_["regret"]) <= len(TARGETS) + 1


async def test_hint_consistency_milestone_for_smart_buyer():
    episodes = await run_protocol_b(
        env_factory,
        agent_factory("smart", skill=0.45, consistency=1.0),
        TARGETS,
        budget=BUDGET,
        seeds=SEEDS,
    )
    flat = [r for runs in episodes.values() for r in runs]
    bought = [r for r in flat if r.purchases]
    assert bought, "weakened smart agent should need hints on at least one target"
    for r in bought:
        hc = next(e for e in r.milestones if e.milestone_id == "hint_consistent")
        # consistency=1.0 keeps every post-hint guess hint-compatible, so the
        # milestone is achieved deterministically (violation path has its own test)
        assert hc.applicable and hc.achieved


async def test_protocol_a_cells_are_purchase_free():
    # a controlled cell must contain grants only: any turn>0 purchase means the
    # agent shopped inside the capability matrix and contaminated it
    matrix = await protocol_a_for("smart", skill=0.45, consistency=0.95)
    for (target, level), runs in matrix.items():
        expected = {lv for lv in LADDER if lv <= level}
        for r in runs:
            assert all(p.turn == 0 for p in r.purchases), f"free purchase in cell {(target, level)}"
            assert {p.level for p in r.purchases} == expected


async def test_protocol_a_bounds_concurrency():
    # unbounded cells would fire targets x levels requests at once and trip
    # provider rate limits; the semaphore must cap simultaneous plays
    import asyncio

    current = 0
    peak = 0

    class CountingAgent:
        def __init__(self, seed):
            pass

        async def play(self, env):
            nonlocal current, peak
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.02)
            current -= 1
            return await env.close()

    def env_factory(target, wallet, grants):
        return WordleEnv(target, wallet=wallet, preload_levels=grants, max_turns=1)

    await run_protocol_a(
        env_factory, CountingAgent, list(ANSWERS)[:2], (0, 1, 2, 3), ladder=LADDER, seeds=4, concurrency=3
    )
    assert 1 < peak <= 3
