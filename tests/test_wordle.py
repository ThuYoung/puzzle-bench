"""Wordle environment tests: marking, consistency, parsing, hint effects."""

import pytest

from hintbench.economy import Wallet
from hintbench.envs.wordle import (
    ABSENT,
    CORRECT,
    PRESENT,
    WordleEnv,
    _vowel_profile,
    consistent_with_feedback,
    mark_guess,
)


def test_mark_guess_duplicate_letters():
    # target a b a c k, guess a a c a a: green at 0; 'a' at 1 present (pool
    # exhausted after), 'c' at 2 present, remaining a's absent
    assert mark_guess("aacaa", "aback") == (CORRECT, PRESENT, PRESENT, ABSENT, ABSENT)


def test_mark_guess_all_green():
    assert mark_guess("cigar", "cigar") == (CORRECT,) * 5


def test_consistency_remarking():
    history = [("apple", mark_guess("apple", "angle"))]
    assert consistent_with_feedback("ankle", history)
    assert not consistent_with_feedback("zesty", history)


def test_vowel_profile():
    assert _vowel_profile("cigar") == "-v-v-"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Guess: crane", "crane"),
        ("**Guess: CRANE**", "crane"),
        ("first try\nGuess: wronglen\nGuess: cider", "cider"),
        ("Guess: zzzqq\nGuess: cider", "cider"),  # not in catalog -> earlier valid line
        ("Guess: maybe crane", "crane"),  # hedge word is catalog; last token wins
        ("I have no idea", None),
    ],
)
def test_parse(text, expected):
    env = WordleEnv("cigar", wallet=Wallet(0))
    assert env._parse(text) == expected


async def test_clean_solve_without_hints():
    env = WordleEnv("cigar", wallet=Wallet(0))
    await env.reset()
    await env.step("Guess: cigar")
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and solved.clean
    assert result.s_complete == result.s_unaided


async def test_answer_hint_taints_solved():
    env = WordleEnv("cigar", wallet=Wallet(7))
    await env.reset()
    for level in (1, 2, 3, 5):  # ladder order is enforced
        await env.buy_hint(level, position=0 if level == 3 else None)
    reply = await env.step("Guess: cigar")
    assert "correct" in reply
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and not solved.clean
    assert result.s_unaided < result.s_complete


async def test_preload_grants_taint_spoiled_milestones():
    env = WordleEnv("cigar", wallet=Wallet(0), preload_levels=(5,))
    await env.reset()
    await env.step("Guess: cigar")
    result = await env.close()
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and not solved.clean


async def test_hint_consistency_requires_purchase():
    env = WordleEnv("cigar", wallet=Wallet(0))
    await env.reset()
    await env.step("Guess: cigar")
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert not hc.applicable


async def test_hint_consistency_violation():
    env = WordleEnv("cigar", wallet=Wallet(4))
    await env.reset()
    await env.buy_hint(1)  # vowel profile -v-v-
    await env.buy_hint(2)  # first letter c
    await env.step("Guess: robot")  # violates the first-letter hint on purpose
    await env.step("Guess: cigar")
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert hc.applicable and not hc.achieved


async def test_ladder_order_enforced():
    env = WordleEnv("cigar", wallet=Wallet(7))
    await env.reset()
    assert "ladder order" in await env.buy_hint(3, position=0)
    assert "already owned" not in await env.buy_hint(1)
    assert "already owned" in await env.buy_hint(1)


async def test_insufficient_coins():
    env = WordleEnv("cigar", wallet=Wallet(1))
    await env.reset()
    await env.buy_hint(1)
    reply = await env.buy_hint(2)
    assert "insufficient" in reply


async def test_no_such_hint():
    env = WordleEnv("cigar", wallet=Wallet(9))
    await env.reset()
    assert "no such hint" in await env.buy_hint(99)
    assert env.coins == 9


async def test_position_validated_before_charging():
    env = WordleEnv("cigar", wallet=Wallet(4))
    await env.reset()
    await env.buy_hint(1)
    await env.buy_hint(2)
    for bad in (None, -1, 5):
        reply = await env.buy_hint(3, position=bad)
        assert "position" in reply and env.coins == 2
    assert "Position" in await env.buy_hint(3, position=0)
    assert env.coins == 0


async def test_buy_after_close_rejected():
    env = WordleEnv("cigar", wallet=Wallet(2))
    await env.reset()
    await env.close()
    assert "episode finished" in await env.buy_hint(1)
    assert env.coins == 2  # a rejected buy must never drain a shared wallet


async def test_purchase_without_later_guess_not_applicable():
    # buying then closing immediately yields zero usable information, so the
    # purchase-gated milestone leaves both denominators instead of taxing 0.20
    env = WordleEnv("cigar", wallet=Wallet(2))
    await env.reset()
    await env.buy_hint(1)
    result = await env.close()
    hc = next(e for e in result.milestones if e.milestone_id == "hint_consistent")
    assert not hc.applicable
    assert result.s_complete == result.s_unaided


async def test_immediate_close_is_zero_and_safe():
    env = WordleEnv("cigar", wallet=Wallet(0))
    await env.reset()
    result = await env.close()
    assert result.s_complete == 0.0 and result.s_unaided == 0.0
    assert result.meta["applicable_weight_total"] > 0


async def test_shared_wallet_starvation_is_deterministic():
    # one wallet across episodes: env1 climbs the whole ladder (7 coins),
    # env2 then cannot afford even the cheapest hint
    wallet = Wallet(7)
    env1 = WordleEnv("cigar", wallet=wallet)
    env2 = WordleEnv("crane", wallet=wallet)
    await env1.reset()
    await env2.reset()
    for level in (1, 2, 3, 5):
        await env1.buy_hint(level, position=0 if level == 3 else None)
    assert wallet.balance == 0
    assert "insufficient" in await env2.buy_hint(1)


async def test_granted_hint_text_appears_in_reset():
    env = WordleEnv("cigar", wallet=Wallet(0), preload_levels=(1, 2))
    preamble = await env.reset()
    assert "-v-v-" in preamble  # L1 vowel profile content, not just a level number
    assert "First letter: c" in preamble
