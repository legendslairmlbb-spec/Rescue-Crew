"""Minimal OpenRouter chat client using a single API key.

All settings come from the environment or the git-ignored .env file, never from code:

- OPENROUTER_API_KEY: the key, sent only in the Authorization header and redacted from errors
- OPENROUTER_MODEL: the model to call first
- OPENROUTER_FALLBACK_MODELS: optional comma-separated models tried in order when the previous
  one is rate-limited, unavailable or times out
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_VAR = "OPENROUTER_API_KEY"
MODEL_VAR = "OPENROUTER_MODEL"
FALLBACK_VAR = "OPENROUTER_FALLBACK_MODELS"

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
    last_model: str | None = None  # the model that produced the most recent reply

    @classmethod
    def from_env(cls, env_file: Path | str = ".env") -> OpenRouterClient:
        load_env(env_file)
        key = os.environ.get(KEY_VAR, "").strip()
        model = os.environ.get(MODEL_VAR, "").strip()
        if not key:
            raise LLMError(f"{KEY_VAR} is not set (put it in .env or the environment)")
        if not model:
            raise LLMError(f"{MODEL_VAR} is not set (put the model name in .env)")
        fallbacks = [m.strip() for m in os.environ.get(FALLBACK_VAR, "").split(",") if m.strip()]
        return cls(api_key=key, models=[model, *[m for m in fallbacks if m != model]])

    def _call(self, model: str, messages: list[dict]) -> str:
        body = json.dumps({"model": model, "messages": messages}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
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
