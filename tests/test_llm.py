"""Gemini client tests. Offline by default; set RESCUE_CREW_LIVE_LLM=1 for one live call."""

import io
import json
import os
import urllib.error

import pytest

from rescue_crew import llm
from rescue_crew.llm import GeminiClient, GeminiError

FAKE_KEY = "AQ.fake-key-for-tests"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(text):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return FakeResponse(json.dumps(body).encode())


def test_generate_sends_key_in_header_not_url(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["key"] = req.get_header("X-goog-api-key")
        seen["body"] = json.loads(req.data)
        return reply(" OK ")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    out = GeminiClient(api_key=FAKE_KEY).generate("hi", system="be brief")
    assert out == "OK"
    assert seen["key"] == FAKE_KEY and FAKE_KEY not in seen["url"]
    assert seen["url"].endswith(f"/models/{llm.DEFAULT_MODEL}:generateContent")
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "be brief"


def test_http_error_is_redacted(monkeypatch):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url, 429, "quota", {}, io.BytesIO(f"quota for {FAKE_KEY}".encode())
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(GeminiError) as e:
        GeminiClient(api_key=FAKE_KEY).generate("hi")
    assert e.value.status == 429 and FAKE_KEY not in str(e.value)


def test_timeout_becomes_gemini_error(monkeypatch):
    def fake_urlopen(req, timeout):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(GeminiError, match="did not answer"):
        GeminiClient(api_key=FAKE_KEY, timeout=5).generate("hi")


def test_missing_key_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.delenv(llm.KEY_VAR, raising=False)
    with pytest.raises(GeminiError, match="GOOGLE_AI_API_KEY is not set"):
        GeminiClient.from_env(tmp_path / "missing.env")


def test_load_env_does_not_override_existing(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("RC_TEST_A=from_file\nRC_TEST_B='quoted'\n# comment\n", encoding="utf-8")
    monkeypatch.setenv("RC_TEST_A", "already_set")
    monkeypatch.delenv("RC_TEST_B", raising=False)
    llm.load_env(env)
    assert os.environ["RC_TEST_A"] == "already_set"
    assert os.environ["RC_TEST_B"] == "quoted"


def test_repr_hides_key():
    assert FAKE_KEY not in repr(GeminiClient(api_key=FAKE_KEY))


@pytest.mark.skipif(os.environ.get("RESCUE_CREW_LIVE_LLM") != "1", reason="live call is opt-in")
def test_live_gemini_call():
    assert "OK" in GeminiClient.from_env().generate("Reply with exactly: OK")
