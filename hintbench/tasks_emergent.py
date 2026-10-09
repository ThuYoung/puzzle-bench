"""Track B6: emergent rule-interaction tasks.

Eight bank generations (handmade / mutations / HOMs / novel specs /
anti-inertia systems / expression grammars / multi-file packages / an
11-module volume package) were all absorbed in one turn by the frontier
pilot model: single-rule spec conformity is solved at every scale tried.
The last untried mechanism is EMERGENCE: two rules are each stated
precisely in the doc, but never jointly — the joint behavior must be
derived by composing them, and the planted fault resolves the composition
by domain instinct instead.

  EM1 creditd: interest accrual base × multi-day compounding.
    R1 says interest accrues "at the end of every day on the available
    balance at that moment"; R2 says freeze/release act "immediately".
    Neither sentence mentions the other, yet together they determine that
    a same-day deposit/release earns interest TODAY. The buggy advance()
    accrues on the day's OPENING balance (the banking instinct) and charges
    simple interest over multi-day advances (the batch instinct).

  EM2 voted: quorum denominator × auto-inactivation timing × streak reset.
    R1 settles a vote with the active count "at the moment of closing";
    R2 inactivates a member after two consecutive misses "effective at the
    closing of the second missed vote". Composed: the departing member
    still counts in THAT vote's denominator. The buggy close() applies
    attendance before tallying (update-then-compute instinct), and
    reactivate() keeps the old miss streak (absence bug).

Public tests avoid every composition edge (green on buggy); hidden tests
drive the compositions directly. F2P/P2P partitions are asserted at import.
"""

from __future__ import annotations

from hintbench.mutate import changed_region
from hintbench.seeds_debug import _t
from hintbench.tasks_debug import DebugTask

# -- EM1: creditd ---------------------------------------------------------------

_CREDIT_FIXED = '''class CreditAccount:
    """Interest-bearing account with balance freezes.

    - deposit(amount) / withdraw(amount) act on the AVAILABLE balance;
      overdrawing it raises ValueError. Frozen funds never cover a
      withdrawal.
    - freeze(amount) / release(amount) move funds between available and
      frozen IMMEDIATELY; overdrawing either side raises ValueError.
    - advance(days=1) passes whole days. At the END of every day, interest
      accrues at 1% of the available balance AT THAT MOMENT, truncated
      toward zero to whole units, and is added to the available balance
      (so later days accrue on it too).

    The constructor's opening balance is the day-0 closing balance.
    """

    RATE_PCT = 1

    def __init__(self, opening: int = 0) -> None:
        if opening < 0:
            raise ValueError("negative opening balance")
        self.available = opening
        self.frozen = 0
        self.day = 0

    def deposit(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("non-positive deposit")
        self.available += amount

    def withdraw(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("non-positive withdrawal")
        if amount > self.available:
            raise ValueError("overdraw")
        self.available -= amount

    def freeze(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("non-positive freeze")
        if amount > self.available:
            raise ValueError("cannot freeze more than available")
        self.available -= amount
        self.frozen += amount

    def release(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("non-positive release")
        if amount > self.frozen:
            raise ValueError("cannot release more than frozen")
        self.frozen -= amount
        self.available += amount

    def advance(self, days: int = 1) -> None:
        if days <= 0:
            raise ValueError("non-positive advance")
        for _ in range(days):
            base = self.available  # the day's closing balance
            self.available += base * self.RATE_PCT // 100
            self.day += 1
'''

# b1: opening-balance accrual (same-day ops shift the base only from the
# next day); b2: simple interest per advance call (no daily compounding)
_CREDIT_BUGGY = _CREDIT_FIXED.replace(
    """        self.available = opening
        self.frozen = 0
        self.day = 0
""",
    """        self.available = opening
        self.frozen = 0
        self.day = 0
        self._day_open = opening
""",
).replace(
    """        if days <= 0:
            raise ValueError("non-positive advance")
        for _ in range(days):
            base = self.available  # the day's closing balance
            self.available += base * self.RATE_PCT // 100
            self.day += 1
""",
    """        if days <= 0:
            raise ValueError("non-positive advance")
        base = self._day_open  # opening balance of the advance period
        self.available += base * self.RATE_PCT * days // 100
        self.day += days
        self._day_open = self.available
""",
)
assert _CREDIT_BUGGY != _CREDIT_FIXED

_CREDIT_TESTS = (
    # b1: same-day freeze cuts the accrual base TODAY
    _t("test_freeze_cuts_today_accrual",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.freeze(4000)\n"
       "    acc.advance()\n"
       "    assert acc.available == 6060, f\"closing-balance accrual: 6000 base, got {acc.available}\""),
    # b1: money deposited today earns interest today
    _t("test_deposit_earns_today",
       "    acc = solution.CreditAccount()\n"
       "    acc.deposit(10000)\n"
       "    acc.advance()\n"
       "    assert acc.available == 10100, f\"today's deposit earns today, got {acc.available}\""),
    # b2: multi-day advance compounds daily
    _t("test_multi_day_compounds",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.advance(3)\n"
       "    assert acc.available == 10303, f\"daily compounding: 10100/10201/10303, got {acc.available}\""),
    # b2: truncation applies per day, not once per call
    _t("test_truncation_is_daily",
       "    acc = solution.CreditAccount(150)\n"
       "    acc.advance(3)\n"
       "    assert acc.available == 153, f\"per-day truncation: 151/152/153, got {acc.available}\""),
    # b1 x b2: same-day freeze plus a multi-day advance hits both
    _t("test_freeze_then_multi_day",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.freeze(2000)\n"
       "    acc.advance(2)\n"
       "    assert acc.available == 8160, f\"8000 closing base, daily: 8080/8160, got {acc.available}\""),
    # -- P2P below: identical on fixed and buggy ------------------------------
    _t("test_opening_accrues_day_one",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.advance()\n"
       "    assert acc.available == 10100, f\"got {acc.available}\""),
    _t("test_second_day_no_ops",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.advance()\n"
       "    acc.advance()\n"
       "    assert acc.available == 10201, f\"got {acc.available}\""),
    _t("test_small_balance_two_days",
       "    acc = solution.CreditAccount(100)\n"
       "    acc.advance(2)\n"
       "    assert acc.available == 102, f\"got {acc.available}\""),
    _t("test_zero_balance_no_interest",
       "    acc = solution.CreditAccount()\n"
       "    acc.advance()\n"
       "    assert acc.available == 0 and acc.day == 1"),
    _t("test_withdraw_overdraw_raises",
       "    acc = solution.CreditAccount(1000)\n"
       "    acc.freeze(600)\n"
       "    try:\n"
       "        acc.withdraw(500)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"frozen funds never cover a withdrawal\")"),
    _t("test_freeze_overdraw_raises",
       "    acc = solution.CreditAccount(1000)\n"
       "    try:\n"
       "        acc.freeze(1001)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
    _t("test_release_overdraw_raises",
       "    acc = solution.CreditAccount(1000)\n"
       "    acc.freeze(100)\n"
       "    try:\n"
       "        acc.release(101)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
    _t("test_day_counter",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.advance()\n"
       "    acc.advance()\n"
       "    assert acc.day == 2, f\"got day={acc.day}\""),
)

_CREDIT_PUBLIC = (
    _t("test_public_accrue",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.advance()\n"
       "    assert acc.available == 10100, f\"got {acc.available}\""),
    _t("test_public_freeze_release",
       "    acc = solution.CreditAccount(10000)\n"
       "    acc.freeze(4000)\n"
       "    acc.release(1000)\n"
       "    assert acc.available == 7000 and acc.frozen == 3000"),
)

_CREDIT_SKETCH = (
    "advance(): accrue 1% on the CURRENT available balance at each day's end "
    "(loop one day at a time), not on the period-opening snapshot, and let "
    "each day's interest land in available so the next day compounds on it "
    "(no simple-interest shortcut for multi-day advances)."
)

_CREDIT_CHOICES = (
    "Two faults: advance() accrues on the day's OPENING balance (same-day deposits, freezes and releases shift the base only from the next day), and multi-day advances charge simple interest on that opening base instead of compounding daily.",
    "Interest truncates to whole units only once per advance() call instead of once per day; everything else follows the doc.",
    "freeze() removes funds from the interest base retroactively, and released funds never earn interest again.",
    "advance() compounds daily on the correct balance, but withdraw() can dip into frozen funds right after interest lands.",
)

# -- EM2: voted -----------------------------------------------------------------

_VOTED_FIXED = '''class Chamber:
    """Quorum voting with attendance-based membership.

    - The chamber has named members; every member starts ACTIVE.
    - open_vote() starts a vote; cast(member, yes) records a ballot
      (casting again overwrites; only active members may vote).
    - close() settles the vote: the proposal PASSES iff
      yes_votes * 2 > active_count, with active_count taken at the moment
      of closing, and appends the outcome to outcomes.
    - Attendance: a member who casts no ballot in a vote misses it. Two
      CONSECUTIVE misses make a member inactive, effective at the closing
      of the second missed vote — that vote's outcome is still settled
      with the member counted active. Casting any ballot resets the
      member's streak.
    - reactivate(member) restores an inactive member with a fresh streak.
    """

    def __init__(self, members: list) -> None:
        self._active = set(members)
        self._streak = {m: 0 for m in members}
        self._vote = None
        self.outcomes: list = []

    def _check_open(self) -> None:
        if self._vote is None:
            raise ValueError("no open vote")

    def open_vote(self) -> None:
        if self._vote is not None:
            raise ValueError("vote already open")
        self._vote = {}

    def cast(self, member: str, yes: bool) -> None:
        self._check_open()
        if member not in self._active:
            raise ValueError(f"not an active member: {member}")
        self._vote[member] = bool(yes)

    def close(self) -> bool:
        self._check_open()
        yes = sum(1 for v in self._vote.values() if v)
        # settle first, attendance second: inactivation takes effect at the
        # closing, so this vote still counts the departing member
        passed = yes * 2 > len(self._active)
        for member in list(self._active):
            if member in self._vote:
                self._streak[member] = 0
            else:
                self._streak[member] += 1
                if self._streak[member] >= 2:
                    self._active.discard(member)
        self._vote = None
        self.outcomes.append(passed)
        return passed

    def reactivate(self, member: str) -> None:
        if member not in self._streak:
            raise ValueError(f"unknown member: {member}")
        self._active.add(member)
        self._streak[member] = 0  # fresh streak

    def active_count(self) -> int:
        return len(self._active)
'''

# b1: close() applies attendance BEFORE tallying (the departing member drops
# out of their own farewell vote's denominator)
_VOTED_BUGGY = _VOTED_FIXED.replace(
    """        yes = sum(1 for v in self._vote.values() if v)
        # settle first, attendance second: inactivation takes effect at the
        # closing, so this vote still counts the departing member
        passed = yes * 2 > len(self._active)
        for member in list(self._active):
            if member in self._vote:
                self._streak[member] = 0
            else:
                self._streak[member] += 1
                if self._streak[member] >= 2:
                    self._active.discard(member)
        self._vote = None
""",
    """        for member in list(self._active):
            if member in self._vote:
                self._streak[member] = 0
            else:
                self._streak[member] += 1
                if self._streak[member] >= 2:
                    self._active.discard(member)
        yes = sum(1 for v in self._vote.values() if v)
        passed = yes * 2 > len(self._active)
        self._vote = None
""",
).replace(
    """        self._active.add(member)
        self._streak[member] = 0  # fresh streak
""",
    """        self._active.add(member)
""",
)
assert _VOTED_BUGGY != _VOTED_FIXED

_VOTE_SETUP = "    ch = solution.Chamber([\"a\", \"b\", \"c\", \"d\"])\n"

_VOTED_TESTS = (
    # b1: the second consecutive miss still counts in THAT vote's denominator
    _t("test_second_miss_still_counts",
       _VOTE_SETUP +
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", False); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"d\", False)\n"
       "    got = ch.close()\n"
       "    assert got is False, f\"c's second miss is effective at closing: 2*2 > 4 fails, got {got}\""),
    # b2: reactivate restarts the streak from zero
    _t("test_reactivate_fresh_streak",
       _VOTE_SETUP +
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.close()\n"
       "    assert ch.active_count() == 2\n"
       "    ch.reactivate(\"c\")\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.close()\n"
       "    assert ch.active_count() == 3, f\"one miss after reactivation must not expel, got {ch.active_count()}\""),
    # b1 x margin: the flipped denominator flips the outcome (same flow as
    # test_second_miss_still_counts read through the outcomes log)
    _t("test_margin_log_records_farewell_denominator",
       _VOTE_SETUP +
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", False); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"d\", False)\n"
       "    ch.close()\n"
       "    assert ch.outcomes == [False, False], f\"got {ch.outcomes}\""),
    # -- P2P below: identical on fixed and buggy ------------------------------
    _t("test_departed_member_frees_next_vote",
       _VOTE_SETUP +
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", False); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"d\", False); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"d\", False)\n"
       "    got = ch.close()\n"
       "    assert got is True, f\"c departed: 2*2 > 3 passes, got {got}\""),
    _t("test_first_miss_never_penalizes",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True)\n"
       "    assert ch.close() is True and ch.active_count() == 3"),
    _t("test_tie_fails",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\", \"d\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"c\", False); ch.cast(\"d\", False)\n"
       "    assert ch.close() is False"),
    _t("test_any_ballot_resets_streak",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"c\", False); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.close()\n"
       "    assert ch.active_count() == 2, f\"c's no-ballot in vote 2 resets its streak, got {ch.active_count()}\""),
    _t("test_inactive_cannot_vote",
       _VOTE_SETUP +
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.close()\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.close()\n"
       "    ch.open_vote()\n"
       "    try:\n"
       "        ch.cast(\"c\", True)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"inactive members must not vote\")"),
    _t("test_cast_overwrites",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"a\", False); ch.cast(\"b\", False); ch.cast(\"c\", False)\n"
       "    assert ch.close() is False"),
    _t("test_unknown_member_raises",
       "    ch = solution.Chamber([\"a\"])\n"
       "    ch.open_vote()\n"
       "    try:\n"
       "        ch.cast(\"zz\", True)\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
    _t("test_double_close_raises",
       "    ch = solution.Chamber([\"a\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.close()\n"
       "    try:\n"
       "        ch.close()\n"
       "    except ValueError:\n"
       "        return\n"
       "    raise AssertionError(\"expected ValueError\")"),
)

_VOTED_PUBLIC = (
    _t("test_public_majority_pass",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", True); ch.cast(\"c\", False)\n"
       "    assert ch.close() is True"),
    _t("test_public_majority_fail",
       "    ch = solution.Chamber([\"a\", \"b\", \"c\"])\n"
       "    ch.open_vote(); ch.cast(\"a\", True); ch.cast(\"b\", False); ch.cast(\"c\", False)\n"
       "    assert ch.close() is False"),
)

_VOTED_SKETCH = (
    "close(): tally yes_votes * 2 > len(active) BEFORE applying attendance "
    "updates (the second consecutive miss is effective at the closing, so "
    "the departing member still counts in that vote's denominator). "
    "reactivate(): reset the member's miss streak to 0 alongside restoring "
    "membership."
)

_VOTED_CHOICES = (
    "close() applies attendance before tallying, so the second consecutive miss removes the member from that vote's own denominator.",
    "reactivate() fails to reset the miss streak, so a reactivated member is expelled again after a single absence.",
    "The majority rule counts inactive members in the denominator; once membership is updated first, every outcome is correct.",
    "Two faults: close() tallies after applying attendance (the second miss should still count in that vote's denominator), and reactivate() keeps the old miss streak instead of resetting it.",
)


def _task(task_id: str, title: str, fixed: str, buggy: str, tests, public, sketch: str, choices: tuple[str, ...], answer: int) -> DebugTask:
    from hintbench.envs.debug import run_tests

    outcomes = run_tests(buggy, tests)
    f2p = tuple(n for n, o in outcomes.items() if not o["passed"])
    p2p = tuple(n for n, o in outcomes.items() if o["passed"])
    assert f2p and p2p, f"{task_id}: f2p={f2p} p2p={p2p}"
    public_bad = [n for n, o in run_tests(buggy, public).items() if not o["passed"]]
    assert not public_bad, f"{task_id}: public tests must be green on buggy, got {public_bad}"
    fixed_bad = [n for n, o in run_tests(fixed, tests + public).items() if not o["passed"]]
    assert not fixed_bad, f"{task_id}: fixed must be fully green, got {fixed_bad}"
    return DebugTask(
        task_id=task_id,
        title=title,
        buggy_source=buggy,
        fixed_source=fixed,
        wrong_variants=(),
        public_tests=public,
        hidden_tests=tests,
        f2p=f2p,
        p2p=p2p,
        fault_region=changed_region(fixed, buggy),
        fix_sketch=sketch,
        fault_choices=choices,
        fault_answer=answer,
    )


EMERGENT_TASKS: tuple[DebugTask, ...] = (
    _task(
        "dbg_em_credit_accrual",
        "creditd: interest accrual base × multi-day compounding",
        _CREDIT_FIXED,
        _CREDIT_BUGGY,
        _CREDIT_TESTS,
        _CREDIT_PUBLIC,
        _CREDIT_SKETCH,
        _CREDIT_CHOICES,
        1,
    ),
    _task(
        "dbg_em_chamber_quorum",
        "voted: quorum denominator × auto-inactivation timing",
        _VOTED_FIXED,
        _VOTED_BUGGY,
        _VOTED_TESTS,
        _VOTED_PUBLIC,
        _VOTED_SKETCH,
        _VOTED_CHOICES,
        4,
    ),
)
