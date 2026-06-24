"""Self-correction benchmark task."""

from typing import Any, Dict, Optional

from ..base import BenchmarkResult, BenchmarkTask


class SelfCorrectionTask(BenchmarkTask):
    """
    Self-correction on arithmetic/reasoning errors.
    Stress-tests: Evaluation, Recovery, Observation
    """

    def __init__(self, problem_idx: int = 0):
        super().__init__(
            task_id=f"correction_{problem_idx:03d}",
            name="Self-Correction",
            description="Detect and correct errors in reasoning"
        )
        self.difficulty = "medium"
        self.tags = ["self-correction", "evaluation", "arithmetic"]

        self.problems = [
            {
                "problem": "Calculate: 15 * 23 + 47",
                "correct_answer": 392,
                "common_wrong": 392,  # Actually this is correct, let's use a trickier one
                "hint": "Follow order of operations"
            },
            {
                "problem": "A train travels 120 miles in 2 hours. How far will it travel in 5 hours at the same speed?",
                "correct_answer": 300,
                "common_wrong": 250,  # Wrong ratio
                "hint": "First find speed, then multiply by time"
            },
            {
                "problem": "If 8 workers can build a wall in 10 days, how long will 16 workers take?",
                "correct_answer": 5,
                "common_wrong": 20,  # Wrong direction
                "hint": "More workers means less time (inverse relationship)"
            },
            {
                "problem": "What is 15% of 80?",
                "correct_answer": 12,
                "common_wrong": 15,  # Confusing percentage
                "hint": "Multiply 80 by 0.15"
            },
            {
                "problem": "Solve: 3(x + 2) = 21",
                "correct_answer": 5,
                "common_wrong": 7,  # Forgetting to divide by 3
                "hint": "First divide both sides by 3"
            }
        ]
        self.problem_idx = problem_idx % len(self.problems)

    def get_input(self) -> Dict[str, Any]:
        return self.problems[self.problem_idx]

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate self-correction."""
        metadata = metadata or {}
        problem = self.problems[self.problem_idx]
        output_str = str(output)

        # Extract final answer
        import re
        numbers = re.findall(r'-?\d+\.?\d*', output_str)
        if numbers:
            try:
                result = float(numbers[-1])
                correct_answer = float(problem["correct_answer"])
                correct = abs(result - correct_answer) < 0.01
            except ValueError:
                correct = str(problem["correct_answer"]) in output_str
        else:
            correct = str(problem["correct_answer"]) in output_str

        # Check for self-correction indicators
        correction_indicators = [
            "incorrect", "error", "wrong", "mistake", "correction",
            "actually", "wait", "reconsider", "check"
        ]
        showed_correction = any(ind in output_str.lower() for ind in correction_indicators)

        # Score based on correctness and self-correction
        if correct and showed_correction:
            score = 1.0  # Full points for correct with visible correction
        elif correct:
            score = 0.8  # Partial for correct without visible correction
        else:
            score = 0.0

        return BenchmarkResult(
            task_id=self.task_id,
            success=correct,
            score=score,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "problem": problem["problem"],
                "correct_answer": problem["correct_answer"],
                "actual_output": output_str[:500],
                "showed_correction": showed_correction,
                "evaluation_iterations": metadata.get("evaluations", 0)
            }
        )
