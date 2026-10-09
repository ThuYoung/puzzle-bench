"""Track B5 volume-escalation task: package invariants and env mechanics."""

import sys

from puzzlebench.economy import Wallet
from puzzlebench.envs.debug import DebugEnv, run_tests
from puzzlebench.tasks_big import BIG_TASKS

MINIDB = BIG_TASKS[0]


def test_bank_invariants():
    t = MINIDB
    assert len(t.files) == len(t.fixed_files) >= 10
    # three planted faults in three different modules
    assert len(t.fault_regions) == 3
    assert len({mod for mod, _, _ in t.fault_regions}) == 3
    outcomes = run_tests(dict(t.fixed_files), t.hidden_tests + t.public_tests)
    assert all(o["passed"] for o in outcomes.values())
    public = run_tests(dict(t.files), t.public_tests)
    assert all(o["passed"] for o in public.values())
    # real gradient: faults split the hidden suite
    buggy = run_tests(dict(t.files), t.hidden_tests)
    failed = {n for n, o in buggy.items() if not o["passed"]}
    assert failed == set(t.f2p) and set(t.p2p).isdisjoint(failed)
    assert 1 <= t.fault_answer <= len(t.fault_choices)


def test_loader_cleans_all_modules():
    run_tests(dict(MINIDB.fixed_files), MINIDB.hidden_tests)
    for mod, _ in MINIDB.files:
        assert mod not in sys.modules


async def test_partial_fix_flow_and_diagnosis_reveal():
    """Fixing dbtypes alone leaves the txn/NULL failures red; the diagnosis
    options appear only once everything passes."""
    env = DebugEnv(MINIDB, wallet=Wallet(0))
    await env.reset()
    fixed = dict(MINIDB.fixed_files)
    reply = await env.step(f"```python:dbtypes\n{fixed['dbtypes']}```")
    assert "patch applied to dbtypes.py" in reply
    assert "hidden tests: 23/27 pass" in reply
    assert "PROBE" not in reply  # not solved yet: no diagnosis options
    reply = await env.step(f"```python:dbtxn\n{fixed['dbtxn']}```")
    # the combined txn+NULL test stays red until dbquery is fixed too
    assert "hidden tests: 24/27 pass" in reply
    reply = await env.step(f"```python:dbquery\n{fixed['dbquery']}```")
    assert "hidden tests: 27/27 pass" in reply
    assert "Which statements are TRUE" in reply or "PROBE" in reply
    await env.probe_answer(MINIDB.fault_answer)
    result = await env.close()
    by_id = {e.milestone_id: e for e in result.milestones}
    assert by_id["solved"].achieved
    assert by_id["diagnosis"].achieved


async def test_l4_lists_all_three_regions():
    env = DebugEnv(MINIDB, wallet=Wallet(9))
    await env.reset()
    for level in (1, 2, 3):
        await env.buy_hint(level)
    l4 = await env.buy_hint(4)
    assert l4 == (
        "Fault regions: dbtypes.py lines 40-51; dbquery.py lines 115-117; "
        "dbtxn.py lines 17-21"
    )


async def test_surgical_precision_partial_rewrite():
    """Fixing only dbtypes yields per-file surgical stats for that module."""
    env = DebugEnv(MINIDB, wallet=Wallet(0))
    await env.reset()
    fixed = dict(MINIDB.fixed_files)
    await env.step(f"```python:dbtypes\n{fixed['dbtypes']}```")
    result = await env.close()
    surgical = result.meta["surgical"]
    assert surgical["precision"] is not None
    assert set(surgical["changed_lines"]) and all(
        ln.startswith("dbtypes:") for ln in surgical["changed_lines"]
    )
    assert surgical["precision"] == 1.0
