"""Explicit provider selection; never fall back to a different paid service."""
from __future__ import annotations

import os
import json
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


def _validate_output(value, schema):
    """Validate the small schema subset used by this project's two JSON outputs."""
    kind = schema.get("type")
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool)}
    if kind in valid and not valid[kind]:
        raise ValueError("AI output has an invalid field type")
    if kind == "object":
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError("AI output is missing a required field")
        if schema.get("additionalProperties") is False and set(value) - set(schema.get("properties", {})):
            raise ValueError("AI output has unexpected fields")
        for key, child in schema.get("properties", {}).items():
            if key in value:
                _validate_output(value[key], child)
    elif kind == "array":
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 1000):
            raise ValueError("AI output has an invalid story count")
        for item in value:
            _validate_output(item, schema["items"])


def request_json(client, *, model, messages, schema, name, temperature=0.1):
    """Constrain generation and retry malformed output once, never fabricate repairs."""
    for attempt in range(2):
        response = client.chat.completions.create(
            model=model, temperature=temperature if attempt == 0 else 0,
            max_tokens=8192,
            response_format={"type": "json_schema", "json_schema": {
                "name": name, "strict": True, "schema": schema,
            }},
            messages=messages + ([] if attempt == 0 else [{"role": "user", "content":
                "上次输出未通过格式检查。请重新生成完整、合法且符合给定schema的JSON，不加Markdown、不省略字段。"}]),
        )
        try:
            content = response.choices[0].message.content or ""
            value = json.loads(content)
            _validate_output(value, schema)
            return value
        except (ValueError, TypeError, IndexError):
            if attempt:
                raise RuntimeError("AI 连续两次返回不完整或无效的简报格式，已停止发送。") from None
