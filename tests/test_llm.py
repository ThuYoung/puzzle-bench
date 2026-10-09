"""LLM adapter tests with a mocked Anthropic endpoint (httpx MockTransport)."""

import asyncio
import json

import httpx

from hintbench.agents.llm import (
    PROVIDERS,
    LLMDebugAgent,
    ModelSpec,
    load_models,
    parse_action,
)
from hintbench.economy import Wallet
from hintbench.envs.debug import DebugEnv
from hintbench.tasks_debug import TASK_SUM


def make_agent(replies: list[str], **kw) -> LLMDebugAgent:
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        text = queue.pop(0) if queue else "DONE"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.anthropic.com")
    return LLMDebugAgent(api_key="test", model="test-model", client=client, **kw)


def test_parse_action_priority_and_shapes():
    assert parse_action("BUY: 2") == ("BUY", 2)
    assert parse_action("let me buy\nBUY: 3\n```python\nx=1\n```") == ("BUY", 3)  # buy before patch
    assert parse_action("PROBE: 4") == ("PROBE", 4)
    assert parse_action("```python\nx = 1\n```") == ("PATCH", None)
    assert parse_action("DONE") == ("DONE", None)
    assert parse_action("I'm thinking...") == ("INVALID", None)


async def test_full_episode_buy_fix_done():
    agent = make_agent([
        "BUY: 1",
        f"```python\n{TASK_SUM.fixed_source}```",
        "DONE",
    ])
    env = DebugEnv(TASK_SUM, wallet=Wallet(5))
    result = await agent.play(env)
    assert [p.level for p in result.purchases] == [1]
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved and solved.clean  # L1 does not spoil the fix
    assert agent.usage == {"input_tokens": 30, "output_tokens": 15}


async def test_malformed_reply_gets_correction_then_recovers():
    agent = make_agent([
        "hmm, not sure what to do",  # INVALID -> correction note
        f"```python\n{TASK_SUM.fixed_source}```",
        "DONE",
    ])
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    result = await agent.play(env)
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved
    assert result.meta["turns_used"] == 1  # correction did not burn a turn


async def test_persistent_malformed_burns_one_turn_not_the_episode():
    agent = make_agent(["garbage", "still garbage", "worse garbage", "DONE"], max_retries=2)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0), max_turns=8)
    result = await agent.play(env)
    assert result.meta["turns_used"] == 1  # one wasted turn via no-op step, then DONE


async def test_transient_status_retried(monkeypatch):
    calls = {"n": 0}
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"content": [{"type": "text", "text": "DONE"}],
                                         "usage": {"input_tokens": 1, "output_tokens": 1}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.anthropic.com")
    agent = LLMDebugAgent(api_key="t", model="m", client=client)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await agent.play(env)
    assert calls["n"] == 2
    assert sleeps and sleeps[0] >= 4  # 429 backoff is real, not a sub-second blip


async def test_openai_compatible_provider_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "DONE"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    spec = ModelSpec(
        label="kimi", provider="openai", model="kimi-k2-0905-preview",
        key_env="MOONSHOT_API_KEY", base_url="https://api.moonshot.cn/v1",
    )
    # for_model would refuse without a key; a mock client makes the key irrelevant
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=spec.base_url,
                               headers={"Authorization": "Bearer sk-test"})
    agent = LLMDebugAgent.for_model(spec, client=client)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await agent.play(env)

    body = seen["body"]
    assert body["messages"][0]["role"] == "system"  # system folded into messages
    assert "system" not in body
    assert seen["auth"] == "Bearer sk-test"
    assert agent.usage == {"input_tokens": 7, "output_tokens": 3}


async def test_reasoning_effort_reaches_openai_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "DONE"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    spec = ModelSpec(
        label="kimi", provider="openai", model="kimi-for-coding",
        key_env="MOONSHOT_API_KEY", base_url="https://api.kimi.com/coding/v1",
        temperature=1.0, reasoning_effort="low",
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=spec.base_url,
                               headers={"Authorization": "Bearer sk-test"})
    agent = LLMDebugAgent.for_model(spec, client=client)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await agent.play(env)
    assert seen["body"]["reasoning_effort"] == "low"
    assert seen["body"]["temperature"] == 1.0


async def test_empty_reply_never_enters_history_verbatim():
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        n = len(bodies)
        text = "" if n == 1 else "DONE"
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": text}],
                  "usage": {"input_tokens": 1, "output_tokens": 1}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.anthropic.com")
    agent = LLMDebugAgent(api_key="t", model="m", client=client)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    await agent.play(env)
    # the second request must not carry an empty assistant message: endpoints
    # answer 400 for those, and the sentinel keeps the trajectory going
    second = bodies[1]
    assistant_msgs = [m for m in second["messages"] if m["role"] == "assistant"]
    assert assistant_msgs and all(m["content"] for m in assistant_msgs)


async def test_client_error_raises_with_body_no_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "invalid temperature"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.anthropic.com")
    agent = LLMDebugAgent(api_key="t", model="m", client=client)
    env = DebugEnv(TASK_SUM, wallet=Wallet(0))
    try:
        await agent.play(env)
    except RuntimeError as exc:
        assert "invalid temperature" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert calls["n"] == 1


def test_load_models_and_key_resolution(tmp_path, monkeypatch):
    toml = tmp_path / "models.toml"
    toml.write_text(
        '[[models]]\nlabel = "a"\nprovider = "anthropic"\nmodel = "m1"\nkey_env = "KEY_A"\n'
        '[[models]]\nlabel = "b"\nprovider = "openai"\nmodel = "m2"\n'
        'base_url = "https://api.moonshot.cn/v1"\nkey_env = "KEY_B"\ntemperature = 0.0\n'
    )
    specs = load_models(str(toml))
    assert [s.label for s in specs] == ["a", "b"]
    monkeypatch.setenv("KEY_A", "sk-x")
    monkeypatch.delenv("KEY_B", raising=False)
    assert specs[0].resolve_key() == "sk-x"
    assert specs[1].resolve_key() is None  # runner skips this one


def test_for_model_refuses_without_key(monkeypatch):
    spec = ModelSpec(label="a", provider="anthropic", model="m", key_env="MISSING_KEY")
    monkeypatch.delenv("MISSING_KEY", raising=False)
    try:
        LLMDebugAgent.for_model(spec)
    except ValueError as exc:
        assert "MISSING_KEY" in str(exc)
    else:
        raise AssertionError("expected ValueError")


async def test_diagnosis_probe_end_to_end():
    from hintbench.tasks_expr import EXPR_TASKS

    task = EXPR_TASKS[0]  # zolarith: fault_answer == 4
    agent = make_agent([
        f"```python\n{task.fixed_source}```",
        "PROBE: 4",
        "DONE",
    ])
    env = DebugEnv(task, wallet=Wallet(0))
    result = await agent.play(env)
    diag = next(e for e in result.milestones if e.milestone_id == "diagnosis")
    assert diag.applicable and diag.achieved and diag.clean
    probe = next(p for p in result.meta["probes"] if p["kind"] == "diagnosis")
    assert probe["claimed"] == 4 and probe["ok"] is True


async def test_turn_exhaustion_still_returns_graded_result():
    # the model never says DONE; when the env stops accepting actions the
    # episode must still close and grade instead of returning None
    task = TASK_SUM
    agent = make_agent(
        [f"```python\n{task.fixed_source}```", f"```python\n{task.fixed_source}```"],
        max_retries=0,
    )
    env = DebugEnv(task, wallet=Wallet(0), max_turns=1)
    result = await agent.play(env)
    assert result is not None
    solved = next(e for e in result.milestones if e.milestone_id == "solved")
    assert solved.achieved
