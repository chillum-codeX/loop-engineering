"""Multi-agent coordination benchmark task."""

from typing import Any, Dict, List, Optional

from ..base import BenchmarkResult, BenchmarkTask


class MultiAgentCoordinationTask(BenchmarkTask):
    """
    Multi-agent coordination with consensus.
    Stress-tests: Multi-agent, Communication, Consensus
    """

    def __init__(self):
        super().__init__(
            task_id="multiagent_001",
            name="Multi-Agent Coordination",
            description="Coordinate multiple agents to reach consensus"
        )
        self.difficulty = "hard"
        self.tags = ["multi-agent", "coordination", "consensus"]

        self.topics = [
            {
                "topic": "best sorting algorithm",
                "options": ["quicksort", "mergesort", "heapsort", "timsort"],
                "criteria": ["time complexity", "space complexity", "stability"]
            },
            {
                "topic": "optimal database for analytics",
                "options": ["PostgreSQL", "ClickHouse", "BigQuery", "Snowflake"],
                "criteria": ["query speed", "scalability", "cost"]
            }
        ]

    def get_input(self) -> Dict[str, Any]:
        return {
            "task": "Reach consensus on the best option",
            "topic": self.topics[0],
            "agents": ["researcher", "evaluator", "synthesizer"],
            "require_consensus": True
        }

    def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
        """Evaluate multi-agent coordination."""
        metadata = metadata or {}
        output_str = str(output).lower()
        topic = self.topics[0]

        # Check if consensus was reached
        consensus_indicators = ["consensus", "agree", "conclusion", "decision", "recommend"]
        reached_consensus = any(ind in output_str for ind in consensus_indicators)

        # Check if a valid option was selected
        selected_option = None
        for option in topic["options"]:
            if option.lower() in output_str:
                selected_option = option
                break

        # Check for consideration of criteria
        criteria_considered = sum(1 for c in topic["criteria"] if c.lower() in output_str)
        criteria_score = criteria_considered / len(topic["criteria"])

        # Score
        if reached_consensus and selected_option:
            score = 0.5 + (criteria_score * 0.5)  # Base 0.5 for consensus, up to 1.0 for criteria
        elif selected_option:
            score = 0.3 + (criteria_score * 0.3)  # Partial for selection
        else:
            score = criteria_score * 0.3  # Only criteria points

        return BenchmarkResult(
            task_id=self.task_id,
            success=reached_consensus and selected_option is not None,
            score=score,
            execution_time=metadata.get("execution_time", 0.0),
            iterations=metadata.get("iterations", 1),
            token_usage=metadata.get("token_usage", 0),
            cost=metadata.get("cost", 0.0),
            metadata={
                "topic": topic["topic"],
                "reached_consensus": reached_consensus,
                "selected_option": selected_option,
                "criteria_considered": criteria_considered,
                "total_criteria": len(topic["criteria"]),
                "agent_messages": metadata.get("agent_messages", 0)
            }
        )
