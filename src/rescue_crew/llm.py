"""Minimal Gemini client using a single Google AI key.

The key is read from GOOGLE_AI_API_KEY (environment or the git-ignored .env file) and is
sent only in the x-goog-api-key header, never in a URL, log line or error message.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Verified 2026-11-19 on the free tier: gemini-3.5-flash-lite answers; gemini-3.5-flash allows
# only 20 requests/day; gemini-flash-latest and gemini-3.8-flash timed out; gemini-2.5-flash is
# closed to new users.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
KEY_VAR = "GOOGLE_AI_API_KEY"


class GeminiError(RuntimeError):
    """A Gemini call failed. The message never contains the API key."""

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
class GeminiClient:
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    timeout: float = 60.0

    @classmethod
    def from_env(cls, env_file: Path | str = ".env") -> GeminiClient:
        load_env(env_file)
        key = os.environ.get(KEY_VAR, "").strip()
        if not key:
            raise GeminiError(f"{KEY_VAR} is not set (put it in .env or the environment)")
        return cls(api_key=key, model=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))

    def generate(self, prompt: str, system: str | None = None) -> str:
        """Send one prompt and return the model's text reply."""
        body: dict = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        req = urllib.request.Request(
            f"{API_BASE}/models/{self.model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300].replace(self.api_key, "***")
            raise GeminiError(f"Gemini returned HTTP {e.code}: {detail}", e.code) from None
        except urllib.error.URLError as e:
            raise GeminiError(f"could not reach Gemini: {e.reason}") from None
        except TimeoutError:
            raise GeminiError(f"Gemini did not answer within {self.timeout:g}s") from None

        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise GeminiError(f"Gemini returned no text ({reason})") from None
        return "".join(p.get("text", "") for p in parts).strip()


def check() -> None:
    """Command-line check: one short live call, printing the model and its reply."""
    client = GeminiClient.from_env()
    reply = client.generate("Reply with exactly: OK")
    print(f"{client.model}: {reply}")
