"""
Core type definitions for the Loop Engineering Framework.

This module defines all data types, enums, and data classes used throughout
the framework, ensuring type safety and clear interfaces between components.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar, Union


class LoopStatus(Enum):
    """Status of a loop execution."""
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    TERMINATED = auto()
    RECOVERING = auto()


class ComponentType(Enum):
    """Types of loop components."""
    PLANNER = "planner"
    ACTOR = "actor"
    OBSERVER = "observer"
    EVALUATOR = "evaluator"
    RECOVERY = "recovery"
    TERMINATOR = "terminator"


class ExecutionMode(Enum):
    """Execution modes for the loop engine."""
    SINGLE_AGENT = auto()
    MULTI_AGENT = auto()
    HIERARCHICAL = auto()


class MemoryType(Enum):
    """Types of memory in the system."""
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    CONSOLIDATED = "consolidated"


class FailureType(Enum):
    """Types of failures that can occur in loop execution."""
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    INVALID_OUTPUT = "invalid_output"
    VERIFICATION_FAILED = "verification_failed"
    SEMANTIC_DRIFT = "semantic_drift"
    EXECUTION_ERROR = "execution_error"
    PLANNING_FAILURE = "planning_failure"
    GOAL_HIJACKING = "goal_hijacking"
    RECOVERY_EXHAUSTED = "recovery_exhausted"


class RecoveryStrategy(Enum):
    """Strategies for recovering from failures."""
    RETRY = "retry"
    BACKOFF = "backoff"
    PLAN_REVISION = "plan_revision"
    HUMAN_HANDOFF = "human_handoff"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    CIRCUIT_BREAK = "circuit_break"


class ExecutionState(Enum):
    """Explicit execution states for the state machine."""
    INITIALIZED = "initialized"
    SPECIFYING = "specifying"
    PLANNING = "planning"
    ACTING = "acting"
    OBSERVING = "observing"
    EVALUATING = "evaluating"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    REPLANNING = "replanning"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    ABSTAINED = "abstained"
    BUDGET_EXHAUSTED = "budget_exhausted"
    POLICY_TERMINATED = "policy_terminated"
    FAILED = "failed"


class FailureStatus(Enum):
    """Lifecycle status for failures."""
    UNHANDLED = "unhandled"
    RECOVERY_PLANNED = "recovery_planned"
    RECOVERY_IN_PROGRESS = "recovery_in_progress"
    RECOVERED = "recovered"
    RECOVERY_FAILED = "recovery_failed"
    ESCALATED = "escalated"
    TERMINAL = "terminal"


@dataclass
class Step:
    """A single step in a plan."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, completed, failed
    output: Any = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """A plan composed of steps."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    steps: List[Step] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    version: int = 1

    def get_next_step(self) -> Optional[Step]:
        """Get the next pending step with satisfied dependencies."""
        completed_ids = {s.id for s in self.steps if s.status == "completed"}
        for step in self.steps:
            if step.status == "pending":
                if all(dep in completed_ids for dep in step.dependencies):
                    return step
        return None

    def get_progress(self) -> float:
        """Calculate plan completion progress (0.0 to 1.0)."""
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == "completed")
        return completed / len(self.steps)


@dataclass
class Observation:
    """An observation from the environment or execution."""
    timestamp: datetime = field(default_factory=datetime.now)
    content: Any = None
    source: str = "unknown"
    step_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Evaluation:
    """Evaluation of progress or quality."""
    score: float = 0.0  # 0.0 to 1.0
    passed: bool = False
    feedback: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Failure:
    """A failure event with lifecycle tracking."""
    type: FailureType = FailureType.EXECUTION_ERROR
    message: str = ""
    step_id: Optional[str] = None
    recoverable: bool = True
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    # Lifecycle tracking
    failure_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: FailureStatus = FailureStatus.UNHANDLED
    recovery_attempts: int = 0
    max_recovery_attempts: int = 3
    recovery_action_ids: List[str] = field(default_factory=list)
    source_component: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def can_recover(self) -> bool:
        """Check if this failure can still be recovered."""
        if not self.recoverable:
            return False
        if self.status in [FailureStatus.TERMINAL, FailureStatus.RECOVERY_FAILED]:
            return False
        return self.recovery_attempts < self.max_recovery_attempts

    def record_recovery_attempt(self, action_id: str) -> None:
        """Record a recovery attempt."""
        self.recovery_attempts += 1
        self.recovery_action_ids.append(action_id)
        if self.recovery_attempts >= self.max_recovery_attempts:
            self.status = FailureStatus.RECOVERY_FAILED
        else:
            self.status = FailureStatus.RECOVERY_IN_PROGRESS

    def mark_recovered(self) -> None:
        """Mark this failure as successfully recovered."""
        self.status = FailureStatus.RECOVERED
        self.recoverable = False

    def mark_terminal(self) -> None:
        """Mark this failure as terminal (cannot be recovered)."""
        self.status = FailureStatus.TERMINAL
        self.recoverable = False


@dataclass
class RecoveryAction:
    """A recovery action with explicit failure tracking."""
    strategy: RecoveryStrategy = RecoveryStrategy.RETRY
    params: Dict[str, Any] = field(default_factory=dict)
    estimated_success: float = 0.5
    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    failure_id: Optional[str] = None  # Links to Failure.failure_id
    timestamp: datetime = field(default_factory=datetime.now)
    executed: bool = False
    success: Optional[bool] = None


@dataclass
class Budget:
    """Budget constraints for execution."""
    max_tokens: Optional[int] = None
    max_steps: Optional[int] = None
    max_time_seconds: Optional[float] = None
    max_cost: Optional[float] = None

    def __post_init__(self):
        self.tokens_used: int = 0
        self.steps_used: int = 0
        self.time_used: float = 0.0
        self.cost_used: float = 0.0

    def check_budget(self) -> bool:
        """Check if budget is still within limits."""
        if self.max_tokens and self.tokens_used >= self.max_tokens:
            return False
        if self.max_steps and self.steps_used >= self.max_steps:
            return False
        if self.max_time_seconds and self.time_used >= self.max_time_seconds:
            return False
        if self.max_cost and self.cost_used >= self.max_cost:
            return False
        return True

    def remaining(self) -> Dict[str, Any]:
        """Get remaining budget."""
        return {
            "tokens": self.max_tokens - self.tokens_used if self.max_tokens else None,
            "steps": self.max_steps - self.steps_used if self.max_steps else None,
            "time": self.max_time_seconds - self.time_used if self.max_time_seconds else None,
            "cost": self.max_cost - self.cost_used if self.max_cost else None,
        }


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: Any = None
    memory_type: MemoryType = MemoryType.WORKING
    timestamp: datetime = field(default_factory=datetime.now)
    importance: float = 0.5  # 0.0 to 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: Set[str] = field(default_factory=set)


@dataclass
class LoopContext:
    """Context for loop execution."""
    goal: str = ""
    initial_context: Dict[str, Any] = field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.SINGLE_AGENT
    budget: Budget = field(default_factory=Budget)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopResult:
    """Result of a loop execution."""
    status: LoopStatus = LoopStatus.PENDING
    output: Any = None
    plan: Optional[Plan] = None
    iterations: int = 0
    execution_time: float = 0.0
    token_usage: int = 0
    cost: float = 0.0
    failures: List[Failure] = field(default_factory=list)
    recoveries: List[RecoveryAction] = field(default_factory=list)
    evaluations: List[Evaluation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationResult:
    """Result of verification."""
    verified: bool = False
    confidence: float = 0.0
    checks: List[Dict[str, Any]] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SafetyCheck:
    """A safety check result."""
    passed: bool = True
    check_type: str = ""
    severity: str = "info"  # info, warning, critical
    message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentMessage:
    """A message between agents in multi-agent mode."""
    sender: str = ""
    recipient: str = ""  # empty = broadcast
    content: Any = None
    message_type: str = "info"
    timestamp: datetime = field(default_factory=datetime.now)


# Type aliases for common patterns
T = TypeVar('T')
AsyncCallable = Callable[..., Any]
ComponentRegistry = Dict[ComponentType, Any]
