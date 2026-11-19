"""OpenRouter client tests. Offline by default; set RESCUE_CREW_LIVE_LLM=1 for one live call."""

import io
import json
import os
import urllib.error
from pathlib import Path

import pytest

from rescue_crew import llm
from rescue_crew.llm import LLMError, OpenRouterClient

FAKE_KEY = "sk-or-v1-fake-key-for-tests"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def reply(text):
    return FakeResponse(json.dumps({"choices": [{"message": {"content": text}}]}).encode())


def http_error(req, code, text="error"):
    return urllib.error.HTTPError(req.full_url, code, "err", {}, io.BytesIO(text.encode()))


def client(*models):
    return OpenRouterClient(api_key=FAKE_KEY, models=list(models or ["model/a"]))


def test_generate_sends_key_in_header_and_model_in_body(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["auth"] = req.get_header("Authorization")
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data)
        return reply(" OK ")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    c = client("model/a")
    assert c.generate("hi", system="be brief") == "OK"
    assert seen["auth"] == f"Bearer {FAKE_KEY}" and FAKE_KEY not in seen["url"]
    assert seen["body"]["model"] == "model/a"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert c.last_model == "model/a"


@pytest.mark.parametrize("code", [429, 402, 404, 503])
def test_falls_back_to_next_model_on_retryable_errors(monkeypatch, code):
    calls = []

    def fake_urlopen(req, timeout):
        model = json.loads(req.data)["model"]
        calls.append(model)
        if model == "model/a":
            raise http_error(req, code)
        return reply("OK")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    c = client("model/a", "model/b")
    assert c.generate("hi") == "OK"
    assert calls == ["model/a", "model/b"] and c.last_model == "model/b"


def test_timeout_falls_back_too(monkeypatch):
    def fake_urlopen(req, timeout):
        if json.loads(req.data)["model"] == "model/a":
            raise TimeoutError("read timed out")
        return reply("OK")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    assert client("model/a", "model/b").generate("hi") == "OK"


def test_bad_key_stops_without_trying_other_models(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append(1)
        raise http_error(req, 401, f"bad key {FAKE_KEY}")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError) as e:
        client("model/a", "model/b").generate("hi")
    assert e.value.status == 401 and len(calls) == 1
    assert FAKE_KEY not in str(e.value)


def test_all_models_failing_reports_each(monkeypatch):
    def fake_urlopen(req, timeout):
        raise http_error(req, 429)

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError, match="all models failed.*model/a.*model/b"):
        client("model/a", "model/b").generate("hi")


def test_empty_reply_is_retried_on_next_model(monkeypatch):
    def fake_urlopen(req, timeout):
        return reply("" if json.loads(req.data)["model"] == "model/a" else "OK")

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    assert client("model/a", "model/b").generate("hi") == "OK"


def test_from_env_reads_key_model_and_fallbacks(monkeypatch, tmp_path):
    for var in (llm.KEY_VAR, llm.MODEL_VAR, llm.FALLBACK_VAR):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(
        f"OPENROUTER_API_KEY={FAKE_KEY}\nOPENROUTER_MODEL=model/a\n"
        "OPENROUTER_FALLBACK_MODELS=model/b, model/a ,model/c\n",
        encoding="utf-8",
    )
    c = OpenRouterClient.from_env(env)
    assert c.api_key == FAKE_KEY and c.models == ["model/a", "model/b", "model/c"]


@pytest.mark.parametrize(
    ("content", "missing"),
    [
        ("OPENROUTER_MODEL=model/a\n", "OPENROUTER_API_KEY"),
        ("OPENROUTER_API_KEY=k\n", "OPENROUTER_MODEL"),
    ],
)
def test_from_env_requires_key_and_model(monkeypatch, tmp_path, content, missing):
    for var in (llm.KEY_VAR, llm.MODEL_VAR, llm.FALLBACK_VAR):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / ".env"
    env.write_text(content, encoding="utf-8")
    with pytest.raises(LLMError, match=f"{missing} is not set"):
        OpenRouterClient.from_env(env)


def test_no_model_name_hardcoded_in_source():
    source = Path(llm.__file__).read_text(encoding="utf-8")
    assert ":free" not in source and "nemotron" not in source


def test_load_env_does_not_override_existing(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("RC_TEST_A=from_file\nRC_TEST_B='quoted'\n# comment\n", encoding="utf-8")
    monkeypatch.setenv("RC_TEST_A", "already_set")
    monkeypatch.delenv("RC_TEST_B", raising=False)
    llm.load_env(env)
    assert os.environ["RC_TEST_A"] == "already_set"
    assert os.environ["RC_TEST_B"] == "quoted"


def test_repr_hides_key():
    assert FAKE_KEY not in repr(client())


@pytest.mark.skipif(os.environ.get("RESCUE_CREW_LIVE_LLM") != "1", reason="live call is opt-in")
def test_live_openrouter_call():
    assert "OK" in OpenRouterClient.from_env().generate("Reply with exactly: OK")
