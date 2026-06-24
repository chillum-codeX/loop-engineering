"""Benchmark suite for Loop Engineering Framework."""

from .tasks import (
    MultiHopReasoningTask,
    LongHorizonPlanningTask,
    ToolUseRecoveryTask,
    SelfCorrectionTask,
    BudgetConstrainedTask,
    MultiAgentCoordinationTask,
    MemoryIntensiveTask,
)

__all__ = [
    "MultiHopReasoningTask",
    "LongHorizonPlanningTask",
    "ToolUseRecoveryTask",
    "SelfCorrectionTask",
    "BudgetConstrainedTask",
    "MultiAgentCoordinationTask",
    "MemoryIntensiveTask",
]
