"""Track B6 emergent-interaction tasks: partitions and env mechanics."""

from hintbench.economy import Wallet
from hintbench.envs.debug import DebugEnv, run_tests
from hintbench.tasks_emergent import EMERGENT_TASKS

CREDIT, VOTED = EMERGENT_TASKS


def test_bank_invariants():
    for t in EMERGENT_TASKS:
        fixed_bad = [
            n
            for n, o in run_tests(t.fixed_source, t.hidden_tests + t.public_tests).items()
            if not o["passed"]
        ]
        assert not fixed_bad, t.task_id
        buggy = run_tests(t.buggy_source, t.hidden_tests)
        failed = {n for n, o in buggy.items() if not o["passed"]}
        assert failed == set(t.f2p) and set(t.p2p).isdisjoint(failed), t.task_id
        public = run_tests(t.buggy_source, t.public_tests)
        assert all(o["passed"] for o in public.values()), t.task_id
        assert 1 <= t.fault_answer <= len(t.fault_choices)


async def test_credit_isolated_rules_pass_on_buggy():
    """The buggy source satisfies every rule in isolation; only the
    compositions (same-day op + accrual, multi-day advance) diverge."""
    env = DebugEnv(CREDIT, wallet=Wallet(0))
    await env.reset()
    reply = await env.step(f"```python\n{CREDIT.fixed_source}```")
    assert "hidden tests: 13/13 pass" in reply
    assert "PROBE" in reply  # diagnosis options revealed after the green suite
    await env.probe_answer(CREDIT.fault_answer)
    result = await env.close()
    by_id = {e.milestone_id: e for e in result.milestones}
    assert by_id["solved"].achieved and by_id["diagnosis"].achieved


async def test_voted_partial_fix_leaves_b2_red():
    """Fixing close() alone: the reactivate streak fault keeps its test red."""
    env = DebugEnv(VOTED, wallet=Wallet(0))
    await env.reset()
    # fixed close() but buggy reactivate() — assemble a half-fixed source
    half = VOTED.fixed_source.replace(
        """        self._active.add(member)
        self._streak[member] = 0  # fresh streak
""",
        """        self._active.add(member)
""",
    )
    assert half != VOTED.fixed_source
    reply = await env.step(f"```python\n{half}```")
    assert "hidden tests: 10/11 pass" in reply
    result = await env.close()
    by_id = {e.milestone_id: e for e in result.milestones}
    assert not by_id["solved"].achieved
    # the b1 fix converts two of three F2P tests: first-flip yes, all-flip no
    assert by_id["first_f2p_pass"].achieved
    assert not by_id["all_f2p_pass"].achieved
