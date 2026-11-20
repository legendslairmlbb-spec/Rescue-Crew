"""Minimal chat client for any OpenAI-compatible endpoint (OpenRouter by default).

All settings come from the environment or the git-ignored .env file, never from code:

- LLM_BASE_URL: the endpoint, e.g. https://openrouter.ai/api/v1 (the default)
- LLM_API_KEY: the key, sent only in the Authorization header and redacted from errors
- LLM_MODEL: the model to call first
- LLM_FALLBACK_MODELS: optional comma-separated models tried in order when the previous one
  is rate-limited, unavailable or times out

The older OPENROUTER_API_KEY / OPENROUTER_MODEL / OPENROUTER_FALLBACK_MODELS names still work
when the LLM_* ones are not set.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
BASE_URL_VAR = "LLM_BASE_URL"
KEY_VAR = "LLM_API_KEY"
MODEL_VAR = "LLM_MODEL"
FALLBACK_VAR = "LLM_FALLBACK_MODELS"
LEGACY_VARS = {
    KEY_VAR: "OPENROUTER_API_KEY",
    MODEL_VAR: "OPENROUTER_MODEL",
    FALLBACK_VAR: "OPENROUTER_FALLBACK_MODELS",
}


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value and name in LEGACY_VARS:
        value = os.environ.get(LEGACY_VARS[name], "").strip()
    return value


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str = field(repr=False)
    models: list[str] = field(default_factory=list)


def settings(env_file: Path | str = ".env") -> LLMSettings:
    """Read endpoint, key and models from the environment / .env, or raise LLMError."""
    load_env(env_file)
    key, model = _env(KEY_VAR), _env(MODEL_VAR)
    if not key:
        raise LLMError(f"{KEY_VAR} is not set (put it in .env or the environment)")
    if not model:
        raise LLMError(f"{MODEL_VAR} is not set (put the model name in .env)")
    fallbacks = [m.strip() for m in _env(FALLBACK_VAR).split(",") if m.strip()]
    base = (_env(BASE_URL_VAR) or DEFAULT_BASE_URL).rstrip("/")
    return LLMSettings(base, key, [model, *[m for m in fallbacks if m != model]])


# Errors worth trying the next model for. 401 (bad key) is not: every model would fail.
RETRYABLE_STATUS = {402, 403, 404, 408, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """A model call failed. The message never contains the API key."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def load_env(path: Path | str = ".env") -> None:
    """Load KEY=value lines from a .env file without overriding variables already set."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


@dataclass
class OpenRouterClient:
    api_key: str = field(repr=False)
    models: list[str]
    timeout: float = 120.0
    base_url: str = DEFAULT_BASE_URL
    last_model: str | None = None  # the model that produced the most recent reply

    @classmethod
    def from_env(cls, env_file: Path | str = ".env") -> OpenRouterClient:
        s = settings(env_file)
        return cls(api_key=s.api_key, models=list(s.models), base_url=s.base_url)

    def _call(self, model: str, messages: list[dict]) -> str:
        # stream=False explicitly: some OpenAI-compatible routers stream when it is omitted.
        body = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Rescue Crew",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300].replace(self.api_key, "***")
            raise LLMError(f"{model}: HTTP {e.code}: {detail}", e.code) from None
        except urllib.error.URLError as e:
            raise LLMError(f"{model}: could not reach OpenRouter: {e.reason}") from None
        except TimeoutError:
            raise LLMError(f"{model}: no answer within {self.timeout:g}s", 408) from None

        if "error" in data:
            err = data["error"]
            raise LLMError(f"{model}: {err.get('message', err)}", err.get("code"))
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"{model}: response had no choices", 502) from None
        if not text.strip():
            raise LLMError(f"{model}: empty reply", 502)
        return text.strip()

    def generate(self, prompt: str, system: str | None = None) -> str:
        """Send one prompt; try each configured model in order until one answers."""
        messages = [{"role": "system", "content": system}] if system else []
        messages.append({"role": "user", "content": prompt})
        errors = []
        for model in self.models:
            try:
                text = self._call(model, messages)
            except LLMError as e:
                if e.status not in RETRYABLE_STATUS:
                    raise
                errors.append(str(e))
                continue
            self.last_model = model
            return text
        raise LLMError("all models failed: " + " | ".join(errors))


def check() -> None:
    """Command-line check: one short live call, printing which model answered."""
    client = OpenRouterClient.from_env()
    reply = client.generate("Reply with exactly: OK")
    print(f"{client.last_model}: {reply}")
