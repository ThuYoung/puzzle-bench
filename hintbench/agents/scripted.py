"""Scripted wordle agents: controllable skill, consistency, and hint policies.

These stand in for LLM agents in the harness self-check. Their job is to make
the grader's expected discriminations observable on purpose: a smart buyer, a
stubborn solver, and a panic buyer should land in different places on the
completion/unaided/regret triad.
"""

from __future__ import annotations

import random

from hintbench.envs.wordle import ANSWERS, WORD_LENGTH, consistent_with_feedback
from hintbench.schema import EpisodeResult


class ScriptedWordleAgent:
    """Plays wordle through the env's text protocol.

    consistency: probability that a guess respects feedback history and hints
    skill: probability of picking the max-elimination guess instead of a random candidate
    format_error_rate: probability of emitting an unparseable turn
    hint_policy: "never" | "smart" | "panic"
    """

    def __init__(
        self,
        seed: int,
        *,
        consistency: float = 1.0,
        skill: float = 1.0,
        format_error_rate: float = 0.0,
        hint_policy: str = "never",
    ) -> None:
        self.rng = random.Random(seed)
        self.consistency = consistency
        self.skill = skill
        self.format_error_rate = format_error_rate
        self.hint_policy = hint_policy
        self.candidates: list[str] = list(ANSWERS)

    def _refilter(self, guess: str, marks: tuple[str, ...], env) -> None:
        self.candidates = [
            w
            for w in self.candidates
            if consistent_with_feedback(w, [(guess, marks)]) and env._satisfies_hints(w)
        ]

    def _pick_guess(self) -> str:
        pool = self.candidates or list(ANSWERS)
        if self.rng.random() > self.consistency:
            return self.rng.choice(list(ANSWERS))
        if self.rng.random() < self.skill and len(pool) > 1:
            return max(pool, key=lambda g: self._elimination(g, pool))
        return pool[0]

    def _elimination(self, guess: str, pool: list[str]) -> float:
        from hintbench.envs.wordle import mark_guess

        buckets: dict[tuple[str, ...], int] = {}
        for target in pool:
            key = mark_guess(guess, target)
            buckets[key] = buckets.get(key, 0) + 1
        return -sum(v * v for v in buckets.values()) / len(pool)

    async def play(self, env) -> EpisodeResult:
        await env.reset()
        self._apply_hint_filter(env, force=True)  # protocol A grants arrive pre-game
        while True:
            # probes: smart agents know their filtering quality
            if env.turn == 2 and self.hint_policy == "smart":
                await env.request_probe()
                await env.probe_answer(len(self.candidates))

            await self._maybe_buy(env)
            if env.solved_turn >= 0 or env.turn >= env.max_turns:
                break

            if self.rng.random() < self.format_error_rate:
                reply = await env.step("Hmm, tricky one. Let me think out loud.")
            else:
                guess = self._pick_guess()
                reply = await env.step(f"My guess:\nGuess: {guess}")
                if ":" in reply and "no parseable" not in reply:
                    marks = tuple(part.split(":")[1] for part in reply.split(" "))
                    self._refilter(guess, marks, env)
            if env.solved_turn >= 0:
                break
        return await env.close()

    def _apply_hint_filter(self, env, *, force: bool = False) -> None:
        if force or self.rng.random() < self.consistency:
            self.candidates = [w for w in self.candidates if env._satisfies_hints(w)]

    async def _maybe_buy(self, env) -> None:
        if self.hint_policy == "never":
            return
        owned = env.owned_levels
        if self.hint_policy == "panic":
            # panic buyers climb the whole ladder to the answer mid-game
            if env.turn == 3 and env.solved_turn < 0:
                for level in (1, 2, 3, 5):
                    if level in owned:
                        continue
                    reply = await env.buy_hint(
                        level, position=self.rng.randrange(WORD_LENGTH) if level == 3 else None
                    )
                    if "insufficient" in reply:
                        break
                self._apply_hint_filter(env, force=True)
            return
        if self.hint_policy == "smart":
            # cheap information is always worth one coin early; deeper hints
            # only when the candidate set stays large
            if env.turn == 0 and 1 not in owned and env.coins >= 1:
                await env.buy_hint(1)
                self._apply_hint_filter(env)
            elif env.turn == 2 and len(self.candidates) > 10 and 2 not in owned and env.coins >= 1:
                await env.buy_hint(2)
                self._apply_hint_filter(env)
            elif env.turn == 3 and len(self.candidates) > 5 and 3 not in owned and env.coins >= 2:
                await env.buy_hint(3, position=self.rng.randrange(WORD_LENGTH))
                self._apply_hint_filter(env)
