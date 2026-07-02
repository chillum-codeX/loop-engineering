"""Budget-capped live provider smoke test with redacted evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from loop_engine.llm_client import LLMClient, create_llm_client


EXPECTED = "LOOP_ENGINE_LIVE_OK"


async def run_smoke(client: LLMClient, model: str) -> Dict[str, Any]:
    text = await client.generate(
        f"Reply with exactly {EXPECTED} and nothing else.",
        model=model,
        temperature=0.0,
        max_tokens=32,
    )
    normalized = text.strip()
    usage = client.usage_records[-1]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "provider": usage.provider,
        "model": usage.model,
        "passed": normalized == EXPECTED,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "reported_cost_usd": usage.cost,
        "response_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "response_stored": False,
        "max_output_tokens": 32,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["openrouter"], default="openrouter")
    parser.add_argument(
        "--output",
        default="experiments/results/live_provider_smoke.json",
    )
    args = parser.parse_args()

    if args.provider == "openrouter":
        model = os.environ.get("OPENROUTER_MODEL")
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise SystemExit("OPENROUTER_API_KEY is not configured")
        if not model:
            raise SystemExit("OPENROUTER_MODEL is not configured")
    else:
        raise SystemExit(f"Unsupported provider: {args.provider}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = await run_smoke(
            create_llm_client(args.provider, model=model),
            model,
        )
    except Exception as exc:
        result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": args.provider,
            "model": model,
            "passed": False,
            "error_type": type(exc).__name__,
            "error_details_stored": False,
            "credentials_stored": False,
            "max_output_tokens": 32,
        }
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        raise SystemExit(1) from None
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
