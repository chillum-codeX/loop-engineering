"""Deterministic benchmark-evaluator validation.

This suite validates benchmark scoring with oracle and empty negative-control
outputs. It does not claim model quality and performs no network calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from benchmarks.tasks.budget import BudgetConstrainedTask
from benchmarks.tasks.correction import SelfCorrectionTask
from benchmarks.tasks.memory import MemoryIntensiveTask
from benchmarks.tasks.multiagent import MultiAgentCoordinationTask
from benchmarks.tasks.multihop import MultiHopReasoningTask
from benchmarks.tasks.planning import LongHorizonPlanningTask
from benchmarks.tasks.tools import ToolUseRecoveryTask


def cases() -> List[Tuple[Any, Any, Dict[str, Any]]]:
    return [
        (MultiHopReasoningTask(0), "Charlie", {}),
        (
            LongHorizonPlanningTask(0),
            "1. guest list 2. venue 3. cake 4. invitations 5. activities 6. execute",
            {"plan_steps": 6},
        ),
        (ToolUseRecoveryTask(), "Recovered after retry. Result: 1060", {}),
        (SelfCorrectionTask(2), "After checking the inverse ratio, the answer is 5.", {}),
        (BudgetConstrainedTask(), "1000", {"iterations": 1, "token_usage": 20}),
        (
            MemoryIntensiveTask(),
            "senior software engineer; 5; MIT; Tesla Model 3; blue; Seattle; Friday; 8",
            {},
        ),
        (
            MultiAgentCoordinationTask(),
            "Consensus decision: recommend timsort after considering time complexity, "
            "space complexity, and stability.",
            {},
        ),
    ]


def run_suite() -> Dict[str, Any]:
    results = []
    for task, oracle, metadata in cases():
        positive = task.evaluate(oracle, metadata)
        negative = task.evaluate("", metadata)
        results.append(
            {
                "task_id": task.task_id,
                "oracle_passed": positive.success,
                "oracle_score": positive.score,
                "negative_rejected": not negative.success and negative.score == 0.0,
                "negative_score": negative.score,
            }
        )
    return {
        "suite": "benchmark_evaluator_validation",
        "network_calls": 0,
        "claims_model_performance": False,
        "all_oracles_passed": all(item["oracle_passed"] for item in results),
        "all_negative_controls_rejected": all(
            item["negative_rejected"] for item in results
        ),
        "results": results,
    }


def main(output: str = "experiments/results/deterministic_validation.json") -> None:
    result = run_suite()
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["all_oracles_passed"] or not result["all_negative_controls_rejected"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
