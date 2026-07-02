"""Offline OpenRouter adapter protocol tests."""

from types import SimpleNamespace

import pytest

from loop_engine.llm_client import LLMClient, OpenRouterClient, TokenPricing


class FakeCompletions:
    async def create(self, **kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="protocol-ok")
                )
            ],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5),
        )


def make_client():
    client = object.__new__(OpenRouterClient)
    LLMClient.__init__(client)
    client.api_key = "not-a-real-key"
    client.default_model = "test/model"
    client.provider_name = "openrouter"
    client.pricing = TokenPricing(1.0, 2.0)
    client.client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    return client


@pytest.mark.asyncio
async def test_openrouter_uses_compatible_protocol_and_records_usage():
    client = make_client()

    text = await client.generate("hello")

    assert text == "protocol-ok"
    assert client.total_tokens == 25
    assert client.total_cost == pytest.approx(0.00003)
    assert client.usage_records[0].provider == "openrouter"
    assert client.usage_records[0].model == "test/model"


def test_openrouter_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="API key required"):
        OpenRouterClient(api_key=None, model="test/model")


def test_openrouter_requires_explicit_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    with pytest.raises(ValueError, match="model required"):
        OpenRouterClient(api_key="not-a-real-key", model=None)
