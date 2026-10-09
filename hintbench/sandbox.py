"""Sandboxed test execution: a persistent worker subprocess.

Real-model patches are arbitrary code, so the env must never exec them
in-process. This module spawns ONE worker (JSON-lines protocol over pipes)
and reuses it for every suite run; per-test SIGALRM timeouts contain hangs,
and a dead worker (a patch can always os._exit) is detected and respawned.

The worker imports run_tests from hintbench.envs.debug, so the execution
semantics have a single source of truth; spawn cost (~0.2s) amortizes across
the whole session. This is process isolation with timeouts, not a container:
filesystem/network restrictions are a pre-real-benchmark requirement (see
README next-steps).
"""

from __future__ import annotations

import json
import select
import subprocess
import sys
from typing import Any

_WORKER = """
import json, signal, sys
from hintbench.envs.debug import run_tests

class Timeout(Exception):
    pass

def handler(sig, frame):
    raise Timeout()

signal.signal(signal.SIGALRM, handler)

HANG = {"passed": False, "kind": "hang", "detail": "exceeded budget", "tb": ""}
SKIP = {"passed": False, "kind": "hang", "detail": "skipped after earlier hang", "tb": ""}

for line in sys.stdin:
    try:
        req = json.loads(line)
        budget = req["timeout"]
        # single-file requests carry "source"; multi-file packages carry "files"
        payload = req["source"] if "source" in req else req["files"]
        outcomes = {}
        hung = False
        for name, src in req["tests"]:
            if hung:
                outcomes[name] = dict(SKIP)  # a hanging module poisons the suite
                continue
            signal.setitimer(signal.ITIMER_REAL, budget)
            try:
                outcomes[name] = run_tests(payload, ((name, src),))[name]
            except Timeout:
                outcomes[name] = dict(HANG)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            if outcomes[name].get("detail", "").startswith("Timeout:"):
                # run_tests caught the alarm as a generic error: re-label it
                outcomes[name] = dict(HANG)
            hung = outcomes[name]["kind"] == "hang"
        sys.stdout.write(json.dumps({"outcomes": outcomes}) + "\\n")
        sys.stdout.flush()
    except Exception as e:
        sys.stdout.write(json.dumps({"error": f"{type(e).__name__}: {e}"}) + "\\n")
        sys.stdout.flush()
"""

SANDBOX_OUTCOME = {"passed": False, "kind": "sandbox", "detail": "worker died mid-suite", "tb": ""}


class SandboxRunner:
    """Sync request/response client to the worker; safe to share across envs."""

    def __init__(self, timeout: float = 0.5) -> None:
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None

    def _ensure(self) -> subprocess.Popen:
        if self._proc is None or self._proc.poll() is not None:
            self._proc = subprocess.Popen(
                [sys.executable, "-c", _WORKER],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, bufsize=1,
            )
        return self._proc

    def run_tests(
        self, source: str | dict[str, str], tests: tuple[tuple[str, str], ...]
    ) -> dict[str, dict[str, Any]]:
        """Same outcome shape as run_tests, plus kind == "hang" on timeouts."""
        key = "source" if isinstance(source, str) else "files"
        request = json.dumps(
            {key: source, "tests": [list(t) for t in tests], "timeout": self.timeout}
        )
        proc = self._ensure()
        try:
            assert proc.stdin and proc.stdout
            proc.stdin.write(request + "\n")
            proc.stdin.flush()
            line = self._readline(proc, deadline=self.timeout * max(len(tests), 1) + 10)
            if line is None:
                raise BrokenPipeError("worker timeout")
            payload = json.loads(line)
        except (BrokenPipeError, OSError, json.JSONDecodeError):
            self._kill()
            return {name: dict(SANDBOX_OUTCOME) for name, _ in tests}
        if "error" in payload:
            return {
                name: {"passed": False, "kind": "sandbox", "detail": payload["error"], "tb": ""}
                for name, _ in tests
            }
        return payload["outcomes"]

    def _readline(self, proc: subprocess.Popen, deadline: float) -> str | None:
        assert proc.stdout
        ready, _, _ = select.select([proc.stdout], [], [], deadline)
        if not ready:
            return None
        line = proc.stdout.readline()
        return line if line else None  # EOF on a dead worker

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass
            self._proc = None

    def close(self) -> None:
        self._kill()

    def __call__(self, source: str | dict[str, str], tests: tuple[tuple[str, str], ...]) -> dict[str, dict[str, Any]]:
        return self.run_tests(source, tests)


_DEFAULT: SandboxRunner | None = None


def default_runner() -> SandboxRunner:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = SandboxRunner()
    return _DEFAULT
