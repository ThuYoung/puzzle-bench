"""Multi-file package tasks: package loading, env mechanics, bank invariants."""

import sys

from hintbench.economy import Wallet
from hintbench.envs.debug import DebugEnv, run_tests
from hintbench.tasks_multifile import MULTI_TASKS

ZEL, LED = MULTI_TASKS


def test_package_loader_cross_import_and_cleanup():
    outcomes = run_tests(dict(LED.fixed_files), LED.hidden_tests)
    assert all(o["passed"] for o in outcomes.values())
    # the worker is persistent: module entries must not leak across runs
    for mod in ("ledstore", "ledlogic", "ledapi", "zlex", "zparse", "zeval"):
        assert mod not in sys.modules


def test_package_loader_collection_error():
    broken = dict(ZEL.fixed_files)
    broken["zparse"] = "def broken(:\n"
    outcomes = run_tests(broken, ZEL.hidden_tests)
    assert all(not o["passed"] and o["kind"] == "collection" for o in outcomes.values())


def test_bank_invariants():
    for t in MULTI_TASKS:
        assert t.files and t.fixed_files and len(t.fault_regions) >= 2
        # faults span different modules
        assert len({mod for mod, _, _ in t.fault_regions}) == len(t.fault_regions)
        outcomes = run_tests(dict(t.fixed_files), t.hidden_tests + t.public_tests)
        assert all(o["passed"] for o in outcomes.values()), t.task_id
        public = run_tests(dict(t.files), t.public_tests)
        assert all(o["passed"] for o in public.values()), t.task_id
        assert 1 <= t.fault_answer <= len(t.fault_choices)


async def test_reset_lists_every_file_and_named_patch_flow():
    env = DebugEnv(ZEL, wallet=Wallet(0))
    preamble = await env.reset()
    assert "--- zlex.py ---" in preamble and "--- zeval.py ---" in preamble
    # patch only the parser: the two evaluator-driven failures stay red
    reply = await env.step(f"```python:zparse\n{ZEL.fixed_files[1][1]}```")
    assert "patch applied to zparse.py" in reply
    assert "hidden tests: 10/12 pass" in reply
    # then the evaluator (untagged block replaces the ENTRY module)
    reply = await env.step(f"```python\n{ZEL.fixed_files[2][1]}```")
    assert "patch applied" in reply and "hidden tests: 12/12 pass" in reply
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved


async def test_unknown_module_block_is_skipped():
    env = DebugEnv(ZEL, wallet=Wallet(0))
    await env.reset()
    reply = await env.step("```python:zz_unknown\nx = 1\n```")
    assert reply == "no parseable patch; turn wasted"


async def test_multi_hint_regions_text():
    env = DebugEnv(LED, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3):
        await env.buy_hint(level)
    l4 = await env.buy_hint(4)
    assert l4 == "Fault regions: ledstore.py lines 19-19; ledlogic.py lines 31-31"


async def test_multi_surgical_per_file():
    # fix only ledlogic (one line inside its region): all changed lines sit
    # inside SOME region only if no other file is touched
    env = DebugEnv(LED, wallet=Wallet(0))
    await env.reset()
    await env.step(f"```python:ledlogic\n{LED.fixed_files[1][1]}```")
    result = await env.close()
    surgical = result.meta["surgical"]
    assert surgical["precision"] == 1.0
    assert surgical["in_region_lines"] == ["ledlogic:31"]


async def test_multi_diagnosis_end_to_end():
    env = DebugEnv(ZEL, wallet=Wallet(0))
    await env.reset()
    # solving requires both module fixes; choices appear once green
    await env.step(
        f"```python:zparse\n{ZEL.fixed_files[1][1]}```\n```python:zeval\n{ZEL.fixed_files[2][1]}```"
    )
    await env.probe_answer(ZEL.fault_answer)
    result = await env.close()
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.applicable and diag.achieved and diag.clean


async def test_multi_hint_consistency_touches_any_region():
    env = DebugEnv(LED, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3, 4):
        await env.buy_hint(level)
    # patch only ledstore: touches ONE of the two regions — consistent
    await env.step(f"```python:ledstore\n{LED.fixed_files[0][1]}```")
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert hc.applicable and hc.achieved


async def test_sandbox_matches_in_process_for_packages():
    from hintbench.sandbox import SandboxRunner

    runner = SandboxRunner()
    try:
        for t in MULTI_TASKS:
            expected = run_tests(dict(t.files), t.hidden_tests)
            via_sandbox = runner.run_tests(dict(t.files), t.hidden_tests)
            assert set(via_sandbox) == set(expected)
            for name, outcome in expected.items():
                assert via_sandbox[name]["passed"] == outcome["passed"], (t.task_id, name)
    finally:
        runner.close()
