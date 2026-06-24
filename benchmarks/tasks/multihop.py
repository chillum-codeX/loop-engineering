"""Multi-hop reasoning benchmark task."""

import re
import time
from typing import Any, Dict, Optional

from ..base import BenchmarkResult, BenchmarkTask


class MultiHopReasoningTask(BenchmarkTask):
    """
    Multi-hop reasoning task requiring verification.
    Stress-tests: Planning, Verification, Recovery
    """

    def __init__(self, question_idx: int = 0):
        super().__init__(
            task_id=f"multihop_{question_idx:03d}",
            name="Multi-Hop Reasoning",
            description="Answer questions requiring multiple reasoning steps with verification"
        )
        self.difficulty = "hard"
        self.tags = ["reasoning", "verification", "multi-step"]

        self.questions = [
            {
                "question": "If Alice is taller than Bob, and Bob is taller than Charlie, who is the shortest?",
                "answer": "Charlie",
                "keywords": ["charlie"]
            },
            {
                "question": "The capital of France is Paris. Paris is on the Seine river. The Seine flows into the English Channel. What body of water is Paris connected to?",
                "answer": "English Channel",
                "keywords": ["english channel", "channel"]
            },
            {
                "question": "A bat and ball cost $11 total. The bat costs $10 more than the ball. How much does the ball cost?",
                "answer": "0.50",
                "keywords": ["0.5", "50 cent", "half", "$0.50"]
            },
            {
                "question": "If it takes 5 machines 5 minutes to make 5 widgets, how long does it take 100 machines to make 100 widgets?",
                "answer": "5 minutes",
                "keywords": ["5", "five"]
            },
            {
                "question": "In a lake, there is a patch of lily pads. Every day, the patch doubles in size. If it takes 48 days for the patch to cover the entire lake, how long would it take for the patch to cover half of the lake?",
                "answer": "47 days",
                "keywords": ["47"]
            }
        ]
        self.question_idx = question_idx % len(self.questions)

    def get_input(self) -> Dict[str, Any]:
        return self.questions[self.question_idx]

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate the answer."""
        metadata = metadata or {}
        question = self.questions[self.question_idx]
        answer = str(output).lower()

        # Check for correct answer or keywords
        correct = question["answer"].lower() in answer
        if not correct:
            for keyword in question["keywords"]:
                if keyword.lower() in answer:
                    correct = True
                    break

        # Check for common errors (for the bat and ball problem)
        if "10" in answer and question["answer"] == "0.50":
            correct = False  # Common wrong answer

        # Check for "47" vs "48" (for lily pad problem)
        if "48" in answer and "47" not in answer and question["answer"] == "47 days":
            correct = False  # Common wrong answer

        return BenchmarkResult(
            task_id=self.task_id,
            success=correct,
            score=1.0 if correct else 0.0,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "question": question["question"],
                "expected": question["answer"],
                "actual": str(output)[:500],
                "verification_passed": metadata.get("verification_passed", None)
            }
        )

    def get_expected_output(self) -> str:
        return self.questions[self.question_idx]["answer"]
