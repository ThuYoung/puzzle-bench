"""Novel-spec seed integrity: references stay green and traps stay documented."""

from hintbench.envs.debug import run_tests
from hintbench.mutate import OPERATORS
from hintbench.seeds_novel import NOVEL_SEEDS


def test_novel_seeds_pass_their_own_suites():
    for seed in NOVEL_SEEDS:
        outcomes = run_tests(seed.source, seed.tests)
        failed = [n for n, o in outcomes.items() if not o["passed"]]
        assert not failed, f"{seed.name}: {failed}"


def test_novel_seeds_have_mutation_sites_and_traps():
    for seed in NOVEL_SEEDS:
        sites = sum(len(op(seed.source)) for op in OPERATORS)
        assert sites >= 8, f"{seed.name}: only {sites} sites"
        # a bank needs enough tests for F2P/P2P partitions after mutation
        assert len(seed.tests) >= 5, seed.name
