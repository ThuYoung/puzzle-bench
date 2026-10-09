"""Track B2: stateful-system tasks with hand-planted non-local bugs.

Mutation-generated bugs are local visual anomalies — a frontier model spots
them on a full read of a small file. These systems instead plant bugs that
look correct line-by-line:

  - ABSENCE bugs (a line that should exist but doesn't: version bump, dict
    removal) — readers are far worse at noticing missing lines than wrong ones
  - ALTERNATIVE-SEMANTICS bugs (both forms defensible; wrong only under a
    specific operation sequence)
  - STATE-FLOW bugs (fault in one method, symptom observed through another)

Hand-authored, not mutated: fault_region is computed from the fixed/buggy
diff, fix_sketch is the planted fault's description. Public tests cover basic
flows only and are GREEN on the buggy source; hidden tests carry the
triggering sequences. Test convention matches tasks_debug: tests define
same-named functions, call solution.<name>, key asserts carry f-strings.
"""

from __future__ import annotations

from hintbench.mutate import changed_region
from hintbench.seeds_debug import _t
from hintbench.tasks_debug import DebugTask

# -- S1: VersionedTextBuffer -----------------------------------------------------

_BUFFER_FIXED = '''class VersionedTextBuffer:
    """Text buffer with undo/redo and per-version snapshots.

    - insert(pos, text), delete(pos, length), replace(pos, length, text)
      edit the text.
    - undo() / redo() walk the history and return False when there is
      nothing to undo/redo.
    - The version number identifies the current text state.
    - snapshot() returns the text of the current state, cached per version.
    The initial version is 1."""

    def __init__(self, initial: str = "") -> None:
        self._text = initial
        self._version = 1
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._snapshots: dict[int, str] = {}

    def _record(self) -> None:
        self._undo.append(self._text)
        self._redo.clear()

    @property
    def version(self) -> int:
        return self._version

    def text(self) -> str:
        return self._text

    def insert(self, pos: int, text: str) -> None:
        self._record()
        self._text = self._text[:pos] + text + self._text[pos:]
        self._version += 1

    def delete(self, pos: int, length: int) -> None:
        self._record()
        self._text = self._text[:pos] + self._text[pos + length:]
        self._version += 1

    def replace(self, pos: int, length: int, text: str) -> None:
        self._record()
        self._text = self._text[:pos] + text + self._text[pos + length:]
        self._version += 1

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._text)
        self._text = self._undo.pop()
        self._version += 1
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._text)
        self._text = self._redo.pop()
        self._version += 1
        return True

    def snapshot(self) -> str:
        if self._version not in self._snapshots:
            self._snapshots[self._version] = self._text
        return self._snapshots[self._version]
'''

# absence bug: replace() forgets the version bump -> stale snapshot cache hits
_BUFFER_BUGGY = _BUFFER_FIXED.replace(
    """    def replace(self, pos: int, length: int, text: str) -> None:
        self._record()
        self._text = self._text[:pos] + text + self._text[pos + length:]
        self._version += 1
""",
    """    def replace(self, pos: int, length: int, text: str) -> None:
        self._record()
        self._text = self._text[:pos] + text + self._text[pos + length:]
""",
)

_BUFFER_TESTS = (
    _t("test_basic_edits",
       "    b = solution.VersionedTextBuffer()\n"
       "    b.insert(0, 'hello')\n"
       "    b.delete(0, 1)\n"
       "    b.replace(0, 2, 'EL')\n"
       "    got = b.text()\n"
       "    assert got == 'ELlo', f\"got {got!r}\""),
    _t("test_undo_redo",
       "    b = solution.VersionedTextBuffer('ab')\n"
       "    b.insert(2, 'cd')\n"
       "    assert b.undo() and b.text() == 'ab'\n"
       "    assert b.redo() and b.text() == 'abcd'"),
    _t("test_version_counts_every_edit",
       "    b = solution.VersionedTextBuffer()\n"
       "    b.insert(0, 'x')\n"
       "    b.replace(0, 1, 'y')\n"
       "    got = b.version\n"
       "    assert got == 3, f\"got {got}  (every edit bumps the version: initial 1, insert 2, replace 3)\""),
    _t("test_snapshot_reflects_current_version",
       "    b = solution.VersionedTextBuffer()\n"
       "    b.insert(0, 'ab')\n"
       "    first = b.snapshot()\n"
       "    b.replace(0, 1, 'x')\n"
       "    got = b.snapshot()\n"
       "    assert got == 'xb', f\"got {got!r}  (snapshot must reflect the CURRENT version, not a stale cache)\""),
    _t("test_redo_cleared_on_edit",
       "    b = solution.VersionedTextBuffer()\n"
       "    b.insert(0, 'a')\n"
       "    b.undo()\n"
       "    b.insert(0, 'b')\n"
       "    assert b.redo() is False"),
    _t("test_undo_then_snapshot",
       "    b = solution.VersionedTextBuffer('one')\n"
       "    b.delete(0, 1)\n"
       "    b.undo()\n"
       "    got = b.snapshot()\n"
       "    assert got == 'one', f\"got {got!r}\""),
)

# -- S2: Warehouse ---------------------------------------------------------------

_WARE_FIXED = '''class Warehouse:
    """FIFO lot inventory with reservations.

    - restock(sku, qty, lot) appends a lot; lots ship oldest-first.
    - reserve(sku, qty) holds stock and returns a reservation id, or None
      when stock is insufficient. available = on-hand minus held.
    - fulfill(rid) ships a reservation, depleting lots FIFO.
    - cancel(rid) releases a reservation without shipping it.
    - fulfill/cancel on an unknown id return False."""

    def __init__(self) -> None:
        self._lots: dict[str, list[list]] = {}
        self._reservations: dict[int, tuple[str, int]] = {}
        self._next_id = 1

    def restock(self, sku: str, qty: int, lot: str) -> None:
        self._lots.setdefault(sku, []).append([lot, qty])

    def _on_hand(self, sku: str) -> int:
        return sum(qty for _, qty in self._lots.get(sku, []))

    def _held(self, sku: str) -> int:
        return sum(qty for s, qty in self._reservations.values() if s == sku)

    def available(self, sku: str) -> int:
        return self._on_hand(sku) - self._held(sku)

    def reserve(self, sku: str, qty: int) -> int | None:
        if qty > self.available(sku):
            return None
        rid = self._next_id
        self._next_id += 1
        self._reservations[rid] = (sku, qty)
        return rid

    def fulfill(self, rid: int) -> bool:
        if rid not in self._reservations:
            return False
        sku, qty = self._reservations.pop(rid)
        lots = self._lots[sku]
        remaining = qty
        while remaining > 0:
            take = min(remaining, lots[0][1])
            lots[0][1] -= take
            remaining -= take
            if lots[0][1] == 0:
                lots.pop(0)
        return True

    def cancel(self, rid: int) -> bool:
        if rid not in self._reservations:
            return False
        del self._reservations[rid]
        return True
'''

# absence bug: cancel() never removes the reservation -> held stock leaks
_WARE_BUGGY = _WARE_FIXED.replace(
    """    def cancel(self, rid: int) -> bool:
        if rid not in self._reservations:
            return False
        del self._reservations[rid]
        return True
""",
    """    def cancel(self, rid: int) -> bool:
        if rid not in self._reservations:
            return False
        return True
""",
)

_WARE_TESTS = (
    _t("test_basic_flow",
       "    w = solution.Warehouse()\n"
       "    w.restock('A', 10, 'L1')\n"
       "    rid = w.reserve('A', 4)\n"
       "    assert w.available('A') == 6\n"
       "    assert w.fulfill(rid)\n"
       "    got = w.available('A')\n"
       "    assert got == 6, f\"got {got}\""),
    _t("test_reserve_insufficient",
       "    w = solution.Warehouse()\n"
       "    w.restock('A', 3, 'L1')\n"
       "    assert w.reserve('A', 4) is None"),
    _t("test_cancel_restores_availability",
       "    w = solution.Warehouse()\n"
       "    w.restock('A', 5, 'L1')\n"
       "    rid = w.reserve('A', 5)\n"
       "    assert w.cancel(rid)\n"
       "    got = w.available('A')\n"
       "    assert got == 5, f\"got {got}  (cancel releases the hold WITHOUT shipping)\""),
    _t("test_double_cancel_is_unknown",
       "    w = solution.Warehouse()\n"
       "    w.restock('A', 5, 'L1')\n"
       "    rid = w.reserve('A', 2)\n"
       "    assert w.cancel(rid)\n"
       "    got = w.cancel(rid)\n"
       "    assert got is False, f\"got {got}  (a cancelled id is gone; second cancel returns False)\""),
    _t("test_fifo_lot_order",
       "    w = solution.Warehouse()\n"
       "    w.restock('A', 5, 'L1')\n"
       "    w.restock('A', 5, 'L2')\n"
       "    rid = w.reserve('A', 7)\n"
       "    w.fulfill(rid)\n"
       "    got = w.available('A')\n"
       "    assert got == 3, f\"got {got}\""),
    _t("test_cancel_unknown_id",
       "    w = solution.Warehouse()\n"
       "    assert w.cancel(999) is False\n"
       "    assert w.fulfill(999) is False"),
)

# -- S3: Scheduler ---------------------------------------------------------------

_SCHED_FIXED = '''class Scheduler:
    """Recurring events on discrete ticks.

    - schedule(name, every, start): the event first fires at `start`.
    - reschedule(name, new_next) moves only the next fire time; the interval
      is preserved.
    - cancel(name) removes the event entirely.
    - tick(now) fires every event due at `now` (in the order the events were
      first scheduled) and sets that event's next fire to `every` ticks
      after this tick."""

    def __init__(self) -> None:
        self._events: dict[str, dict] = {}
        self._order: list[str] = []

    def schedule(self, name: str, every: int, start: int) -> None:
        if name not in self._events:
            self._order.append(name)
        self._events[name] = {"every": every, "next": start}

    def cancel(self, name: str) -> bool:
        if name not in self._events:
            return False
        del self._events[name]
        self._order.remove(name)
        return True

    def reschedule(self, name: str, new_next: int) -> bool:
        if name not in self._events:
            return False
        self._events[name]["next"] = new_next
        return True

    def tick(self, now: int) -> list[str]:
        fired = []
        for name in self._order:
            ev = self._events.get(name)
            if ev is None or ev["next"] > now:
                continue
            fired.append(name)
            ev["next"] = now + ev["every"]
        return fired
'''

# alternative-semantics bug: relative advance (+= every) instead of rebasing on
# the tick -> catch-up bursts after sparse ticks
_SCHED_BUGGY = _SCHED_FIXED.replace(
    '            ev["next"] = now + ev["every"]\n',
    '            ev["next"] += ev["every"]\n',
)

_SCHED_TESTS = (
    _t("test_basic_fire",
       "    s = solution.Scheduler()\n"
       "    s.schedule('a', 2, 1)\n"
       "    assert s.tick(1) == ['a']\n"
       "    assert s.tick(2) == []\n"
       "    got = s.tick(3)\n"
       "    assert got == ['a'], f\"got {got}\""),
    _t("test_sparse_ticks_no_catchup",
       "    s = solution.Scheduler()\n"
       "    s.schedule('a', 2, 1)\n"
       "    s.tick(1)\n"
       "    assert s.tick(10) == ['a']\n"
       "    got = s.tick(11)\n"
       "    assert got == [], f\"got {got}  (after firing at t=10 next is 12: sparse ticks never catch up)\""),
    _t("test_next_rebased_on_tick",
       "    s = solution.Scheduler()\n"
       "    s.schedule('a', 2, 1)\n"
       "    s.tick(1)\n"
       "    s.tick(10)\n"
       "    s.tick(11)\n"
       "    got = s.tick(12)\n"
       "    assert got == ['a'], f\"got {got}  (next = 10 + 2)\""),
    _t("test_reschedule_preserves_interval",
       "    s = solution.Scheduler()\n"
       "    s.schedule('a', 3, 1)\n"
       "    s.reschedule('a', 5)\n"
       "    assert s.tick(4) == []\n"
       "    assert s.tick(5) == ['a']\n"
       "    got = s.tick(8)\n"
       "    assert got == ['a'], f\"got {got}  (interval preserved: 5 + 3)\""),
    _t("test_cancel",
       "    s = solution.Scheduler()\n"
       "    s.schedule('a', 1, 1)\n"
       "    assert s.cancel('a')\n"
       "    assert s.tick(1) == []\n"
       "    assert s.cancel('a') is False"),
    _t("test_registration_order",
       "    s = solution.Scheduler()\n"
       "    s.schedule('b', 1, 1)\n"
       "    s.schedule('a', 1, 1)\n"
       "    got = s.tick(1)\n"
       "    assert got == ['b', 'a'], f\"got {got}\""),
)

# -- S4: Ledger ------------------------------------------------------------------

_LEDGER_FIXED = '''class Ledger:
    """Accounts with holds and settlement.

    - open(name, balance) creates an account.
    - hold(acc, amount) freezes funds and returns a hold id (None when the
      available balance is insufficient). available = balance - active holds.
    - release(hid) cancels a hold without settling it.
    - settle(hid) converts a hold into a real debit.
    - transfer(src, dst, amount) moves available funds; returns False (and
      moves nothing) when src cannot cover it."""

    def __init__(self) -> None:
        self._balance: dict[str, int] = {}
        self._holds: dict[int, tuple[str, int]] = {}
        self._next_id = 1

    def open(self, name: str, balance: int) -> None:
        self._balance[name] = balance

    def balance(self, name: str) -> int:
        return self._balance[name]

    def available(self, name: str) -> int:
        held = sum(amt for acc, amt in self._holds.values() if acc == name)
        return self._balance[name] - held

    def hold(self, name: str, amount: int) -> int | None:
        if amount > self.available(name):
            return None
        hid = self._next_id
        self._next_id += 1
        self._holds[hid] = (name, amount)
        return hid

    def release(self, hid: int) -> bool:
        if hid not in self._holds:
            return False
        del self._holds[hid]
        return True

    def settle(self, hid: int) -> bool:
        if hid not in self._holds:
            return False
        name, amount = self._holds.pop(hid)
        self._balance[name] -= amount
        return True

    def transfer(self, src: str, dst: str, amount: int) -> bool:
        if amount > self.available(src):
            return False
        self._balance[src] -= amount
        self._balance[dst] += amount
        return True
'''

# commission bug: release() credits the balance (hold semantics confusion)
_LEDGER_BUGGY = _LEDGER_FIXED.replace(
    """    def release(self, hid: int) -> bool:
        if hid not in self._holds:
            return False
        del self._holds[hid]
        return True
""",
    """    def release(self, hid: int) -> bool:
        if hid not in self._holds:
            return False
        name, amount = self._holds.pop(hid)
        self._balance[name] += amount
        return True
""",
)

_LEDGER_TESTS = (
    _t("test_hold_and_settle",
       "    l = solution.Ledger()\n"
       "    l.open('a', 100)\n"
       "    hid = l.hold('a', 30)\n"
       "    assert l.available('a') == 70\n"
       "    assert l.settle(hid)\n"
       "    got = (l.balance('a'), l.available('a'))\n"
       "    assert got == (70, 70), f\"got {got}\""),
    _t("test_release_restores_without_credit",
       "    l = solution.Ledger()\n"
       "    l.open('a', 100)\n"
       "    hid = l.hold('a', 30)\n"
       "    assert l.release(hid)\n"
       "    got = (l.available('a'), l.balance('a'))\n"
       "    assert got == (100, 100), f\"got {got}  (release restores availability but NEVER credits the balance)\""),
    _t("test_transfer_uses_available",
       "    l = solution.Ledger()\n"
       "    l.open('a', 100)\n"
       "    l.open('b', 0)\n"
       "    l.hold('a', 80)\n"
       "    assert l.transfer('a', 'b', 30) is False\n"
       "    assert l.transfer('a', 'b', 20)\n"
       "    got = l.balance('b')\n"
       "    assert got == 20, f\"got {got}\""),
    _t("test_release_then_new_cycle",
       "    l = solution.Ledger()\n"
       "    l.open('a', 100)\n"
       "    l.release(l.hold('a', 30))\n"
       "    hid = l.hold('a', 50)\n"
       "    l.settle(hid)\n"
       "    got = l.balance('a')\n"
       "    assert got == 50, f\"got {got}  (100 - 50; the released 30 was never real money)\""),
    _t("test_unknown_hold",
       "    l = solution.Ledger()\n"
       "    assert l.release(999) is False\n"
       "    assert l.settle(999) is False"),
    _t("test_hold_insufficient",
       "    l = solution.Ledger()\n"
       "    l.open('a', 10)\n"
       "    assert l.hold('a', 11) is None"),
)

# -- S5: DocumentHistory ---------------------------------------------------------

_HISTORY_FIXED = '''class DocumentHistory:
    """Line-based document with versioned history.

    - The document is a list of lines; set_lines(lines) replaces the content
      and creates a new version (versions start at 0).
    - history(v) returns the lines of version v; latest() returns the
      current lines. Both return independent snapshots: mutating a returned
      list must never change what is stored.
    - diff_count(v) reports how many lines differ between version v and the
      current content (by position; length differences count too)."""

    def __init__(self, lines: list[str]) -> None:
        self._versions: list[list[str]] = [list(lines)]

    def set_lines(self, lines: list[str]) -> None:
        self._versions.append(list(lines))

    @property
    def version(self) -> int:
        return len(self._versions) - 1

    def history(self, v: int) -> list[str]:
        return list(self._versions[v])

    def latest(self) -> list[str]:
        return list(self._versions[-1])

    def diff_count(self, v: int) -> int:
        old = self._versions[v]
        cur = self._versions[-1]
        n = max(len(old), len(cur))
        return sum(
            1 for i in range(n)
            if i >= len(old) or i >= len(cur) or old[i] != cur[i]
        )
'''

# aliasing bug: history()/latest() hand out the internal list — every returned
# "snapshot" is a live view; mutating it rewrites the stored history
_HISTORY_BUGGY = _HISTORY_FIXED.replace(
    "    def history(self, v: int) -> list[str]:\n        return list(self._versions[v])\n",
    "    def history(self, v: int) -> list[str]:\n        return self._versions[v]\n",
).replace(
    "    def latest(self) -> list[str]:\n        return list(self._versions[-1])\n",
    "    def latest(self) -> list[str]:\n        return self._versions[-1]\n",
)

_HISTORY_TESTS = (
    _t("test_versions",
       "    d = solution.DocumentHistory(['a', 'b'])\n"
       "    d.set_lines(['a', 'c'])\n"
       "    assert d.version == 1\n"
       "    got = d.diff_count(0)\n"
       "    assert got == 1, f\"got {got}\""),
    _t("test_history_snapshot_independent",
       "    d = solution.DocumentHistory(['a', 'b'])\n"
       "    h = d.history(0)\n"
       "    h.append('x')\n"
       "    got = d.history(0)\n"
       "    assert got == ['a', 'b'], f\"got {got}  (a returned snapshot must never change what is stored)\""),
    _t("test_latest_snapshot_independent",
       "    d = solution.DocumentHistory(['a'])\n"
       "    cur = d.latest()\n"
       "    cur[0] = 'MUTATED'\n"
       "    got = d.latest()\n"
       "    assert got == ['a'], f\"got {got}  (latest() must return an independent snapshot)\""),
    _t("test_mutation_does_not_corrupt_diff",
       "    d = solution.DocumentHistory(['a', 'b'])\n"
       "    d.set_lines(['a', 'c'])\n"
       "    h = d.history(0)\n"
       "    h[1] = 'MUTATED'\n"
       "    got = d.diff_count(0)\n"
       "    assert got == 1, f\"got {got}  (diff must use the stored version, not an alias)\""),
    _t("test_diff_length_difference",
       "    d = solution.DocumentHistory(['a'])\n"
       "    d.set_lines(['a', 'b', 'c'])\n"
       "    got = d.diff_count(0)\n"
       "    assert got == 2, f\"got {got}\""),
    _t("test_constructor_isolation",
       "    src = ['a']\n"
       "    d = solution.DocumentHistory(src)\n"
       "    src.append('b')\n"
       "    got = d.latest()\n"
       "    assert got == ['a'], f\"got {got}\""),
)

# -- S6: ConfigMerger ------------------------------------------------------------

_CONFIG_FIXED = '''class ConfigMerger:
    """Layered configuration: defaults plus overrides, merged per section.

    - set_default(section, key, value) / set_override(section, key, value)
      store values in their layer.
    - merged(section) returns defaults updated by overrides for that
      section. The returned dict is detached: mutating it must not change
      either stored layer.
    - sections(name) lists the keys of a layer; unknown sections merge to an
      empty dict."""

    def __init__(self) -> None:
        self._defaults: dict[str, dict[str, str]] = {}
        self._overrides: dict[str, dict[str, str]] = {}

    def set_default(self, section: str, key: str, value: str) -> None:
        self._defaults.setdefault(section, {})[key] = value

    def set_override(self, section: str, key: str, value: str) -> None:
        self._overrides.setdefault(section, {})[key] = value

    def merged(self, section: str) -> dict[str, str]:
        out = dict(self._defaults.get(section, {}))
        out.update(self._overrides.get(section, {}))
        return out

    def sections(self, layer: str) -> list[str]:
        store = self._defaults if layer == "defaults" else self._overrides
        return sorted(store)
'''

# aliasing bug: merged() reuses the stored defaults dict when it exists —
# updating the result writes straight into the defaults layer
_CONFIG_BUGGY = _CONFIG_FIXED.replace(
    "        out = dict(self._defaults.get(section, {}))\n",
    "        out = self._defaults.get(section, {})\n",
)

_CONFIG_TESTS = (
    _t("test_merge_layers",
       "    c = solution.ConfigMerger()\n"
       "    c.set_default('db', 'host', 'localhost')\n"
       "    c.set_default('db', 'port', '5432')\n"
       "    c.set_override('db', 'host', 'prod')\n"
       "    got = c.merged('db')\n"
       "    assert got == {'host': 'prod', 'port': '5432'}, f\"got {got}\""),
    _t("test_merged_result_detached",
       "    c = solution.ConfigMerger()\n"
       "    c.set_default('db', 'host', 'localhost')\n"
       "    m = c.merged('db')\n"
       "    m['host'] = 'MUTATED'\n"
       "    m['injected'] = 'x'\n"
       "    got = c.merged('db')\n"
       "    assert got == {'host': 'localhost'}, f\"got {got}  (mutating a merged result must not touch stored layers)\""),
    _t("test_mutation_does_not_leak_across_calls",
       "    c = solution.ConfigMerger()\n"
       "    c.set_default('cache', 'ttl', '60')\n"
       "    first = c.merged('cache')\n"
       "    first['ttl'] = '0'\n"
       "    second = c.merged('cache')\n"
       "    got = second['ttl']\n"
       "    assert got == '60', f\"got {got!r}\""),
    _t("test_unknown_section_empty",
       "    c = solution.ConfigMerger()\n"
       "    assert c.merged('nope') == {}"),
    _t("test_sections_sorted",
       "    c = solution.ConfigMerger()\n"
       "    c.set_default('b', 'k', '1')\n"
       "    c.set_default('a', 'k', '1')\n"
       "    got = c.sections('defaults')\n"
       "    assert got == ['a', 'b'], f\"got {got}\""),
)

# -- S7: RankTable (anti-idiom tie order) -----------------------------------------

_RANK_FIXED = '''def rank_table(entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Competition ranking. entries are (name, score) in submission order.

    Return (name, rank) rows sorted by score descending. Equal scores share
    one rank and the next rank skips (1, 2, 2, 4). Within a tie, the LATER
    submission is listed first."""
    order = sorted(range(len(entries)), key=lambda i: (-entries[i][1], -i))
    rows = []
    prev_score = None
    rank = 0
    for pos, i in enumerate(order):
        score = entries[i][1]
        if score != prev_score:
            rank = pos + 1
            prev_score = score
        rows.append((entries[i][0], rank))
    return rows
'''

# idiom bug: ties in submission order (stable sort instinct) instead of
# later-submission-first as documented
_RANK_BUGGY = _RANK_FIXED.replace(
    "key=lambda i: (-entries[i][1], -i)",
    "key=lambda i: (-entries[i][1], i)",
)

_RANK_TESTS = (
    _t("test_distinct_scores",
       "    got = solution.rank_table([('a', 10), ('b', 30), ('c', 20)])\n"
       "    assert got == [('b', 1), ('c', 2), ('a', 3)], f\"got {got}\""),
    _t("test_tie_later_first",
       "    got = solution.rank_table([('a', 10), ('b', 20), ('c', 20), ('d', 5)])\n"
       "    assert got == [('c', 1), ('b', 1), ('a', 3), ('d', 4)], f\"got {got}  (within a tie the LATER submission is listed first)\""),
    _t("test_rank_skip_after_tie",
       "    got = solution.rank_table([('a', 5), ('b', 5), ('c', 5), ('d', 1)])\n"
       "    assert got[-1] == ('d', 4), f\"got {got}\""),
    _t("test_three_way_tie_order",
       "    got = solution.rank_table([('x', 7), ('y', 7), ('z', 7)])\n"
       "    assert [name for name, _ in got] == ['z', 'y', 'x'], f\"got {got}\""),
    _t("test_empty", "    assert solution.rank_table([]) == []"),
)

# -- S8: Rebates (anti-idiom rounding) ---------------------------------------------

_REBATE_FIXED = '''def rebates(prices_cents: list[int]) -> list[int]:
    """15% rebate per price, in integer cents.

    Non-integer rebates round to the nearest cent; a rebate that lands on an
    exact half cent rounds DOWN (37.5 -> 37, 52.5 -> 52)."""
    out = []
    for price in prices_cents:
        num = price * 15
        q, r = divmod(num, 100)
        if 2 * r > 100:
            q += 1
        out.append(q)
    return out
'''

# idiom bug: half rounds UP (the common nearest-integer instinct) instead of
# the documented half-down
_REBATE_BUGGY = _REBATE_FIXED.replace(
    "        if 2 * r > 100:\n",
    "        if 2 * r >= 100:\n",
)

_REBATE_TESTS = (
    _t("test_whole_rebates",
       "    got = solution.rebates([100, 200])\n"
       "    assert got == [15, 30], f\"got {got}\""),
    _t("test_exact_half_rounds_down",
       "    got = solution.rebates([250])\n"
       "    assert got == [37], f\"got {got}  (37.5 rounds DOWN to 37)\""),
    _t("test_second_half_case",
       "    got = solution.rebates([350])\n"
       "    assert got == [52], f\"got {got}  (52.5 rounds DOWN to 52)\""),
    _t("test_above_half_rounds_up",
       "    got = solution.rebates([251])\n"
       "    assert got == [38], f\"got {got}  (37.65 rounds to 38)\""),
    _t("test_below_half_rounds_down",
       "    got = solution.rebates([249])\n"
       "    assert got == [37], f\"got {got}  (37.35 rounds to 37)\""),
    _t("test_empty", "    assert solution.rebates([]) == []"),
)

# -- S9: slice_window (inclusive stop, anti-slicing idiom) -------------------------

_WINDOW_FIXED = '''def slice_window(xs: list[int], start: int, stop: int) -> list[int]:
    """Window of xs from index `start` to index `stop`.

    Both bounds are INCLUSIVE (unlike Python slicing): slice_window(x, 1, 3)
    returns x[1], x[2], x[3]. An empty window results when stop < start."""
    return [xs[i] for i in range(start, stop + 1)]
'''

_WINDOW_BUGGY = _WINDOW_FIXED.replace(
    "range(start, stop + 1)",
    "range(start, stop)",
)

_WINDOW_TESTS = (
    _t("test_middle",
       "    got = solution.slice_window([10, 20, 30, 40, 50], 1, 3)\n"
       "    assert got == [20, 30, 40], f\"got {got}  (stop is INCLUSIVE)\""),
    _t("test_single_element",
       "    got = solution.slice_window([10, 20, 30], 2, 2)\n"
       "    assert got == [30], f\"got {got}  (start == stop gives one element, not empty)\""),
    _t("test_full_span",
       "    got = solution.slice_window([1, 2, 3], 0, 2)\n"
       "    assert got == [1, 2, 3], f\"got {got}\""),
    _t("test_empty_when_inverted",
       "    assert solution.slice_window([1, 2, 3], 2, 1) == []"),
    _t("test_last_index",
       "    got = solution.slice_window([7, 8, 9], 1, 2)\n"
       "    assert got == [8, 9], f\"got {got}\""),
)

# -- S10: merge tie order (second list wins ties, anti-merge idiom) -----------------

_MERGETIE_FIXED = '''def merge_records(a: list[tuple[int, str]], b: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Merge two lists of (key, payload), each ascending by key, into one
    ascending list.

    When the two heads have EQUAL keys, the element from b is taken first."""
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        if b[j][0] <= a[i][0]:
            out.append(b[j])
            j += 1
        else:
            out.append(a[i])
            i += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out
'''

_MERGETIE_BUGGY = _MERGETIE_FIXED.replace(
    "        if b[j][0] <= a[i][0]:\n",
    "        if a[i][0] <= b[j][0]:\n",
).replace(
    """            out.append(b[j])
            j += 1
        else:
            out.append(a[i])
            i += 1""",
    """            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1""",
)

_MERGETIE_TESTS = (
    _t("test_interleave",
       "    got = solution.merge_records([(1, 'a1'), (4, 'a4')], [(2, 'b2'), (3, 'b3')])\n"
       "    assert got == [(1, 'a1'), (2, 'b2'), (3, 'b3'), (4, 'a4')], f\"got {got}\""),
    _t("test_equal_keys_b_first",
       "    got = solution.merge_records([(1, 'A')], [(1, 'B')])\n"
       "    assert got == [(1, 'B'), (1, 'A')], f\"got {got}  (equal keys: b's element is taken first)\""),
    _t("test_tie_run_b_drains_first",
       "    got = solution.merge_records([(1, 'A1'), (1, 'A2')], [(1, 'B')])\n"
       "    assert got == [(1, 'B'), (1, 'A1'), (1, 'A2')], f\"got {got}\""),
    _t("test_one_empty",
       "    assert solution.merge_records([], [(2, 'b')]) == [(2, 'b')]\n"
       "    assert solution.merge_records([(2, 'a')], []) == [(2, 'a')]"),
    _t("test_strict_order_kept",
       "    got = solution.merge_records([(1, 'a')], [(3, 'b'), (4, 'c')])\n"
       "    assert got == [(1, 'a'), (3, 'b'), (4, 'c')], f\"got {got}\""),
)

# -- S11: split collapse (empty fields dropped, anti-str.split idiom) ---------------

_SPLIT_FIXED = '''def split_fields(s: str) -> list[str]:
    """Split s on commas. Consecutive delimiters COLLAPSE: they never
    produce empty fields, and leading/trailing commas are ignored."""
    return [field for field in s.split(",") if field != ""]
'''

_SPLIT_BUGGY = _SPLIT_FIXED.replace(
    'return [field for field in s.split(",") if field != ""]',
    'return s.split(",")',
)

_SPLIT_TESTS = (
    _t("test_basic",
       "    got = solution.split_fields('a,b,c')\n"
       "    assert got == ['a', 'b', 'c'], f\"got {got}\""),
    _t("test_consecutive_collapse",
       "    got = solution.split_fields('a,,b')\n"
       "    assert got == ['a', 'b'], f\"got {got}  (consecutive delimiters collapse: no empty fields)\""),
    _t("test_edges_ignored",
       "    got = solution.split_fields(',a,')\n"
       "    assert got == ['a'], f\"got {got}\""),
    _t("test_all_delimiters",
       "    got = solution.split_fields(',,,')\n"
       "    assert got == [], f\"got {got}\""),
    _t("test_empty_string",
       "    assert solution.split_fields('') == []"),
)

# -- S12: clamp wrap (out-of-range wraps, anti-min/max idiom) ------------------------

_WRAP_FIXED = '''def clamp_wrap(x: int, lo: int, hi: int) -> int:
    """Confine x to the inclusive range [lo, hi].

    Out-of-range values do NOT clamp to the nearest edge: they WRAP around
    to the other side, repeating the range as a cycle (hi + 1 -> lo)."""
    span = hi - lo + 1
    return (x - lo) % span + lo
'''

_WRAP_BUGGY = _WRAP_FIXED.replace(
    """    span = hi - lo + 1
    return (x - lo) % span + lo""",
    """    return min(max(x, lo), hi)""",
)

_WRAP_TESTS = (
    _t("test_inside",
       "    got = solution.clamp_wrap(5, 1, 10)\n"
       "    assert got == 5, f\"got {got}\""),
    _t("test_above_wraps_to_low",
       "    got = solution.clamp_wrap(11, 1, 10)\n"
       "    assert got == 1, f\"got {got}  (hi + 1 wraps to lo, not clamps to hi)\""),
    _t("test_below_wraps_to_high",
       "    got = solution.clamp_wrap(0, 1, 10)\n"
       "    assert got == 10, f\"got {got}  (lo - 1 wraps to hi)\""),
    _t("test_multiple_cycles",
       "    got = solution.clamp_wrap(23, 1, 10)\n"
       "    assert got == 3, f\"got {got}\""),
    _t("test_edges",
       "    assert solution.clamp_wrap(1, 1, 10) == 1\n"
       "    assert solution.clamp_wrap(10, 1, 10) == 10"),
)

# -- S13: div_trunc (toward zero, anti-floor-division idiom) -------------------------

_DIV_FIXED = '''def div_trunc(a: int, b: int) -> int:
    """Integer division of a by b (b != 0).

    The quotient truncates TOWARD ZERO (C-style), which differs from floor
    division for negative operands: div_trunc(-7, 2) is -3, not -4."""
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q
'''

_DIV_BUGGY = _DIV_FIXED.replace(
    """    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return q""",
    """    return a // b""",
)

_DIV_TESTS = (
    _t("test_positive",
       "    got = solution.div_trunc(7, 2)\n"
       "    assert got == 3, f\"got {got}\""),
    _t("test_negative_numerator",
       "    got = solution.div_trunc(-7, 2)\n"
       "    assert got == -3, f\"got {got}  (truncates TOWARD ZERO: -3.5 -> -3, not -4)\""),
    _t("test_negative_denominator",
       "    got = solution.div_trunc(7, -2)\n"
       "    assert got == -3, f\"got {got}\""),
    _t("test_both_negative",
       "    got = solution.div_trunc(-7, -2)\n"
       "    assert got == 3, f\"got {got}\""),
    _t("test_exact",
       "    assert solution.div_trunc(-6, 3) == -2"),
)

# -- S14: top_percent (count rounds UP, anti-truncation idiom) ------------------------

_PERCENT_FIXED = '''def top_percent(scores: list[int], percent: int) -> list[int]:
    """The top `percent`% of scores (0 < percent <= 100), highest first.

    The number of elements taken rounds UP to a whole element: any fraction
    of an element counts as one (top 10% of 25 scores is 3, not 2)."""
    n = len(scores)
    take = (n * percent + 99) // 100
    return sorted(scores, reverse=True)[:take]
'''

_PERCENT_BUGGY = _PERCENT_FIXED.replace(
    "    take = (n * percent + 99) // 100\n",
    "    take = n * percent // 100\n",
)

_PERCENT_TESTS = (
    _t("test_even_split",
       "    got = solution.top_percent([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50)\n"
       "    assert got == [10, 9, 8, 7, 6], f\"got {got}\""),
    _t("test_fraction_rounds_up",
       "    got = solution.top_percent(list(range(1, 26)), 10)\n"
       "    assert len(got) == 3, f\"got {got}  (10% of 25 = 2.5 rounds UP to 3)\""),
    _t("test_small_list_one",
       "    got = solution.top_percent([5, 3, 8], 10)\n"
       "    assert got == [8], f\"got {got}  (0.3 elements still counts as one)\""),
    _t("test_highest_first",
       "    got = solution.top_percent([3, 9, 1, 7], 50)\n"
       "    assert got == [9, 7], f\"got {got}\""),
    _t("test_hundred",
       "    got = solution.top_percent([2, 1], 100)\n"
       "    assert got == [2, 1], f\"got {got}\""),
)

# -- task assembly -----------------------------------------------------------------


def _task(task_id: str, title: str, fixed: str, buggy: str, tests, public, sketch: str, wrong: tuple[str, ...], choices: tuple[str, ...] = (), answer: int = -1) -> DebugTask:
    from hintbench.envs.debug import run_tests

    assert buggy != fixed, task_id
    # real F2P/P2P partition from executing the buggy source; import-time so a
    # bad plant fails loudly instead of producing a mislabeled task
    outcomes = run_tests(buggy, tuple(tests))
    f2p = tuple(n for n, o in outcomes.items() if not o["passed"])
    p2p = tuple(n for n, o in outcomes.items() if o["passed"])
    assert f2p and p2p, f"{task_id}: f2p={f2p} p2p={p2p}"
    public_bad = [n for n, o in run_tests(buggy, tuple(public)).items() if not o["passed"]]
    assert not public_bad, f"{task_id}: public tests must be green on buggy, got {public_bad}"
    assert not choices or 1 <= answer <= len(choices), task_id
    return DebugTask(
        task_id=task_id,
        title=title,
        buggy_source=buggy,
        fixed_source=fixed,
        wrong_variants=wrong,
        public_tests=tuple(public),
        hidden_tests=tuple(tests),
        f2p=f2p,
        p2p=p2p,
        fault_region=changed_region(fixed, buggy),
        fix_sketch=sketch,
        fault_choices=choices,
        fault_answer=answer,
    )


def _none_variant(source: str) -> str:
    first_line = source.splitlines()[0]
    return f"{first_line}\n    pass\n"


SYSTEM_TASKS: tuple[DebugTask, ...] = (
    _task(
        "dbg_sys_buffer_stale_snapshot",
        "VersionedTextBuffer: stale snapshot cache",
        _BUFFER_FIXED,
        _BUFFER_BUGGY,
        _BUFFER_TESTS,
        (_BUFFER_TESTS[0],),
        "replace() does not bump the version, so snapshot() serves a stale cached version.",
        (_none_variant(_BUFFER_FIXED), _BUFFER_FIXED.replace("self._version += 1", "self._version += 2", 1)),
        (
            "undo() restores the text but forgets to bump the version.",
            "replace() does not bump the version, so snapshot() can serve a stale cached text.",
            "snapshot() caches by text length instead of by version.",
            "delete() records the wrong undo state, corrupting later snapshots.",
        ),
        2,
    ),
    _task(
        "dbg_sys_warehouse_cancel_leak",
        "Warehouse: cancel leaks the hold",
        _WARE_FIXED,
        _WARE_BUGGY,
        _WARE_TESTS,
        (_WARE_TESTS[0],),
        "cancel() returns True but never removes the reservation, so held stock stays unavailable.",
        (_none_variant(_WARE_FIXED), _WARE_FIXED.replace("qty > self.available(sku)", "qty >= self.available(sku)")),
        (
            "reserve() double-counts stock when the same SKU is reserved twice.",
            "cancel() raises instead of returning False for unknown reservation ids.",
            "cancel() returns True but never removes the reservation, so its stock stays held.",
            "ship() forgets to decrement the held stock.",
        ),
        3,
    ),
    _task(
        "dbg_sys_scheduler_catchup",
        "Scheduler: catch-up bursts after sparse ticks",
        _SCHED_FIXED,
        _SCHED_BUGGY,
        _SCHED_TESTS,
        (_SCHED_TESTS[0],),
        "tick() advances next by += every instead of rebasing on now + every, causing catch-up fires.",
        (_none_variant(_SCHED_FIXED), _SCHED_FIXED.replace('ev["next"] > now', 'ev["next"] >= now')),
        (
            "after an event fires, tick() advances its next fire by += every instead of rebasing it to now + every as the doc requires.",
            "tick() fires events one tick early (>= instead of >).",
            "after an event fires, tick() rebases its next fire to now + every instead of advancing it by += every as the doc requires.",
            "schedule() drops events whose first fire is in the past.",
        ),
        1,
    ),
    _task(
        "dbg_sys_ledger_release_credit",
        "Ledger: release credits the balance",
        _LEDGER_FIXED,
        _LEDGER_BUGGY,
        _LEDGER_TESTS,
        (_LEDGER_TESTS[0],),
        "release() pops the hold AND credits the balance, minting money out of a cancelled hold.",
        (_none_variant(_LEDGER_FIXED), _LEDGER_FIXED.replace("amount > self.available(src)", "amount >= self.available(src)")),
        (
            "release() forgets to pop the hold, so released amounts stay locked.",
            "hold() credits the balance before the hold is released.",
            "transfer() allows overdrawing by exactly one unit.",
            "release() pops the hold AND credits the balance, minting money out of a cancelled hold.",
        ),
        4,
    ),
    _task(
        "dbg_sys_history_alias",
        "DocumentHistory: snapshots alias internal state",
        _HISTORY_FIXED,
        _HISTORY_BUGGY,
        _HISTORY_TESTS,
        (_HISTORY_TESTS[0],),
        "history()/latest() return the internal list instead of a copy, so caller mutations rewrite stored versions.",
        (_none_variant(_HISTORY_FIXED), _HISTORY_FIXED.replace("i >= len(old) or i >= len(cur) or ", "")),
        (
            "append() stores the caller's list by reference instead of copying it.",
            "history()/latest() hand out the internal list object, so caller edits rewrite stored versions.",
            "latest() returns the oldest stored version instead of the newest.",
            "history() returns the versions in reverse order.",
        ),
        2,
    ),
    _task(
        "dbg_sys_config_alias",
        "ConfigMerger: merged result aliases the defaults layer",
        _CONFIG_FIXED,
        _CONFIG_BUGGY,
        _CONFIG_TESTS,
        (_CONFIG_TESTS[0],),
        "merged() reuses the stored defaults dict instead of copying it, so caller mutations corrupt the layer.",
        (_none_variant(_CONFIG_FIXED), _CONFIG_FIXED.replace("out.update(self._overrides.get(section, {}))", "out.update(self._defaults.get(section, {}))")),
        (
            "merged() applies overrides before defaults, so defaults win.",
            "set_default() mutates the overrides layer instead of defaults.",
            "merged() reuses the stored defaults dict, so mutating the returned dict corrupts the layer.",
            "merged() copies the overrides layer instead of the defaults layer.",
        ),
        3,
    ),
    _task(
        "dbg_sys_rank_tie_order",
        "RankTable: tie order follows stable-sort instinct, not the rule",
        _RANK_FIXED,
        _RANK_BUGGY,
        _RANK_TESTS,
        (_RANK_TESTS[0],),
        "Ties are ordered by submission order (stable sort), but the rule lists the later submission first.",
        (_none_variant(_RANK_FIXED), _RANK_FIXED.replace("rank = pos + 1", "rank = pos")),
        (
            "tied entries keep submission order (stable sort), but the rule puts the LATER submission first.",
            "tied entries are ordered later-submission-first, but the rule keeps submission order.",
            "the sort key ignores the score field entirely.",
            "ranks are assigned 0-based instead of 1-based.",
        ),
        1,
    ),
    _task(
        "dbg_sys_rebate_half_up",
        "Rebates: exact halves round up, not down",
        _REBATE_FIXED,
        _REBATE_BUGGY,
        _REBATE_TESTS,
        (_REBATE_TESTS[0],),
        "An exact half cent rounds up (the common instinct); the rule rounds half down.",
        (_none_variant(_REBATE_FIXED), _REBATE_FIXED.replace("num = price * 15", "num = price * 10")),
        (
            "the percentage is applied to the price twice.",
            "exact halves round down; the rule rounds half up.",
            "rounding is applied before the percentage, not after.",
            "exact half cents round up (common instinct); the rule rounds half down.",
        ),
        4,
    ),
    _task(
        "dbg_sys_window_exclusive",
        "slice_window: stop treated as exclusive",
        _WINDOW_FIXED,
        _WINDOW_BUGGY,
        _WINDOW_TESTS,
        (_WINDOW_TESTS[3],),  # inverted bounds: the only case both versions agree on
        "stop is treated as an exclusive bound (slicing instinct); the rule makes both bounds inclusive.",
        (_none_variant(_WINDOW_FIXED), _WINDOW_FIXED.replace("range(start, stop + 1)", "range(start + 1, stop + 1)")),
        (
            "stop is inclusive; the rule treats stop as exclusive.",
            "stop is treated as exclusive (slicing instinct); the rule makes both bounds inclusive.",
            "start is treated as exclusive instead of inclusive.",
            "an inverted window (start > stop) returns the whole list.",
        ),
        2,
    ),
    _task(
        "dbg_sys_merge_tie_a_first",
        "merge_records: ties taken from a first",
        _MERGETIE_FIXED,
        _MERGETIE_BUGGY,
        _MERGETIE_TESTS,
        (_MERGETIE_TESTS[0],),
        "Equal keys take a's element first (classic merge instinct); the rule takes b's first.",
        (_none_variant(_MERGETIE_FIXED), _MERGETIE_FIXED.replace("out.extend(a[i:])", "out.extend(b[j:])")),
        (
            "elements with equal keys are deduplicated.",
            "equal keys take b's element first; the rule takes a's first.",
            "equal keys take a's element first (classic merge instinct); the rule takes b's first.",
            "the leftover tail of the longer input is dropped.",
        ),
        3,
    ),
    _task(
        "dbg_sys_split_keeps_empties",
        "split_fields: empty fields kept",
        _SPLIT_FIXED,
        _SPLIT_BUGGY,
        _SPLIT_TESTS,
        (_SPLIT_TESTS[0],),
        "Consecutive delimiters produce empty fields (str.split instinct); the rule collapses them.",
        (_none_variant(_SPLIT_FIXED), _SPLIT_FIXED.replace('s.split(",")', 's.split(";")')),
        (
            "consecutive delimiters produce empty fields (str.split instinct); the rule collapses them.",
            "empty fields are collapsed; the rule keeps them.",
            "fields are not stripped of surrounding whitespace.",
            "the delimiter is ';' instead of ','.",
        ),
        1,
    ),
    _task(
        "dbg_sys_clamp_edges",
        "clamp_wrap: out-of-range clamps to edges",
        _WRAP_FIXED,
        _WRAP_BUGGY,
        _WRAP_TESTS,
        (_WRAP_TESTS[0],),
        "Out-of-range values clamp to the nearest edge (min/max instinct); the rule wraps them around.",
        (_none_variant(_WRAP_FIXED), _WRAP_FIXED.replace("span = hi - lo + 1", "span = hi - lo")),
        (
            "out-of-range values wrap around; the rule clamps them to the edges.",
            "the wrap span is computed as hi - lo, off by one.",
            "lo > hi raises instead of being handled.",
            "out-of-range values clamp to the nearest edge (min/max instinct); the rule wraps them around.",
        ),
        4,
    ),
    _task(
        "dbg_sys_div_floor",
        "div_trunc: negative division floors",
        _DIV_FIXED,
        _DIV_BUGGY,
        _DIV_TESTS,
        (_DIV_TESTS[0],),
        "Negative operands use floor division (Python // instinct); the rule truncates toward zero.",
        (_none_variant(_DIV_FIXED), _DIV_FIXED.replace("q = abs(a) // abs(b)", "q = abs(a) // abs(b) + 1")),
        (
            "negative operands truncate toward zero; the rule floors.",
            "negative operands use floor division (Python // instinct); the rule truncates toward zero.",
            "division by zero returns 0 instead of raising.",
            "the remainder is returned instead of the quotient.",
        ),
        2,
    ),
    _task(
        "dbg_sys_percent_trunc",
        "top_percent: fractional count truncated",
        _PERCENT_FIXED,
        _PERCENT_BUGGY,
        _PERCENT_TESTS,
        (_PERCENT_TESTS[0],),
        "The element count is truncated (int-division instinct); the rule rounds any fraction up.",
        (_none_variant(_PERCENT_FIXED), _PERCENT_FIXED.replace("sorted(scores, reverse=True)", "sorted(scores)")),
        (
            "the count rounds any fraction up; the rule truncates.",
            "the top elements are taken from the LOWEST scores.",
            "the element count truncates the fraction (int-division instinct); the rule rounds any fraction up.",
            "percent values above 100 are accepted instead of rejected.",
        ),
        3,
    ),
)
