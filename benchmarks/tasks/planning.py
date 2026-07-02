"""Long-horizon planning benchmark task."""

from typing import Any, Dict, Optional

from ..base import BenchmarkResult, BenchmarkTask


class LongHorizonPlanningTask(BenchmarkTask):
    """
    Long-horizon planning task with dependency tracking.
    Stress-tests: Planning, Memory, Termination
    """

    def __init__(self, scenario_idx: int = 0):
        super().__init__(
            task_id=f"planning_{scenario_idx:03d}",
            name="Long-Horizon Planning",
            description="Create and execute a multi-step plan with dependencies"
        )
        self.difficulty = "hard"
        self.tags = ["planning", "dependencies", "long-horizon"]

        self.scenarios = [
            {
                "goal": "Organize a surprise birthday party",
                "constraints": ["Must keep it secret", "Budget $500", "30 guests"],
                "expected_steps": 6,
                "key_elements": ["guest list", "venue", "cake", "invitation", "activities"]
            },
            {
                "goal": "Deploy a web application with zero downtime",
                "constraints": ["Zero downtime", "Rollback capability", "Monitor health"],
                "expected_steps": 5,
                "key_elements": ["test", "staging", "rollback", "deploy", "monitor"]
            },
            {
                "goal": "Write a research paper",
                "constraints": ["Peer-reviewed", "Novel contribution", "Reproducible"],
                "expected_steps": 7,
                "key_elements": ["research", "experiment", "write", "review", "revise"]
            }
        ]
        self.scenario_idx = scenario_idx % len(self.scenarios)

    def get_input(self) -> Dict[str, Any]:
        return self.scenarios[self.scenario_idx]

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate the plan quality."""
        metadata = metadata or {}
        scenario = self.scenarios[self.scenario_idx]
        output_str = str(output).lower()

        # Score based on key elements present
        key_elements = scenario["key_elements"]
        elements_found = sum(1 for elem in key_elements if elem.lower() in output_str)
        element_score = elements_found / len(key_elements)

        # Check for reasonable number of steps
        plan_steps = metadata.get("plan_steps", 0) if output_str.strip() else 0
        if plan_steps == 0:
            # Try to count steps from output
            step_indicators = ["step", "1.", "2.", "3.", "- ", "* "]
            plan_steps = sum(output_str.count(ind.lower()) for ind in step_indicators)

        step_score = min(1.0, plan_steps / scenario["expected_steps"]) if scenario["expected_steps"] > 0 else 0.5

        # Combined score
        score = (element_score * 0.7 + step_score * 0.3) if output_str.strip() else 0.0
        success = score >= 0.5

        return BenchmarkResult(
            task_id=self.task_id,
            success=success,
            score=score,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "goal": scenario["goal"],
                "elements_found": elements_found,
                "total_elements": len(key_elements),
                "plan_steps": plan_steps,
                "expected_steps": scenario["expected_steps"]
            }
        )
