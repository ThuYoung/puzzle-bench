"""Track B2 integrity: planted bugs fail hidden tests, never public ones."""

from puzzlebench.envs.debug import run_tests
from puzzlebench.tasks_systems import SYSTEM_TASKS


def test_fixed_sources_are_green():
    for task in SYSTEM_TASKS:
        failed = [n for n, o in run_tests(task.fixed_source, task.hidden_tests).items() if not o["passed"]]
        assert not failed, f"{task.task_id}: {failed}"


def test_buggy_partition_and_public_invariant():
    for task in SYSTEM_TASKS:
        assert task.f2p, f"{task.task_id}: planted bug fails nothing"
        assert task.p2p, f"{task.task_id}: no regression-guard material"
        public = run_tests(task.buggy_source, task.public_tests)
        assert all(o["passed"] for o in public.values()), task.task_id


def test_fault_region_covers_the_plant():
    for task in SYSTEM_TASKS:
        a, b = task.fault_region
        buggy_lines = task.buggy_source.splitlines()[a - 1 : b]
        fixed_lines = task.fixed_source.splitlines()[a - 1 : b]
        assert buggy_lines != fixed_lines, task.task_id


def test_wrong_variants_are_actually_wrong():
    for task in SYSTEM_TASKS:
        for variant in task.wrong_variants:
            failed = [n for n, o in run_tests(variant, task.hidden_tests).items() if not o["passed"]]
            assert failed, f"{task.task_id}: a wrong variant passes everything"
