"""Wordle self-check environment for the hint-economy harness.

Purpose: exercise the full grading pipeline (budget -> milestones -> spoil
attribution -> terminal scalar) before any real task bank exists. The game is
an information economy in miniature: guesses buy information with turns, hints
buy it with coins.

Grading stays silent: step() returns only the game's own marks. Milestone
state is evaluated at close() from the recorded trajectory.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from puzzlebench.economy import Wallet
from puzzlebench.grader import grade
from puzzlebench.schema import EpisodeResult, HintSpec, MilestoneSpec, PurchaseEvent, TaskSpec
from puzzlebench.words import ANSWERS

CORRECT, PRESENT, ABSENT = "correct", "present", "absent"
WORD_LENGTH = 5
VOWELS = frozenset("aeiou")

_GUESS_LINE = re.compile(r".*guess\s*:\s*(.*)", re.IGNORECASE)
_TOKEN = re.compile(r"[A-Za-z]+")

HINT_LADDER: tuple[HintSpec, ...] = (
    HintSpec(level=1, kind="vowel_profile", cost=1),
    HintSpec(level=2, kind="first_letter", cost=1),
    HintSpec(level=3, kind="reveal_position", cost=2),
    HintSpec(level=5, kind="answer", cost=3),
)

MILESTONES: tuple[MilestoneSpec, ...] = (
    MilestoneSpec("format_ok", weight=0.05),
    MilestoneSpec("feedback_consistent", weight=0.20),
    MilestoneSpec("hint_consistent", weight=0.20, requires_hint_purchase=True),
    MilestoneSpec("greens_3plus", weight=0.15, revealed_by=frozenset({5})),
    MilestoneSpec("solved", weight=0.40, revealed_by=frozenset({5})),
)


def make_task(budget: int) -> TaskSpec:
    return TaskSpec(task_id="wordle@5", budget=budget, hints=HINT_LADDER, milestones=MILESTONES)


def mark_guess(guess: str, target: str) -> tuple[str, ...]:
    marks = [ABSENT] * WORD_LENGTH
    pool = Counter(target)
    for i in range(WORD_LENGTH):
        if guess[i] == target[i]:
            marks[i] = CORRECT
            pool[guess[i]] -= 1
    for i in range(WORD_LENGTH):
        if marks[i] != CORRECT and pool[guess[i]] > 0:
            marks[i] = PRESENT
            pool[guess[i]] -= 1
    return tuple(marks)


def consistent_with_feedback(candidate: str, history: list[tuple[str, tuple[str, ...]]]) -> bool:
    """Re-marking test: candidate must reproduce every past mark vector.

    Re-marking (not accumulated letter constraints) is what makes "absent"
    mean "no further copies" correctly when a guess repeated a letter.
    """
    return all(mark_guess(past, candidate) == past_marks for past, past_marks in history)


def _vowel_profile(word: str) -> str:
    return "".join("v" if ch in VOWELS else "-" for ch in word)


class WordleEnv:
    """Async env API: reset / step / buy_hint / request_probe / probe_answer / close.

    target is injected by the harness; the agent never sees it. preload_levels
    implements protocol A: hints are granted at turn 0 and taint spoiled
    milestones exactly like purchases do.
    """

    def __init__(
        self,
        target: str,
        *,
        wallet: Wallet,
        max_turns: int = 8,
        preload_levels: tuple[int, ...] = (),
    ) -> None:
        if target not in ANSWERS:
            raise ValueError(f"target not in catalog: {target}")
        self.target = target
        self.wallet = wallet
        self.task = make_task(wallet.balance)
        self.max_turns = max_turns
        self.turn = 0
        self.history: list[tuple[str, tuple[str, ...]]] = []
        self.purchases: list[PurchaseEvent] = []
        self.hint_constraints: list[tuple[str, Any]] = []
        self.parseable = 0
        self.consistent_count = 0
        self.hint_consistent_count = 0
        self.hint_checked_guesses = 0
        self.best_green = 0
        self.solved_turn = -1
        self.greens_turn = -1
        # first turn each ratio milestone crossed its threshold; milestones
        # attribute to first achievement, not to the end of the episode
        self.format_turn = -1
        self.feedback_turn = -1
        self.hint_turn = -1
        self.granted_texts: list[tuple[int, str]] = []
        self.probes: list[dict[str, Any]] = []
        self._closed = False
        for level in sorted(preload_levels):
            self._grant(level)

    # -- hint machinery -----------------------------------------------------

    def _constraint_for(self, level: int, position: int | None) -> tuple[str, Any, str]:
        if level == 1:
            profile = _vowel_profile(self.target)
            return ("vowel_profile", profile, f"Vowel pattern (v=vowel): {profile}")
        if level == 2:
            return ("first_letter", self.target[0], f"First letter: {self.target[0]}")
        if level == 3:
            assert position is not None and 0 <= position < WORD_LENGTH
            return ("position", (position, self.target[position]),
                    f"Position {position + 1} letter: {self.target[position]}")
        if level == 5:
            return ("answer", self.target, f"The answer is: {self.target}")
        raise ValueError(f"no hint at level {level}")

    def _grant(self, level: int) -> None:
        # protocol A grant: effective from turn 0, recorded for attribution;
        # the text is kept so reset() can hand the agent the actual content
        pos = self._pick_grant_position() if level == 3 else None
        kind, value, text = self._constraint_for(level, pos)
        self.hint_constraints.append((kind, value))
        self.granted_texts.append((level, text))
        self.purchases.append(PurchaseEvent(level=level, turn=0))

    def _pick_grant_position(self) -> int:
        revealed = {v[0] for k, v in self.hint_constraints if k == "position"}
        for i in range(WORD_LENGTH):
            if i not in revealed:
                return i
        return 0

    def _satisfies_hints(self, candidate: str) -> bool:
        for kind, value in self.hint_constraints:
            if kind == "vowel_profile" and _vowel_profile(candidate) != value:
                return False
            if kind == "first_letter" and candidate[0] != value:
                return False
            if kind == "position" and candidate[value[0]] != value[1]:
                return False
            if kind == "answer" and candidate != value:
                return False
        return True

    # -- env API ------------------------------------------------------------

    async def reset(self) -> str:
        catalog = "\n".join(" ".join(ANSWERS[i : i + 16]) for i in range(0, len(ANSWERS), 16))
        granted = [p.level for p in self.purchases]
        preamble = (
            f"Wordle. Guess the hidden {WORD_LENGTH}-letter word in {self.max_turns} turns. "
            "State guesses as 'Guess: xxxxx'. Marks per letter: "
            f"{CORRECT}/{PRESENT}/{ABSENT}. The answer is one of:\n{catalog}\n"
            f"Hint coins: {self.coins}. Ladder: "
            + "; ".join(f"L{h.level} {h.kind} cost {h.cost}" for h in HINT_LADDER)
        )
        if granted:
            # spec: a forced-level cell injects the prompt plus the hint content
            texts = "\n".join(f"L{level}: {text}" for level, text in self.granted_texts)
            preamble += f"\nPre-granted hints:\n{texts}"
        return preamble

    async def step(self, text: str) -> str:
        if self._closed or self.turn >= self.max_turns or self.solved_turn >= 0:
            return "episode finished"
        self.turn += 1
        guess = self._parse(text)
        if guess is None:
            return "no parseable guess; turn wasted"
        self.parseable += 1
        marks = mark_guess(guess, self.target)
        self.history.append((guess, marks))
        if consistent_with_feedback(guess, self.history[:-1]):
            self.consistent_count += 1
        if self.purchases:
            self.hint_checked_guesses += 1
            if self._satisfies_hints(guess):
                self.hint_consistent_count += 1
        if self.format_turn < 0 and self.parseable / self.turn >= 0.8:
            self.format_turn = self.turn
        if (
            self.feedback_turn < 0
            and self.parseable > 0
            and self.consistent_count / self.parseable >= 0.8
        ):
            self.feedback_turn = self.turn
        if (
            self.hint_turn < 0
            and self.hint_checked_guesses > 0
            and self.hint_checked_guesses == self.hint_consistent_count
        ):
            self.hint_turn = self.turn
        green = marks.count(CORRECT)
        if green >= 3 and self.greens_turn < 0:
            self.greens_turn = self.turn
        self.best_green = max(self.best_green, green)
        if guess == self.target and self.solved_turn < 0:
            self.solved_turn = self.turn
        return " ".join(f"{ch}:{m}" for ch, m in zip(guess, marks))

    @property
    def coins(self) -> int:
        return self.wallet.balance

    @property
    def owned_levels(self) -> set[int]:
        return {p.level for p in self.purchases}

    async def buy_hint(self, level: int, *, position: int | None = None) -> str:
        if self._closed or self.turn >= self.max_turns or self.solved_turn >= 0:
            return "episode finished"
        spec = next((h for h in HINT_LADDER if h.level == level), None)
        if spec is None:
            return "no such hint"
        owned = self.owned_levels
        if level in owned:
            return "hint already owned"
        missing = [h.level for h in HINT_LADDER if h.level < level and h.level not in owned]
        if missing:
            return f"hints are sold in ladder order; next available: L{min(missing)}"
        # validate before charging: a malformed request must never cost coins
        if level == 3 and not (position is not None and 0 <= position < WORD_LENGTH):
            return f"reveal_position needs position in [0, {WORD_LENGTH})"
        if not self.wallet.try_spend(spec.cost):
            return "insufficient coins"
        kind, value, text = self._constraint_for(level, position)
        self.hint_constraints.append((kind, value))
        # effective on the next turn: purchases between turns t and t+1 stamp t+1
        self.purchases.append(PurchaseEvent(level=level, turn=self.turn + 1))
        return text

    async def request_probe(self, kind: str = "diagnosis") -> str:
        # kind is accepted for protocol compatibility; wordle has one probe type
        return "How many catalog words remain consistent with all feedback and hints?"

    def _truth(self) -> int:
        return sum(
            1
            for w in ANSWERS
            if consistent_with_feedback(w, self.history) and self._satisfies_hints(w)
        )

    async def probe_answer(self, n: int) -> None:
        self.probes.append(
            {"turn": self.turn, "claimed": n, "truth": self._truth(), "ok": n == self._truth()}
        )

    def _parse(self, text: str) -> str | None:
        norm = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
        for line in reversed(norm.split("\n")):
            match = _GUESS_LINE.match(line)
            if match is None:
                continue
            # last catalog word on the line wins: trailing hedges like
            # "Guess: maybe crane" register the final word, not the hedge
            tokens = [
                token.lower()
                for token in _TOKEN.findall(match.group(1))
                if len(token) == WORD_LENGTH and token.lower() in ANSWERS
            ]
            if tokens:
                return tokens[-1]
        return None

    async def close(self) -> EpisodeResult:
        self._closed = True
        achieved: dict[str, int] = {}
        if self.solved_turn >= 0:
            achieved["solved"] = self.solved_turn
        if self.greens_turn >= 0:
            achieved["greens_3plus"] = self.greens_turn
        end_turn = max(self.turn, 1)
        # ratio milestones keep their final-state test but attribute to the
        # first turn the threshold was crossed
        if self.turn > 0 and self.parseable / self.turn >= 0.8:
            achieved["format_ok"] = self.format_turn if self.format_turn >= 0 else end_turn
        if self.parseable > 0 and self.consistent_count / self.parseable >= 0.8:
            achieved["feedback_consistent"] = (
                self.feedback_turn if self.feedback_turn >= 0 else end_turn
            )
        if (
            self.purchases
            and self.hint_checked_guesses > 0
            and self.hint_checked_guesses == self.hint_consistent_count
        ):
            achieved["hint_consistent"] = self.hint_turn if self.hint_turn >= 0 else end_turn
        if not self.probes:
            # forced end-probe: calibration metadata exists even when the
            # agent never volunteers a self-assessment (no claim recorded)
            self.probes.append(
                {"turn": self.turn, "claimed": None, "truth": self._truth(), "ok": None}
            )
        # a purchase with zero post-purchase guesses yielded no information to
        # use, so its gated milestone leaves both denominators entirely
        purchased_levels = (
            {p.level for p in self.purchases} if self.hint_checked_guesses > 0 else set()
        )
        return grade(
            self.task,
            achieved,
            self.purchases,
            purchased_levels=purchased_levels,
            meta={
                "target": self.target,
                "probes": self.probes,
                "turns_used": self.turn,
                "regret_inputs": {
                    "ladder_costs": {h.level: h.cost for h in HINT_LADDER},
                    "budget_initial": self.wallet.balance + self.wallet.spent,
                },
            },
        )
