"""Explicit provider selection; never fall back to a different paid service."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from openai import OpenAI


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    key_name: str
    base_url: str
    api_key: str = field(repr=False)

    def require_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(f"请在 GitHub Actions Secrets 中填写 {self.key_name}。")


def get_ai_settings() -> AISettings:
    provider = os.getenv("AI_PROVIDER", "gemini").strip().lower()
    if provider == "gemini":
        key_name = "GEMINI_API_KEY"
        model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.5-flash-lite"
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    elif provider == "openai":
        key_name = "OPENAI_API_KEY"
        model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
        base_url = "https://api.openai.com/v1/"
    else:
        raise ValueError("AI_PROVIDER 只支持 gemini 或 openai。")
    return AISettings(provider, model, key_name, base_url, os.getenv(key_name, "").strip())


def create_ai_client(settings: AISettings) -> OpenAI:
    settings.require_key()
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=90,
        max_retries=1,
    )
