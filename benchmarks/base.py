"""
Base classes for benchmark tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class BenchmarkResult:
    """Result of a benchmark task execution."""
    task_id: str
    success: bool
    score: float  # 0.0 to 1.0
    execution_time: float
    iterations: int
    token_usage: int
    cost: float
    metadata: Dict[str, Any]
    error: Optional[str] = None


class BenchmarkTask(ABC):
    """Abstract base class for benchmark tasks."""

    def __init__(self, task_id: str, name: str, description: str):
        self.task_id = task_id
        self.name = name
        self.description = description
        self.difficulty = "medium"
        self.tags: List[str] = []

    @abstractmethod
    def get_input(self) -> Dict[str, Any]:
        """Get the input for this task."""
        pass

    @abstractmethod
    def evaluate(self, output: Any) -> BenchmarkResult:
        """Evaluate the output of a system on this task."""
        pass

    def get_expected_output(self) -> Any:
        """Get the expected/correct output (if applicable)."""
        return None


class MultiHopReasoningTask(BenchmarkTask):
    """
    Multi-hop reasoning task requiring verification.

    Stress-tests: Planning, Verification, Recovery
    """

    def __init__(self):
        super().__init__(
            task_id="multihop_001",
            name="Multi-Hop Reasoning",
            description="Answer questions requiring multiple reasoning steps with verification"
        )
        self.difficulty = "hard"
        self.tags = ["reasoning", "verification", "multi-step"]

        # Sample questions requiring multi-hop reasoning
        self.questions = [
            {
                "question": "If Alice is taller than Bob, and Bob is taller than Charlie, who is the shortest?",
                "answer": "Charlie",
                "hops": [("Alice > Bob", "given"), ("Bob > Charlie", "given"), ("Therefore Alice > Charlie", "inference")]
            },
            {
                "question": "The capital of France is Paris. Paris is on the Seine river. The Seine flows into the English Channel. What body of water is Paris connected to?",
                "answer": "English Channel",
                "hops": [("Paris is capital of France", "given"), ("Paris is on Seine", "given"), ("Seine flows to English Channel", "given")]
            },
            {
                "question": "A bat and ball cost $11 total. The bat costs $10 more than the ball. How much does the ball cost?",
                "answer": "0.50",
                "hops": [("Let ball = x", "setup"), ("Bat = x + 10", "setup"), ("x + (x + 10) = 11", "equation"), ("2x = 1", "solve"), ("x = 0.50", "solution")]
            }
        ]

    def get_input(self) -> Dict[str, Any]:
        """Get a random question from the set."""
        import random
        return random.choice(self.questions)

    def evaluate(self, output: Any, expected: Optional[str] = None) -> BenchmarkResult:
        """Evaluate the answer."""
        # This will be implemented with actual execution results
        pass


class LongHorizonPlanningTask(BenchmarkTask):
    """
    Long-horizon planning task with dependency tracking.

    Stress-tests: Planning, Memory, Termination
    """

    def __init__(self):
        super().__init__(
            task_id="planning_001",
            name="Long-Horizon Planning",
            description="Create and execute a multi-step plan with dependencies"
        )
        self.difficulty = "hard"
        self.tags = ["planning", "dependencies", "long-horizon"]

        self.scenarios = [
            {
                "goal": "Organize a surprise birthday party",
                "constraints": ["Must keep it secret", "Budget $500", "30 guests"],
                "expected_steps": ["Create guest list", "Book venue", "Order cake", "Send invitations", "Plan activities", "Execute party"]
            },
            {
                "goal": "Deploy a web application",
                "constraints": ["Zero downtime", "Rollback capability", "Monitor health"],
                "expected_steps": ["Test in staging", "Prepare rollback", "Deploy to production", "Monitor metrics", "Verify health"]
            }
        ]

    def get_input(self) -> Dict[str, Any]:
        import random
        return random.choice(self.scenarios)

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass


class ToolUseRecoveryTask(BenchmarkTask):
    """
    Tool use with error recovery.

    Stress-tests: Recovery, Error handling, Tool use
    """

    def __init__(self):
        super().__init__(
            task_id="tool_001",
            name="Tool Use with Recovery",
            description="Use tools that may fail and recover from errors"
        )
        self.difficulty = "medium"
        self.tags = ["tools", "recovery", "error-handling"]

    def get_input(self) -> Dict[str, Any]:
        return {
            "task": "Calculate the sum of all prime numbers between 1 and 100",
            "tools": ["calculator", "prime_checker"],
            "injection_failures": True  # Some tools will fail initially
        }

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass


class SelfCorrectionTask(BenchmarkTask):
    """
    Self-correction on arithmetic/reasoning errors.

    Stress-tests: Evaluation, Recovery, Observation
    """

    def __init__(self):
        super().__init__(
            task_id="correction_001",
            name="Self-Correction",
            description="Detect and correct errors in reasoning"
        )
        self.difficulty = "medium"
        self.tags = ["self-correction", "evaluation", "arithmetic"]

        self.problems = [
            {
                "problem": "Calculate: 15 * 23 + 47",
                "correct_answer": 392,
                "common_error": "Incorrect order of operations or calculation error"
            },
            {
                "problem": "A train travels 120 miles in 2 hours. How far will it travel in 5 hours at the same speed?",
                "correct_answer": 300,
                "common_error": "Wrong unit conversion or ratio error"
            },
            {
                "problem": "If 8 workers can build a wall in 10 days, how long will 16 workers take?",
                "correct_answer": 5,
                "common_error": "Inverse proportion error (answering 20 instead of 5)"
            }
        ]

    def get_input(self) -> Dict[str, Any]:
        import random
        return random.choice(self.problems)

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass


class BudgetConstrainedTask(BenchmarkTask):
    """
    Budget-constrained optimization task.

    Stress-tests: Budget controls, Efficiency, Termination
    """

    def __init__(self):
        super().__init__(
            task_id="budget_001",
            name="Budget-Constrained Optimization",
            description="Solve a problem within strict resource constraints"
        )
        self.difficulty = "hard"
        self.tags = ["budget", "optimization", "constraints"]

    def get_input(self) -> Dict[str, Any]:
        return {
            "problem": "Find the maximum value in a list of 1000 numbers with limited token budget",
            "budget": {"max_tokens": 500, "max_steps": 10},
            "numbers": list(range(1000, 0, -1))  # Descending, max at start
        }

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass


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

    def get_input(self) -> Dict[str, Any]:
        return {
            "task": "Reach consensus on the best algorithm for sorting",
            "agents": ["researcher", "evaluator", "implementer"],
            "require_consensus": True
        }

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass


class MemoryIntensiveTask(BenchmarkTask):
    """
    Memory-intensive task requiring information consolidation.

    Stress-tests: Memory systems, Consolidation, Long-horizon
    """

    def __init__(self):
        super().__init__(
            task_id="memory_001",
            name="Memory-Intensive Task",
            description="Accumulate and consolidate information over many steps"
        )
        self.difficulty = "hard"
        self.tags = ["memory", "consolidation", "long-horizon"]

    def get_input(self) -> Dict[str, Any]:
        # Generate a story with facts to remember
        story_parts = [
            "Alice works at TechCorp as an engineer.",
            "She has a dog named Max who is 5 years old.",
            "Her favorite color is blue.",
            "She lives in Seattle.",
            "She graduated from MIT in 2019.",
            "Her project deadline is next Friday.",
            "She needs to call her mom tomorrow.",
            "She bought a new car last month - a Tesla."
        ]

        questions = [
            "What is Alice's job?",
            "How old is her dog?",
            "Where did she graduate?",
            "What car did she buy?"
        ]

        return {
            "story_parts": story_parts,
            "questions": questions,
            "expected_answers": ["engineer at TechCorp", "5 years old", "MIT in 2019", "Tesla"]
        }

    def evaluate(self, output: Any) -> BenchmarkResult:
        pass
