"""Debug-env tests: test execution, hint goods, consistency, lifecycle."""

from puzzlebench.economy import Wallet
from puzzlebench.envs.debug import DebugEnv
from puzzlebench.tasks_debug import DEBUG_TASKS, TASK_PALINDROME, TASK_SUM


async def test_buggy_baseline_f2p_fail_p2p_pass():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    outcomes = env._hidden()
    assert all(not outcomes[n]["passed"] for n in TASK_SUM.f2p)
    assert all(outcomes[n]["passed"] for n in TASK_SUM.p2p)


async def test_clean_fix_without_hints():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await env.reset()
    reply = await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    assert "1/1 pass" in reply  # only public results leak
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and solved.clean
    assert result.s_complete == result.s_unaided


async def test_ladder_goods_content_and_order():
    env = DebugEnv(TASK_SUM, wallet=Wallet(9))
    await env.reset()
    assert "ladder order" in await env.buy_hint(3)
    assert await env.buy_hint(99) == "no such hint"
    assert "test_sum_three" in await env.buy_hint(1)
    assert "already owned" in await env.buy_hint(1)
    l2 = await env.buy_hint(2)
    assert "expected 6, got 3" in l2 and "expected 55, got 45" in l2
    assert "ladder order" in await env.buy_hint(4)  # L3 not owned yet
    assert "solution.py lines 4-5" in (await env.buy_hint(3), await env.buy_hint(4))[1]
    assert env.coins == 9 - (1 + 1 + 2 + 2)


async def test_l1_reflects_state_at_purchase_time():
    env = DebugEnv(TASK_SUM, wallet=Wallet(9))
    await env.reset()
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    assert "none" in await env.buy_hint(1)


async def test_sketch_hint_taints_spoiled_milestones():
    env = DebugEnv(TASK_SUM, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3, 4, 5):
        await env.buy_hint(level)
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and not solved.clean
    assert result.s_unaided < result.s_complete


async def test_hint_consistency_requires_region_touch():
    env = DebugEnv(TASK_PALINDROME, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3, 4):
        await env.buy_hint(level)
    outside = TASK_PALINDROME.wrong_variants[1]  # edits line 4; region is line 3
    await env.step(f"```python\n{outside}```")
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert hc.applicable and not hc.achieved


async def test_zero_info_purchase_not_applicable():
    env = DebugEnv(TASK_PALINDROME, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3, 4):
        await env.buy_hint(level)
    result = await env.close()  # no patch after the region reveal
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert not hc.applicable
    assert result.s_complete == result.s_unaided


async def test_low_hints_alone_do_not_gate_consistency():
    # buying only L1-L3 (no region) leaves the gated milestone out entirely
    env = DebugEnv(TASK_SUM, wallet=Wallet(4))
    await env.reset()
    await env.buy_hint(1)
    await env.buy_hint(2)
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert not hc.applicable


async def test_grants_inject_text_and_taint():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0), preload_levels=(4, 5))
    preamble = await env.reset()
    assert "Fault region: solution.py lines 4-5" in preamble
    assert "Fix sketch:" in preamble


async def test_unparseable_patch_wastes_turn_and_keeps_source():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await env.reset()
    assert "no parseable patch" in await env.step("def broken(:\n")
    result = await env.close()
    fmt = next(e for e in result.milestones if e.milestone_id == "format_ok")
    assert not fmt.achieved  # 0/1 parseable


async def test_regression_guard_fails_when_p2p_breaks():
    overshoot = TASK_SUM.wrong_variants[2]  # range(1, n+2) breaks sum_up_to(0)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await env.reset()
    await env.step(f"```python\n{overshoot}```")
    result = await env.close()
    reg = next(e for e in result.milestones if e.milestone_id == "regression_guard")
    assert not reg.achieved


async def test_lifecycle_guards():
    env = DebugEnv(TASK_SUM, wallet=Wallet(2), max_turns=1)
    await env.reset()
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    assert "episode finished" in await env.step("```python\nx = 1\n```")
    assert "episode finished" in await env.buy_hint(1)
    assert env.coins == 2


async def test_all_tasks_internal_consistency():
    # every bank task: fix solves everything; buggy keeps P2P green
    for task in DEBUG_TASKS:
        env = DebugEnv(task, wallet=Wallet(0))
        buggy = env._hidden()
        assert all(not buggy[n]["passed"] for n in task.f2p), task.task_id
        assert all(buggy[n]["passed"] for n in task.p2p), task.task_id
        fixed = env._hidden(task.fixed_source)
        assert all(o["passed"] for o in fixed.values()), task.task_id


# -- diagnosis probe and surgical precision --------------------------------------

from puzzlebench.tasks_expr import EXPR_TASKS

EXPR_ZOL = EXPR_TASKS[0]  # zolarith: two planted grammar faults, answer 4


async def test_diagnosis_choices_revealed_only_after_solve():
    env = DebugEnv(EXPR_ZOL, wallet=Wallet(0))
    await env.reset()
    reply = await env.step(f"```python\n{EXPR_ZOL.buggy_source}```")  # still buggy
    assert "Diagnosis probe" not in reply
    reply = await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    assert "Diagnosis probe" in reply
    assert EXPR_ZOL.fault_choices[-1] in reply
    reply = await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    assert "Diagnosis probe" not in reply  # presented once


async def test_diagnosis_correct_answer_clean_without_hints():
    env = DebugEnv(EXPR_ZOL, wallet=Wallet(0))
    await env.reset()
    await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    await env.probe_answer(EXPR_ZOL.fault_answer)
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.applicable and diag.achieved and diag.clean


async def test_diagnosis_wrong_answer_one_shot():
    env = DebugEnv(EXPR_ZOL, wallet=Wallet(0))
    await env.reset()
    await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    wrong = 1 if EXPR_ZOL.fault_answer != 1 else 2
    await env.probe_answer(wrong)
    await env.probe_answer(EXPR_ZOL.fault_answer)  # second attempt must not count
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.applicable and not diag.achieved
    probe = next(p for p in result.meta["probes"] if p["kind"] == "diagnosis")
    assert probe["claimed"] == wrong and probe["ok"] is False


async def test_diagnosis_tainted_by_sketch_purchase():
    env = DebugEnv(EXPR_ZOL, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3, 4, 5):
        await env.buy_hint(level)
    await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    await env.probe_answer(EXPR_ZOL.fault_answer)
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.achieved and not diag.clean


async def test_diagnosis_not_applicable_without_choices():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))  # hand task: no fault choices
    await env.reset()
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert not diag.applicable
    # excluded from every denominator: a perfect run still scores 1.0
    assert result.s_complete == result.s_unaided == 1.0


async def test_diagnosis_blind_answer_before_reveal_ignored():
    env = DebugEnv(EXPR_ZOL, wallet=Wallet(0))
    await env.reset()
    await env.probe_answer(EXPR_ZOL.fault_answer)  # choices not on the table yet
    assert env.diagnosis_answer is None  # the one shot is not consumed
    await env.step(f"```python\n{EXPR_ZOL.fixed_source}```")
    await env.probe_answer(EXPR_ZOL.fault_answer)
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.achieved


async def test_surgical_precision_located_vs_cosmetic():
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await env.reset()
    await env.step(f"```python\n{TASK_SUM.fixed_source}```")
    result = await env.close()
    assert result.meta["surgical"]["precision"] == 1.0

    # same fix plus a cosmetic docstring edit outside the fault region
    patched = TASK_SUM.fixed_source.replace(
        "Return 1 + 2 + ... + n for n >= 0.", "Return the sum of 1..n."
    )
    env2 = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await env2.reset()
    await env2.step(f"```python\n{patched}```")
    result2 = await env2.close()
    surgical = result2.meta["surgical"]
    assert 0 < surgical["precision"] < 1.0 and surgical["in_region_lines"]


# -- pipeline: archetypes through protocols A/B -------------------------------

from puzzlebench.agents.debug_scripted import ScriptedDebugAgent
from puzzlebench.protocols import optimal_allocation, regret, run_protocol_a, run_protocol_b
from puzzlebench.tasks_debug import DEBUG_LADDER

LADDER = tuple(h.level for h in DEBUG_LADDER)
COSTS = {h.level: h.cost for h in DEBUG_LADDER}
LEVELS = (0,) + LADDER
TARGETS = list(DEBUG_TASKS)
BUDGET = 9
SEEDS = 2


def env_factory(target, wallet, grants):
    return DebugEnv(target, wallet=wallet, max_turns=8, preload_levels=grants)


def agent_factory(policy, **kw):
    return lambda seed: ScriptedDebugAgent(seed, hint_policy=policy, **kw)


async def test_protocol_a_cells_are_purchase_free():
    matrix = await run_protocol_a(
        env_factory, agent_factory("smart", skill=0.4), TARGETS, LEVELS, ladder=LADDER, seeds=SEEDS
    )
    for (task_id, level), runs in matrix.items():
        expected = {lv for lv in LADDER if lv <= level}
        for r in runs:
            assert all(p.turn == 0 for p in r.purchases), f"free purchase in cell {(task_id, level)}"
            assert {p.level for p in r.purchases} == expected


async def test_answer_level_unlocks_every_cell():
    matrix = await run_protocol_a(
        env_factory, agent_factory("never", skill=0.0), TARGETS, (0, 5), ladder=LADDER, seeds=SEEDS
    )
    for task in TARGETS:
        for r in matrix[(task, 5)]:
            solved = next(e for e in r.milestones if e.milestone_id == "solved")
            assert solved.achieved and not solved.clean  # sketch is decisive but tainting


async def test_debug_archetype_triads():
    out = {}
    for policy, kw in [
        ("never", dict(skill=0.95)),
        ("smart", dict(skill=0.35)),
        ("panic", dict(skill=0.1)),
    ]:
        matrix = await run_protocol_a(
            env_factory, agent_factory(policy, **kw), TARGETS, LEVELS, ladder=LADDER, seeds=SEEDS
        )
        oracle = optimal_allocation(matrix, TARGETS, LEVELS, COSTS, BUDGET)
        episodes = await run_protocol_b(
            env_factory, agent_factory(policy, **kw), TARGETS, budget=BUDGET, seeds=SEEDS
        )
        flat = [r for runs in episodes.values() for r in runs]
        out[policy] = dict(
            complete=sum(r.s_complete for r in flat) / len(flat),
            unaided=sum(r.s_unaided for r in flat) / len(flat),
            regret=regret(matrix, TARGETS, LEVELS, COSTS, BUDGET, episodes),
            spent=[sum(COSTS[p.level] for p in r.purchases) for r in flat],
        )

    never, smart, panic = out["never"], out["smart"], out["panic"]
    assert never["complete"] == never["unaided"]
    assert all(s == 0 for s in never["spent"])
    # panic climbs to the sketch when stuck: completion must outrun unaided
    assert panic["unaided"] < panic["complete"]
    assert max(panic["spent"]) == 9
    for out_ in out.values():
        assert all(s <= BUDGET for s in out_["spent"])
        assert abs(out_["regret"]) <= len(TARGETS) + 1
