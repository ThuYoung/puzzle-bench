"""Real-model agent adapter: drives a chat model through the env text protocol.

The harness owns the loop (per project conventions a plain httpx client, no
agent SDK): the model sees reset() and each env reply, and answers with ONE
action per turn:

    BUY: <level>          purchase the next ladder hint
    ```python ... ```     submit a full replacement solution.py
    PROBE: <n>            answer the env's calibration probe
    DONE                  close the episode

Malformed replies do not reach the env; the adapter asks again with a short
correction note (budget of retries, then the turn is wasted via a no-op step
so a stuck model still produces a gradeable trajectory).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx

from puzzlebench.schema import EpisodeResult

SYSTEM_PROMPT = """You are being evaluated on a debugging task with PAID hints.

Protocol — exactly one action per reply:
- To buy a hint: a line "BUY: <level>" (hints are sold in ladder order)
- To submit a fix: one fenced ```python block containing the FULL corrected solution.py
  (for multi-file tasks: one block per changed file, tagged ```python:<module>;
  an untagged block replaces the entry file)
- To answer a probe: a line "PROBE: <integer>"
- To end the episode: "DONE"

Hidden tests grade your fix. Each patch report shows public-test results and
the hidden PASS COUNT; WHICH hidden tests fail and why is what paid hints
reveal (L1 names, L2 assertion details, deeper levels beyond). Hints cost
coins from a shared budget across tasks — spend them where they pay off.
After buying a hint, your next patch should reflect what it revealed.
Once all hidden tests pass, some tasks offer diagnosis options in the patch
report: naming the TRUE planted fault with "PROBE: <number>" is scored
separately (one attempt) — answer it before DONE if you understood the bug."""

_BUY = re.compile(r"^BUY:\s*(\d+)\s*$", re.MULTILINE)
_PROBE = re.compile(r"^PROBE:\s*(\d+)\s*$", re.MULTILINE)
_DONE = re.compile(r"^DONE\b", re.MULTILINE)
_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

_CORRECTION = (
    "No action parsed. Reply with exactly one of: 'BUY: <level>', "
    "a fenced ```python block with the full solution, 'PROBE: <n>', or 'DONE'."
)


def parse_action(text: str) -> tuple[str, int | None]:
    """(kind, payload): BUY/PROBE carry the integer, PATCH/DONE/INVALID None."""
    if match := _BUY.search(text):
        return "BUY", int(match.group(1))
    if match := _PROBE.search(text):
        return "PROBE", int(match.group(1))
    if _FENCE.search(text):
        return "PATCH", None
    if _DONE.search(text):
        return "DONE", None
    return "INVALID", None


class Provider:
    """Wire format for one chat-completions family. Single-shot calls only;
    retry/backoff stays in the agent so every provider shares it."""

    endpoint: str = ""

    def build_client(self, api_key: str, base_url: str) -> httpx.AsyncClient:
        raise NotImplementedError

    def payload(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
        reasoning_effort: str | None = None,
    ) -> dict:
        raise NotImplementedError

    def parse(self, data: dict) -> tuple[str, dict[str, int]]:
        """-> (completion text, {"input_tokens": n, "output_tokens": n})"""
        raise NotImplementedError

    @staticmethod
    def retryable(status: int) -> bool:
        return status in (429, 500, 502, 503, 529)


class AnthropicProvider(Provider):
    endpoint = "/v1/messages"

    def build_client(self, api_key: str, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=httpx.Timeout(120.0),
        )

    def payload(self, *, model, system, messages, max_tokens, temperature, reasoning_effort=None) -> dict:
        return {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": messages,
        }

    def parse(self, data: dict) -> tuple[str, dict[str, int]]:
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        raw = data.get("usage", {})
        return text, {
            "input_tokens": raw.get("input_tokens", 0),
            "output_tokens": raw.get("output_tokens", 0),
        }


class OpenAICompatibleProvider(Provider):
    """OpenAI chat-completions format; covers Moonshot, DeepSeek, vLLM, etc."""

    endpoint = "/chat/completions"

    def build_client(self, api_key: str, base_url: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(120.0),
        )

    def payload(self, *, model, system, messages, max_tokens, temperature, reasoning_effort=None) -> dict:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        # reasoning-only endpoints (e.g. kimi-for-coding) accept an effort knob;
        # plain chat models never see the field
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
        return body

    def parse(self, data: dict) -> tuple[str, dict[str, int]]:
        choices = data.get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content") or ""
        raw = data.get("usage") or {}
        return text, {
            "input_tokens": raw.get("prompt_tokens", 0),
            "output_tokens": raw.get("completion_tokens", 0),
        }


PROVIDERS: dict[str, Provider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAICompatibleProvider(),
}

DEFAULT_BASE_URL = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
}


def _provider_name(provider: Provider) -> str:
    for name, p in PROVIDERS.items():
        if type(p) is type(provider):
            return name
    raise ValueError(f"unregistered provider: {provider!r}")


@dataclass(frozen=True)
class ModelSpec:
    """One model under evaluation, from models.toml. The API key itself is
    never in the file — only the name of the env var that holds it."""

    label: str
    provider: str
    model: str
    key_env: str
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096
    reasoning_effort: str | None = None

    def resolve_key(self) -> str | None:
        import os

        return os.environ.get(self.key_env) or None


def load_models(path: str) -> list[ModelSpec]:
    import tomllib

    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    specs = []
    for entry in data.get("models", []):
        if entry["provider"] not in PROVIDERS:
            raise ValueError(f"unknown provider: {entry['provider']}")
        specs.append(ModelSpec(**entry))
    return specs


class LLMDebugAgent:
    """One instance per episode; conversation state is per-episode."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        provider: Provider | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        reasoning_effort: str | None = None,
        client: httpx.AsyncClient | None = None,
        max_retries: int = 2,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.max_retries = max_retries
        self.system_prompt = system_prompt
        self.provider = provider or AnthropicProvider()
        self._client = client or self.provider.build_client(
            api_key, base_url or DEFAULT_BASE_URL[_provider_name(self.provider)]
        )
        self._owns_client = client is None
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    @classmethod
    def for_model(cls, spec: ModelSpec, *, client: httpx.AsyncClient | None = None, **kw) -> "LLMDebugAgent":
        api_key = spec.resolve_key()
        if api_key is None and client is None:
            raise ValueError(f"{spec.label}: env var {spec.key_env} is not set")
        return cls(
            api_key=api_key or "",
            model=spec.model,
            provider=PROVIDERS[spec.provider],
            base_url=spec.base_url,
            max_tokens=spec.max_tokens,
            temperature=spec.temperature,
            reasoning_effort=spec.reasoning_effort,
            client=client,
            **kw,
        )

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        body = self.provider.payload(
            model=self.model,
            system=self.system_prompt,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            reasoning_effort=self.reasoning_effort,
        )
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                resp = await self._client.post(self.provider.endpoint, json=body)
                if self.provider.retryable(resp.status_code):
                    last_error = RuntimeError(f"transient {resp.status_code}")
                    # 429 bursts need real backoff; transport blips are short
                    await asyncio.sleep(min(2 ** (attempt + 2), 60))
                    continue
                if resp.status_code >= 400:
                    # non-retryable: fail at once, with the body for diagnosis
                    raise RuntimeError(f"completion refused: {resp.status_code}: {resp.text[:300]}")
                text, usage = self.provider.parse(resp.json())
                self.usage["input_tokens"] += usage["input_tokens"]
                self.usage["output_tokens"] += usage["output_tokens"]
                return text
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
        raise RuntimeError(f"completion failed after retries: {last_error}")

    async def play(self, env) -> EpisodeResult:
        obs = await env.reset()
        messages: list[dict[str, str]] = [{"role": "user", "content": obs}]
        try:
            while True:
                reply = None
                for _ in range(self.max_retries + 1):
                    text = await self._complete(messages)
                    # some endpoints 400 on empty assistant content in the
                    # history; park a sentinel instead (parses as INVALID)
                    messages.append({"role": "assistant", "content": text.strip() or "(empty reply)"})
                    kind, payload = parse_action(text)
                    if kind == "INVALID":
                        messages.append({"role": "user", "content": _CORRECTION})
                        continue
                    if kind == "BUY":
                        reply = await env.buy_hint(payload)
                    elif kind == "PROBE":
                        await env.probe_answer(payload)
                        reply = "probe recorded"
                    elif kind == "PATCH":
                        reply = await env.step(text)
                    else:  # DONE
                        return await env.close()
                    break
                if reply is None:
                    # burned every retry on malformed output: waste the turn so
                    # the trajectory stays gradeable instead of looping forever
                    reply = await env.step("no action")
                if "episode finished" in reply:
                    break
                messages.append({"role": "user", "content": reply})
            # turn budget exhausted without DONE: still close so the trajectory
            # is graded instead of vanishing
            return await env.close()
        finally:
            if self._owns_client:
                await self._client.aclose()
        return await env.close()
