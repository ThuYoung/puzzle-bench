"""Expression-language trap bank: partitions, trap semantics, diagnosis metadata."""

from puzzlebench.envs.debug import run_tests
from puzzlebench.tasks_expr import EXPR_TASKS

ZOL, ZOO = EXPR_TASKS


def _eval(source: str, fname: str, expr: str):
    ns: dict = {}
    exec(source, ns)
    return ns[fname](expr)


def test_fixed_sources_pass_everything():
    for t in EXPR_TASKS:
        outcomes = run_tests(t.fixed_source, t.hidden_tests + t.public_tests)
        assert all(o["passed"] for o in outcomes.values()), t.task_id


def test_buggy_partition_and_public_invariant():
    for t in EXPR_TASKS:
        assert t.f2p and t.p2p
        public = run_tests(t.buggy_source, t.public_tests)
        assert all(o["passed"] for o in public.values()), t.task_id


def test_traps_are_counter_conventional():
    # fixed: documented anti-idiom semantics
    assert _eval(ZOL.fixed_source, "zolarith", "2 ^ 3 ^ 2") == 64
    assert _eval(ZOL.fixed_source, "zolarith", "-2 ^ 2") == 4
    assert _eval(ZOO.fixed_source, "zoologic", "1 or 0 and 0") == 0
    assert _eval(ZOO.fixed_source, "zoologic", "not 1 == 2") == 0
    # buggy: conventional grammar wins instead
    assert _eval(ZOL.buggy_source, "zolarith", "2 ^ 3 ^ 2") == 512
    assert _eval(ZOL.buggy_source, "zolarith", "-2 ^ 2") == -4
    assert _eval(ZOO.buggy_source, "zoologic", "1 or 0 and 0") == 1
    assert _eval(ZOO.buggy_source, "zoologic", "not 1 == 2") == 1


def test_idiom_rewrite_detectors_green_on_buggy():
    # documented rules the buggy source honours: a rewrite with standard
    # idioms fails these even though they are not the planted faults
    assert _eval(ZOL.buggy_source, "zolarith", "-7 % 3") == -1  # Python gives 2
    assert _eval(ZOO.buggy_source, "zoologic", "3 > 2 > 1") == 0  # Python chain gives 1


def test_wrong_variants_really_wrong():
    for t in EXPR_TASKS:
        for w in t.wrong_variants:
            assert w != t.fixed_source
            outcomes = run_tests(w, t.hidden_tests)
            assert not all(o["passed"] for o in outcomes.values()), t.task_id


def test_fault_region_covers_parser_methods():
    for t in EXPR_TASKS:
        a, b = t.fault_region
        lines = t.buggy_source.splitlines()[a - 1 : b]
        assert any("_factor" in ln or "_expr" in ln for ln in lines), t.task_id


def test_diagnosis_metadata():
    for t in EXPR_TASKS:
        assert len(t.fault_choices) == 4
        assert 1 <= t.fault_answer <= 4
        true_text = t.fault_choices[t.fault_answer - 1]
        assert "Two planted faults" in true_text
        others = [c for i, c in enumerate(t.fault_choices, 1) if i != t.fault_answer]
        assert all(c != true_text for c in others)
