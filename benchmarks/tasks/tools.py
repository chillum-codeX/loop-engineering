"""Tool use with recovery benchmark task."""

import random
from typing import Any, Callable, Dict, Optional

from ..base import BenchmarkResult, BenchmarkTask


class FailingTool:
    """Tool that fails initially then succeeds."""

    def __init__(self, fail_count: int = 1):
        self.fail_count = fail_count
        self.attempts = 0

    def __call__(self, *args, **kwargs):
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise RuntimeError(f"Tool failed (attempt {self.attempts})")
        return f"Success after {self.attempts} attempts"


class CalculatorTool:
    """Simple calculator tool."""

    def __call__(self, expression: str) -> str:
        try:
            # Safe evaluation
            allowed = {"sum": sum, "range": range, "len": len}
            result = eval(expression, {"__builtins__": {}}, allowed)
            return str(result)
        except Exception as e:
            return f"Error: {e}"


class ToolUseRecoveryTask(BenchmarkTask):
    """
    Tool use with error recovery.
    Stress-tests: Recovery, Error handling, Tool use
    """

    def __init__(self, fail_probability: float = 0.3):
        super().__init__(
            task_id="tools_001",
            name="Tool Use with Recovery",
            description="Use tools that may fail and recover from errors"
        )
        self.difficulty = "medium"
        self.tags = ["tools", "recovery", "error-handling"]
        self.fail_probability = fail_probability

        # Prime numbers between 1-100
        self.primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47,
                       53, 59, 61, 67, 71, 73, 79, 83, 89, 97]
        self.expected_sum = sum(self.primes)

    def get_input(self) -> Dict[str, Any]:
        return {
            "task": "Calculate the sum of all prime numbers between 1 and 100",
            "tools": {
                "calculator": CalculatorTool(),
                "failing_calculator": FailingTool(fail_count=1)
            },
            "expected_sum": self.expected_sum
        }

    def get_tools(self) -> Dict[str, Callable]:
        """Get tools for this task."""
        return {
            "calculator": CalculatorTool(),
            "failing_calculator": FailingTool(fail_count=1)
        }

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate tool use."""
        metadata = metadata or {}
        output_str = str(output)

        # Extract number from output
        import re
        numbers = re.findall(r'\d+', output_str)
        if numbers:
            try:
                result = int(numbers[-1])  # Take last number
                correct = result == self.expected_sum
            except ValueError:
                correct = False
        else:
            correct = False

        # Check for recovery indicators
        recovery_indicators = ["retry", "attempt", "again", "recover", "failed"]
        showed_recovery = any(ind in output_str.lower() for ind in recovery_indicators)

        # Bonus for showing recovery behavior
        score = 1.0 if correct else 0.0
        if correct and showed_recovery:
            score = 1.0  # Full credit for correct with recovery

        return BenchmarkResult(
            task_id=self.task_id,
            success=correct,
            score=score,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "expected_sum": self.expected_sum,
                "actual_output": output_str[:500],
                "recovery_used": metadata.get("recovery_used", False),
                "failures_encountered": metadata.get("failures", 0)
            }
        )
