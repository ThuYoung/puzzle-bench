"""Scripted debug agents: the never/smart/panic archetypes for Track B.

Same role as the wordle test doubles: make the grader's discriminations
observable on purpose. The agent knows the canonical fix (test doubles may
read env.task); whether it lands the fix on a given turn is sampled from an
effective skill that hint ownership raises — L2 clarifies expectations, L4
points at the region, L5 is decisive.
"""

from __future__ import annotations

import random

from hintbench.schema import EpisodeResult
from hintbench.tasks_debug import DebugTask

_SKILL_BUMP = {2: 0.25, 4: 0.25}


class ScriptedDebugAgent:
    """hint_policy: "never" | "smart" | "panic"."""

    def __init__(
        self,
        seed: int,
        *,
        skill: float = 0.5,
        format_error_rate: float = 0.0,
        hint_policy: str = "never",
    ) -> None:
        self.task: DebugTask | None = None  # bound from the env at play() time
        self.rng = random.Random(seed)
        self.skill = skill
        self.format_error_rate = format_error_rate
        self.hint_policy = hint_policy
        self._public_passed = False

    def _effective_skill(self, owned: set[int]) -> float:
        if 5 in owned:
            return 1.0  # fix sketch is decisive for a scripted agent
        return min(1.0, self.skill + sum(_SKILL_BUMP.get(lv, 0.0) for lv in owned))

    def _attempt(self, owned: set[int]) -> str:
        assert self.task is not None
        if self.rng.random() < self._effective_skill(owned):
            return self.task.fixed_source
        return self.rng.choice(self.task.wrong_variants)

    async def play(self, env) -> EpisodeResult:
        self.task = env.task
        await env.reset()
        while env.turn < env.max_turns:
            await self._maybe_buy(env)
            if self._public_passed:
                break
            if self.rng.random() < self.format_error_rate:
                await env.step("Let me think about this bug first.")
                continue
            patch = self._attempt(env.owned_levels)
            reply = await env.step(f"Here is my fix:\n```python\n{patch}```")
            self._public_passed = _public_all_pass(reply)
        return await env.close()

    async def _buy(self, env, level: int) -> bool:
        reply = await env.buy_hint(level)
        return "insufficient" not in reply and "episode finished" not in reply

    async def _maybe_buy(self, env) -> None:
        if self.hint_policy == "never" or self._public_passed:
            return
        owned = env.owned_levels
        if self.hint_policy == "panic":
            # stuck mid-game: climb the whole ladder until the wallet says no
            if env.turn >= 3:
                for level in (1, 2, 3, 4, 5):
                    if level not in owned:
                        await self._buy(env, level)
            return
        if self.hint_policy == "smart":
            # cheap diagnostics first; deeper goods only while still failing
            if env.turn == 0 and 1 not in owned and env.coins >= 1:
                await self._buy(env, 1)
            elif env.turn == 2 and 2 not in owned and env.coins >= 1:
                await self._buy(env, 2)
            elif env.turn == 4 and 4 not in owned and env.coins >= 4:
                # ladder order: must own L3 before L4
                if 3 not in owned:
                    await self._buy(env, 3)
                await self._buy(env, 4)


def _public_all_pass(reply: str) -> bool:
    marker = "public tests: "
    if marker not in reply:
        return False
    ratio = reply.split(marker, 1)[1].split(" pass", 1)[0]
    got, total = ratio.split("/", 1)
    return got == total
