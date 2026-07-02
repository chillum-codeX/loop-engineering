"""Provider-neutral usage and budget accounting tests."""

import pytest

from baselines.one_shot import OneShotBaseline
from loop_engine import ScriptedLLMClient, TokenPricing
from loop_engine.components import LLMActor
from loop_engine.core import LoopEngine
from loop_engine.types import Budget, ComponentType


@pytest.mark.asyncio
async def test_scripted_provider_records_exact_usage():
    client = ScriptedLLMClient(
        ["answer"],
        input_tokens_per_call=12,
        output_tokens_per_call=4,
        cost_per_call=0.25,
    )

    assert await client.generate("question") == "answer"
    assert client.total_tokens == 16
    assert client.total_cost == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_baseline_uses_provider_usage_not_character_count():
    client = ScriptedLLMClient(
        ["Charlie"],
        input_tokens_per_call=7,
        output_tokens_per_call=2,
        cost_per_call=0.01,
    )
    result = await OneShotBaseline(client, model="scripted").solve(
        {"question": "Who is shortest?"}
    )

    assert result["token_usage"] == 9
    assert result["cost"] == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_registered_provider_updates_active_loop_budget():
    client = ScriptedLLMClient(
        ["ok"],
        input_tokens_per_call=5,
        output_tokens_per_call=3,
        cost_per_call=0.02,
    )
    engine = LoopEngine()
    engine.register_component(ComponentType.ACTOR, LLMActor(client, "scripted"))
    engine.budget = Budget(max_tokens=100, max_cost=1.0)

    await client.generate("work")

    assert engine.budget.tokens_used == 8
    assert engine.budget.cost_used == pytest.approx(0.02)


def test_explicit_pricing_calculates_cost_without_stale_global_prices():
    pricing = TokenPricing(input_per_million=3.0, output_per_million=15.0)

    assert pricing.cost(1_000_000, 100_000) == pytest.approx(4.5)
