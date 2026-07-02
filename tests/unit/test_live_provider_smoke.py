"""The live smoke harness is tested offline with a scripted provider."""

import pytest

from experiments.live_provider_smoke import run_smoke
from loop_engine import ScriptedLLMClient


@pytest.mark.asyncio
async def test_live_smoke_evidence_is_redacted_and_budget_capped():
    client = ScriptedLLMClient(
        ["LOOP_ENGINE_LIVE_OK"],
        input_tokens_per_call=8,
        output_tokens_per_call=4,
        cost_per_call=0.001,
    )

    result = await run_smoke(client, "scripted/test")

    assert result["passed"] is True
    assert result["total_tokens"] == 12
    assert result["reported_cost_usd"] == pytest.approx(0.001)
    assert result["response_stored"] is False
    assert "LOOP_ENGINE_LIVE_OK" not in str(result)
