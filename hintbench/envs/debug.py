"""Debug-economy environment (Track B prototype).

The agent receives a buggy module and a public example test. Everything else
is an information good: which hidden tests fail (L1), their assertion
messages (L2), a trimmed traceback (L3), the fault region (L4), and a fix
sketch (L5). step() replaces the module and reports ONLY public-test results
— hidden-test outcomes are the paid goods, never leaked (silent grading).

A patch is a full replacement of solution.py (fenced code block or raw
source). Execution goes through the persistent sandbox worker (hintbench.
sandbox): process isolation plus per-test timeouts, so hostile or hanging
patches cannot take the harness down. run_tests remains as the in-process
reference implementation used by the worker and by fast tests.
"""

from __future__ import annotations

import difflib
import re
import traceback
from types import SimpleNamespace
from typing import Any

from hintbench.economy import Wallet
from hintbench.grader import grade
from hintbench.schema import EpisodeResult, PurchaseEvent
from hintbench.tasks_debug import DEBUG_LADDER, REGION_LEVELS, DebugTask, make_debug_spec

_FENCE = re.compile(r"```(?:python)?(?:\:([A-Za-z_][\w]*(?:\.py)?))?\s*\n(.*?)```", re.DOTALL)


def run_tests(
    source: str | dict[str, str], tests: tuple[tuple[str, str], ...]
) -> dict[str, dict[str, Any]]:
    """Execute a test suite against a candidate solution, in-process.

    source is either the single solution.py source or a {module_name: source}
    mapping (multi-file task; the LAST module in insertion order is the entry
    point tests reach as `solution`). Shared by the env and the mutation
    pipeline's execution filter (the filter additionally isolates it in a
    subprocess with a timeout). Only tasks admitted past the filter may reach
    the in-process path.
    """
    module = _load_module(source) if isinstance(source, str) else _load_package(source)
    outcomes: dict[str, dict[str, Any]] = {}
    for name, src in tests:
        if module is None:
            outcomes[name] = {"passed": False, "kind": "collection", "detail": "solution.py failed to import", "tb": ""}
            continue
        test_ns: dict[str, Any] = {"solution": module}
        try:
            exec(compile(src, f"{name}.py", "exec"), test_ns)
            test_ns[name]()
            outcomes[name] = {"passed": True, "kind": "", "detail": "", "tb": ""}
        except AssertionError as exc:
            outcomes[name] = {"passed": False, "kind": "assertion", "detail": str(exc), "tb": traceback.format_exc()}
        except Exception as exc:  # noqa: BLE001 - errors are information goods too
            outcomes[name] = {"passed": False, "kind": "error", "detail": f"{type(exc).__name__}: {exc}", "tb": traceback.format_exc()}
    return outcomes


def _load_module(source: str) -> SimpleNamespace | None:
    ns: dict[str, Any] = {}
    try:
        exec(compile(source, "solution.py", "exec"), ns)
    except Exception:
        return None  # collection error: every test errors
    return SimpleNamespace(**{k: v for k, v in ns.items() if not k.startswith("__")})


def _load_package(files: dict[str, str]) -> SimpleNamespace | None:
    """Load a {module_name: source} mapping as importable modules.

    Each module is registered in sys.modules BEFORE exec so plain
    `import sibling` statements resolve; the entry module (last key) is what
    tests see as `solution`. sys.modules entries are removed afterwards so a
    persistent worker never leaks modules across episodes.
    """
    import sys
    import types

    loaded: list[str] = []
    try:
        entry = None
        for modname, src in files.items():
            mod = types.ModuleType(modname)
            mod.__file__ = f"{modname}.py"
            sys.modules[modname] = mod
            loaded.append(modname)
            try:
                exec(compile(src, f"{modname}.py", "exec"), mod.__dict__)
            except Exception:
                return None  # collection error: every test errors
            entry = mod
        assert entry is not None
        return SimpleNamespace(
            **{k: v for k, v in vars(entry).items() if not k.startswith("__")}
        )
    finally:
        for modname in loaded:
            sys.modules.pop(modname, None)


class DebugEnv:
    """Async env API mirroring the wordle self-check: reset/step/buy_hint/
    request_probe/probe_answer/close, with the same purchase stamping,
    ladder-order, and lifecycle rules (spec v0.2 sections 4, 6, 7)."""

    def __init__(
        self,
        task: DebugTask,
        *,
        wallet: Wallet,
        max_turns: int = 8,
        preload_levels: tuple[int, ...] = (),
        runner=None,
    ) -> None:
        self.task = task
        self.wallet = wallet
        self.spec = make_debug_spec(task, wallet.balance)
        # test execution goes through the sandbox worker; an in-process runner
        # (run_tests) may be injected only by tests for speed
        self.runner = runner
        self.max_turns = max_turns
        self.turn = 0
        # multi-file tasks carry task.files; single-file tasks are the
        # degenerate one-module case (module name "solution", file solution.py)
        self.current_files: dict[str, str] = (
            dict(task.files) if task.files else {"solution": task.buggy_source}
        )
        self._buggy_files = dict(self.current_files)
        self.entry: str = next(reversed(self.current_files))
        self._fault_regions: tuple[tuple[str, int, int], ...] = (
            task.fault_regions or ((self.entry, *task.fault_region),)
        )
        self.purchases: list[PurchaseEvent] = []
        self.granted_texts: list[tuple[int, str]] = []
        self.submissions = 0
        self.parseable = 0
        self.format_turn = -1
        self.first_f2p_turn = -1
        self.all_f2p_turn = -1
        self.solved_turn = -1
        self.hc_turn = -1  # hint-consistency evaluated (pass or fail) at this turn
        self.hc_ok = False
        self.probes: list[dict[str, Any]] = []
        self.diagnosis_answer: int | None = None  # 1-based choice; one shot
        self._diagnosis_turn = -1
        self._choices_presented = False
        self._closed = False
        for level in sorted(preload_levels):
            self._grant(level)

    @property
    def current_source(self) -> str:
        """Compat read for single-file callers: the entry module's source."""
        return self.current_files[self.entry]

    # -- test execution -----------------------------------------------------

    def _exec(self, files: dict[str, str], tests: tuple[tuple[str, str], ...]) -> dict[str, dict[str, Any]]:
        if self.runner is not None:
            return self.runner(files, tests)
        from hintbench.sandbox import default_runner

        return default_runner().run_tests(files, tests)

    def _hidden(self, override: str | dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
        if override is None:
            files = self.current_files
        elif isinstance(override, str):
            files = {self.entry: override}
        else:
            files = override
        return self._exec(files, self.task.hidden_tests)

    def _failing(self, override: str | dict[str, str] | None = None) -> list[str]:
        return [n for n, o in self._hidden(override).items() if not o["passed"]]

    # -- hint machinery -----------------------------------------------------

    def _hint_text(self, level: int, files: dict[str, str]) -> str:
        outcomes = self._hidden(files)
        failing = [n for n, o in outcomes.items() if not o["passed"]]
        if level == 1:
            return "Failing hidden tests: " + (", ".join(failing) if failing else "none")
        if level == 2:
            if not failing:
                return "Assertion details: no failing hidden tests"
            return "Assertion details:\n" + "\n".join(
                f"{n}: {outcomes[n]['detail'] or outcomes[n]['kind']}" for n in failing
            )
        if level == 3:
            if not failing:
                return "Stack trace: no failing hidden tests"
            first = failing[0]
            return f"Stack trace for {first} (trimmed):\n{self._trim_tb(outcomes[first]['tb'], first)}"
        if level == 4:
            regions = "; ".join(
                f"{mod}.py lines {a}-{b}" for mod, a, b in self._fault_regions
            )
            label = "Fault region" if len(self._fault_regions) == 1 else "Fault regions"
            return f"{label}: {regions}"
        if level == 5:
            return f"Fix sketch: {self.task.fix_sketch}"
        raise ValueError(f"no hint at level {level}")

    @staticmethod
    def _trim_tb(tb: str, test_name: str) -> str:
        lines = [ln for ln in tb.splitlines() if "solution.py" in ln or test_name in ln]
        tail = tb.strip().splitlines()[-1:]
        return "\n".join(lines + tail)

    def _grant(self, level: int) -> None:
        # protocol A grant: content snapshot on the buggy source, stamped turn 0
        text = self._hint_text(level, self._buggy_files)
        self.granted_texts.append((level, text))
        self.purchases.append(PurchaseEvent(level=level, turn=0))

    @property
    def coins(self) -> int:
        return self.wallet.balance

    @property
    def owned_levels(self) -> set[int]:
        return {p.level for p in self.purchases}

    def _region_revealed(self) -> bool:
        return bool(REGION_LEVELS & self.owned_levels)

    def _changed_lines(self, files: dict[str, str]) -> set[tuple[str, int]]:
        """(module, 1-based line) pairs differing from the buggy sources."""
        changed: set[tuple[str, int]] = set()
        for mod, src in files.items():
            base = self._buggy_files.get(mod)
            if base is None:
                continue
            sm = difflib.SequenceMatcher(a=base.splitlines(), b=src.splitlines())
            for tag, i1, i2, _, _ in sm.get_opcodes():
                if tag == "equal":
                    continue
                if tag == "insert":
                    changed.add((mod, i1 + 1))
                else:
                    changed.update((mod, ln) for ln in range(i1 + 1, i2 + 1))
        return changed

    # -- env API ------------------------------------------------------------

    async def reset(self) -> str:
        if len(self.current_files) == 1:
            intro = (
                "solution.py is buggy. Submit a full fixed version in a fenced code block."
            )
            files_block = f"--- solution.py ---\n{self.current_files['solution']}---\n"
        else:
            intro = (
                "The package below is buggy. Submit one fenced block per file you "
                f"change, tagged ```python:<module> (untagged blocks replace {self.entry}.py)."
            )
            files_block = "".join(
                f"--- {mod}.py ---\n{src}---\n" for mod, src in self.current_files.items()
            )
        preamble = (
            f"Debug task: {self.task.title}\n"
            f"{intro} "
            f"You have {self.max_turns} submissions. Hidden tests grade the fix; "
            "only public-test results are reported back.\n"
            f"{files_block}"
            f"Hint coins: {self.coins}. Ladder: "
            + "; ".join(f"L{h.level} {h.kind} cost {h.cost}" for h in DEBUG_LADDER)
        )
        if self.granted_texts:
            texts = "\n".join(f"L{level}: {text}" for level, text in self.granted_texts)
            preamble += f"\nPre-granted hints:\n{texts}"
        return preamble

    async def step(self, text: str) -> str:
        if self._closed or self.turn >= self.max_turns:
            return "episode finished"
        self.turn += 1
        self.submissions += 1
        patches = self._extract_patches(text)
        if patches is None:
            return "no parseable patch; turn wasted"
        self.parseable += 1
        self.current_files.update(patches)
        hidden = self._hidden()
        f2p_pass = [n for n in self.task.f2p if hidden[n]["passed"]]
        if f2p_pass and self.first_f2p_turn < 0:
            self.first_f2p_turn = self.turn
        if len(f2p_pass) == len(self.task.f2p) and self.all_f2p_turn < 0:
            self.all_f2p_turn = self.turn
        if all(o["passed"] for o in hidden.values()) and self.solved_turn < 0:
            self.solved_turn = self.turn
        if self.format_turn < 0 and self.parseable / self.submissions >= 0.8:
            self.format_turn = self.turn
        # hint consistency: the first patch after the region is revealed must
        # touch it (spec: the next action agrees with the hint content)
        if self.hc_turn < 0 and self._region_revealed():
            self.hc_turn = self.turn
            self.hc_ok = any(
                mod == rmod and a <= ln <= b
                for mod, ln in self._changed_lines(self.current_files)
                for rmod, a, b in self._fault_regions
            )
        public = self._exec(self.current_files, self.task.public_tests)
        passed = sum(1 for o in public.values() if o["passed"])
        # the hidden pass COUNT is free (a bare failure signal); WHICH tests
        # fail and why is exactly what the ladder sells (L1/L2)
        hidden_passed = sum(1 for o in hidden.values() if o["passed"])
        if len(self.current_files) == 1:
            applied = "patch applied"
        else:
            applied = "patch applied to " + ", ".join(f"{mod}.py" for mod in patches)
        reply = (
            f"{applied}; public tests: {passed}/{len(public)} pass; "
            f"hidden tests: {hidden_passed}/{len(hidden)} pass"
        )
        # diagnosis options are revealed only once the suite is green: before
        # that the true statement IS the answer (a free L5); after solving it
        # discriminates "located the fault" from "patched until green"
        if (
            self.solved_turn >= 0
            and self.task.fault_choices
            and not self._choices_presented
        ):
            self._choices_presented = True
            options = "\n".join(
                f"  {i}. {choice}" for i, choice in enumerate(self.task.fault_choices, start=1)
            )
            reply += (
                "\nDiagnosis probe (scored, ONE attempt): which statement describes "
                'the actual planted fault(s)? Reply "PROBE: <number>" before DONE.'
                f"\n{options}"
            )
        return reply

    def _extract_patches(self, text: str) -> dict[str, str] | None:
        """Module-targeted patches from fenced blocks.

        ```python:mod (or ```:mod) replaces that module; an untagged block
        replaces the entry module; raw unfenced text is a whole-entry patch
        (legacy protocol). Blocks naming unknown modules or failing to compile
        are skipped; None means nothing applicable at all (wasted turn).
        """
        patches: dict[str, str] = {}
        fenced = _FENCE.findall(text)
        if fenced:
            for fname, code in fenced:
                target = (fname or self.entry).removesuffix(".py")
                if target not in self.current_files:
                    continue
                try:
                    compile(code, f"{target}.py", "exec")
                except (SyntaxError, ValueError):
                    continue
                patches[target] = code
        else:
            try:
                compile(text, f"{self.entry}.py", "exec")
            except (SyntaxError, ValueError):
                return None
            patches[self.entry] = text
        return patches or None

    async def buy_hint(self, level: int) -> str:
        if self._closed or self.turn >= self.max_turns:
            return "episode finished"
        spec = next((h for h in DEBUG_LADDER if h.level == level), None)
        if spec is None:
            return "no such hint"
        owned = self.owned_levels
        if level in owned:
            return "hint already owned"
        missing = [h.level for h in DEBUG_LADDER if h.level < level and h.level not in owned]
        if missing:
            return f"hints are sold in ladder order; next available: L{min(missing)}"
        if not self.wallet.try_spend(spec.cost):
            return "insufficient coins"
        # content snapshot at purchase time: what is failing RIGHT NOW
        text = self._hint_text(level, self.current_files)
        self.purchases.append(PurchaseEvent(level=level, turn=self.turn + 1))
        return text

    async def request_probe(self, kind: str = "diagnosis") -> str:
        # kind accepted for protocol compatibility; one probe type here
        return "How many hidden tests currently fail?"

    async def probe_answer(self, n: int) -> None:
        # the first PROBE answer after the choices are revealed is the one-shot
        # diagnosis attempt; answering before reveal is a blind guess and does
        # not consume the shot (the question is not on the table yet)
        if (
            self.task.fault_choices
            and self._choices_presented
            and self.diagnosis_answer is None
        ):
            self.diagnosis_answer = n
            self._diagnosis_turn = self.turn
            self.probes.append({
                "turn": self.turn, "kind": "diagnosis",
                "claimed": n, "truth": self.task.fault_answer,
                "ok": n == self.task.fault_answer,
            })
            return
        if self.task.fault_choices and not self._choices_presented:
            return
        truth = len(self._failing())
        self.probes.append({"turn": self.turn, "kind": "count", "claimed": n, "truth": truth, "ok": n == truth})

    async def close(self) -> EpisodeResult:
        self._closed = True
        achieved: dict[str, int] = {}
        if self.first_f2p_turn >= 0:
            achieved["first_f2p_pass"] = self.first_f2p_turn
        if self.all_f2p_turn >= 0:
            achieved["all_f2p_pass"] = self.all_f2p_turn
        if self.solved_turn >= 0:
            achieved["solved"] = self.solved_turn
        end_turn = max(self.turn, 1)
        final = self._hidden()
        if all(final[n]["passed"] for n in self.task.p2p):
            achieved["regression_guard"] = end_turn
        if self.submissions > 0 and self.parseable / self.submissions >= 0.8:
            achieved["format_ok"] = self.format_turn if self.format_turn >= 0 else end_turn
        if self.hc_turn >= 0 and self.hc_ok:
            achieved["hint_consistent"] = self.hc_turn
        if (
            self.diagnosis_answer is not None
            and self.diagnosis_answer == self.task.fault_answer
        ):
            achieved["diagnosis"] = max(self._diagnosis_turn, 0)
        if not self.probes:
            self.probes.append(
                {"turn": self.turn, "kind": "count", "claimed": None,
                 "truth": len(self._failing()), "ok": None}
            )
        # applicability escape: consistency is only defined when the region was
        # revealed AND at least one patch followed (zero-information purchases
        # must not tax the score, spec v0.2 section 5)
        purchased_levels = (
            {p.level for p in self.purchases} if self.hc_turn >= 0 else set()
        )
        # the diagnosis milestone is undefined on tasks without fault choices
        not_applicable = frozenset() if self.task.fault_choices else frozenset({"diagnosis"})
        # surgical precision: how much of the final diff sits inside the fault
        # regions — a located one-line fix scores 1.0, a full rewrite near 0
        changed = self._changed_lines(self.current_files)
        in_region = {
            (mod, ln)
            for mod, ln in changed
            for rmod, a, b in self._fault_regions
            if mod == rmod and a <= ln <= b
        }
        surgical = {
            "changed_lines": sorted(f"{mod}:{ln}" for mod, ln in changed),
            "in_region_lines": sorted(f"{mod}:{ln}" for mod, ln in in_region),
            "precision": (len(in_region) / len(changed)) if changed else None,
        }
        return grade(
            self.spec,
            achieved,
            self.purchases,
            purchased_levels=purchased_levels,
            not_applicable=not_applicable,
            meta={
                "target": self.task.task_id,
                "probes": self.probes,
                "turns_used": self.turn,
                "surgical": surgical,
                "regret_inputs": {
                    "ladder_costs": {h.level: h.cost for h in DEBUG_LADDER},
                    "budget_initial": self.wallet.balance + self.wallet.spent,
                },
            },
        )
