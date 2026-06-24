"""Budget-constrained optimization benchmark task."""

from typing import Any, Dict, List, Optional

from ..base import BenchmarkResult, BenchmarkTask


class BudgetConstrainedTask(BenchmarkTask):
    """
    Budget-constrained optimization task.
    Stress-tests: Budget controls, Efficiency, Termination
    """

    def __init__(self, max_steps: int = 10, max_tokens: int = 500):
        super().__init__(
            task_id=f"budget_{max_steps:02d}",
            name="Budget-Constrained Optimization",
            description="Solve a problem within strict resource constraints"
        )
        self.difficulty = "hard"
        self.tags = ["budget", "optimization", "constraints"]
        self.max_steps = max_steps
        self.max_tokens = max_tokens

        # Generate test data - maximum at position 0
        self.numbers = list(range(1000, 0, -1))  # 1000, 999, 998, ...
        self.correct_answer = 1000  # Maximum value

    def get_input(self) -> Dict[str, Any]:
        return {
            "problem": f"Find the maximum value in a list of {len(self.numbers)} numbers within limited budget",
            "budget": {"max_tokens": self.max_tokens, "max_steps": self.max_steps},
            "hint": "The maximum is near the beginning of the list",
            "numbers_sample": self.numbers[:20]  # Show sample, not full list
        }

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate budget-constrained execution."""
        metadata = metadata or {}
        output_str = str(output)

        # Extract answer
        import re
        numbers = re.findall(r'\d+', output_str)
        if numbers:
            try:
                result = int(numbers[-1])
                correct = result == self.correct_answer
            except ValueError:
                correct = False
        else:
            correct = False

        # Calculate efficiency score
        steps_used = metadata.get("iterations", 1)
        tokens_used = metadata.get("token_usage", 0)

        # Ideal: find answer in 1 step, minimal tokens
        step_efficiency = max(0, 1.0 - (steps_used / self.max_steps))
        token_efficiency = max(0, 1.0 - (tokens_used / self.max_tokens)) if self.max_tokens > 0 else 0

        # Combined score: correctness weighted heavily, efficiency bonus
        correctness_score = 1.0 if correct else 0.0
        efficiency_bonus = (step_efficiency * 0.1 + token_efficiency * 0.1)

        score = correctness_score * 0.8 + efficiency_bonus

        # Success if correct, regardless of efficiency
        success = correct

        return BenchmarkResult(
            task_id=self.task_id,
            success=success,
            score=min(1.0, score),
            execution_time=metadata.get("execution_time", 0.0),
            iterations=steps_used,
            token_usage=tokens_used,
            cost=metadata.get("cost", 0.0),
            metadata={
                "correct_answer": self.correct_answer,
                "steps_allowed": self.max_steps,
                "tokens_allowed": self.max_tokens,
                "step_efficiency": step_efficiency,
                "token_efficiency": token_efficiency,
                "budget_exhausted": metadata.get("budget_exhausted", False)
            }
        )
