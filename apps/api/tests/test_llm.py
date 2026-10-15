from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from forge import llm
from forge.llm import LLMError, call_anthropic_api, call_claude_cli, complete_json


class Answer(BaseModel):
    text: str


def fake_client(response):
    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = SimpleNamespace(parse=lambda **request: response(request))

    return FakeAnthropic


def usage(tokens_in, tokens_out):
    return SimpleNamespace(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )


def test_api_provider_returns_data_and_prices_the_call(monkeypatch):
    seen = {}

    def respond(request):
        seen.update(request)
        return SimpleNamespace(
            stop_reason="end_turn", parsed_output=Answer(text="hi"), usage=usage(2000, 1000)
        )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(llm.anthropic, "Anthropic", fake_client(respond))

    result = call_anthropic_api("system", "prompt", Answer, "claude-haiku-5-5")

    assert result.data == {"text": "hi"}
    assert seen["output_format"] is Answer and seen["system"] == "system"
    assert result.cost_usd == pytest.approx((2000 * 0.10 + 1000 * 0.50) / 1_000_000)


def test_api_provider_treats_a_refusal_as_an_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(
        llm.anthropic,
        "Anthropic",
        fake_client(lambda r: SimpleNamespace(stop_reason="refusal", parsed_output=None, usage=usage(1, 0))),
    )
    with pytest.raises(LLMError, match="refusal"):
        call_anthropic_api("s", "p", Answer, "claude-haiku-5-5")


def test_api_provider_needs_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        call_anthropic_api("s", "p", Answer, "claude-haiku-5-5")


def test_missing_cli_is_a_clear_error(monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", "/nowhere/claude")
    with pytest.raises(LLMError, match="FORGE_LLM_PROVIDER=anthropic"):
        call_claude_cli("s", "p", Answer.model_json_schema(), "claude-haiku-5-5")


def test_results_are_cached_by_prompt_and_schema(monkeypatch, tmp_path):
    calls = []

    def fake_cli(system, prompt, schema, model):
        calls.append(prompt)
        return llm.LLMResult({"text": prompt}, model, 1, 1, 0.001, 10)

    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "PROVIDER", "claude-cli")
    monkeypatch.setattr(llm, "call_claude_cli", fake_cli)

    first = complete_json("s", "one", Answer, "m")
    again = complete_json("s", "one", Answer, "m")
    other = complete_json("s", "two", Answer, "m")

    assert calls == ["one", "two"]
    assert (first.cached, again.cached, other.cached) == (False, True, False)
    assert again.cost_usd == 0.001  # the original call's estimate is kept
