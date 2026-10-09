"""Configuration via pydantic-settings; see project conventions."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HINTBENCH_", env_file=".env", extra="ignore")

    wordle_max_turns: int = 4  # tight enough that the L0 cell is not a ceiling
    default_seeds: int = 3
    default_budget: int = 7
    reward_lambda: float = 0.02
    log_level: str = "INFO"

    # real-model adapter (agents/llm.py); empty key disables main_llm.py
    anthropic_api_key: str = ""
    llm_base_url: str = "https://api.anthropic.com"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.0  # benchmark runs should be near-deterministic


@lru_cache
def get_settings() -> Settings:
    return Settings()
