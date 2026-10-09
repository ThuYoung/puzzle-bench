"""Sandbox worker tests: isolation, respawn, fidelity vs the in-process reference."""

from hintbench.envs.debug import run_tests
from hintbench.sandbox import SandboxRunner
from hintbench.seeds_debug import SEED_SUMRANGE

HANG_SRC = "def f(n):\n    while True:\n        pass\n"
KILLER_SRC = "import os\nos._exit(0)\n"
OK_SRC = SEED_SUMRANGE.source

T = (("test_one", "def test_one():\n    assert solution.f(1) is None\n"),)
SUM_TESTS = SEED_SUMRANGE.tests


def test_fidelity_matches_inprocess_reference():
    runner = SandboxRunner()
    try:
        sandboxed = runner.run_tests(OK_SRC, SUM_TESTS)
        reference = run_tests(OK_SRC, SUM_TESTS)
    finally:
        runner.close()
    for name in sandboxed:
        assert sandboxed[name]["passed"] == reference[name]["passed"]
        assert sandboxed[name]["kind"] == reference[name]["kind"]


def test_hang_is_contained_and_worker_survives():
    runner = SandboxRunner(timeout=0.3)
    try:
        out = runner.run_tests(HANG_SRC, T)
        assert out["test_one"]["kind"] == "hang" and not out["test_one"]["passed"]
        # same worker must still answer the next request
        ok = runner.run_tests(OK_SRC, SUM_TESTS)
        assert all(o["passed"] for o in ok.values())
    finally:
        runner.close()


def test_dead_worker_respawns():
    runner = SandboxRunner()
    try:
        dead = runner.run_tests(KILLER_SRC, T)
        assert dead["test_one"]["kind"] == "sandbox" and not dead["test_one"]["passed"]
        # worker killed itself mid-request; the next call must respawn cleanly
        ok = runner.run_tests(OK_SRC, SUM_TESTS)
        assert all(o["passed"] for o in ok.values())
    finally:
        runner.close()


def test_error_outcomes_carry_details_for_hint_goods():
    buggy = OK_SRC.replace("b + 1", "b")  # failing assertions with messages
    runner = SandboxRunner()
    try:
        out = runner.run_tests(buggy, SUM_TESTS)
    finally:
        runner.close()
    failed = [n for n, o in out.items() if not o["passed"]]
    assert failed
    assert any("expected" in out[n]["detail"] for n in failed)
    assert any("AssertionError" in out[n]["tb"] for n in failed)
