"""
Runtime Contracts Module

Phase 1: Canonical typed interfaces for Loop Runtime V1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from .types import Failure, RecoveryAction, LoopStatus


class RuntimePhase(Enum):
    """The five canonical phases of the Loop Runtime."""
    DISCOVERY = "discovery"
    HANDOFF = "handoff"
    VERIFICATION = "verification"
    PERSISTENCE = "persistence"
    SCHEDULING = "scheduling"


class DiscoveryStatus(Enum):
    """Status of the discovery phase."""
    IDLE = "idle"
    LOADING_STATE = "loading_state"
    LOADING_SKILLS = "loading_skills"
    EVALUATING_TRIGGERS = "evaluating_triggers"
    BUILDING_LEDGER = "building_ledger"
    SELECTING_TASK = "selecting_task"
    COMPLETE = "complete"
    NO_TASKS = "no_tasks"


class HandoffStatus(Enum):
    """Status of the handoff phase."""
    IDLE = "idle"
    RESERVING_BUDGET = "reserving_budget"
    CREATING_WORKTREE = "creating_worktree"
    SETUP_GENERATOR = "setup_generator"
    READY = "ready"
    FAILED = "failed"


class VerificationStatus(Enum):
    """Status of the verification phase."""
    IDLE = "idle"
    PRE_GATES = "pre_gates"
    GENERATING = "generating"
    POST_GATES = "post_gates"
    EVALUATING = "evaluating"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class PersistenceStatus(Enum):
    """Status of the persistence phase."""
    IDLE = "idle"
    SAVING_STATE = "saving_state"
    UPDATING_LEDGER = "updating_ledger"
    COMPLETE = "complete"


class SchedulingStatus(Enum):
    """Status of the scheduling phase."""
    IDLE = "idle"
    EVALUATING_QUEUE = "evaluating_queue"
    SCHEDULING_NEXT = "scheduling_next"
    COMPLETE = "complete"
    PAUSED = "paused"


class TaskStatus(Enum):
    """Lifecycle status of a task."""
    PENDING = "pending"
    DISCOVERED = "discovered"
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    COMMITTED = "committed"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Priority levels for task scheduling."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class TaskRecord:
    """A record of work to be done."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    skill_name: Optional[str] = None
    goal: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    status_history: List[Dict[str, Any]] = field(default_factory=list)
    discovered_at: Optional[datetime] = None
    reserved_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    budget_reservation_id: Optional[str] = None
    worktree_path: Optional[Path] = None

    def transition_to(self, new_status: TaskStatus, metadata: Optional[Dict] = None) -> None:
        """Transition task to new status with history tracking."""
        old_status = self.status
        self.status = new_status
        self.status_history.append({
            "from": old_status.value,
            "to": new_status.value,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        })
        if new_status == TaskStatus.RESERVED:
            self.reserved_at = datetime.now()
        elif new_status == TaskStatus.IN_PROGRESS:
            self.started_at = datetime.now()
        elif new_status in (TaskStatus.COMMITTED, TaskStatus.REJECTED, TaskStatus.ROLLED_BACK, TaskStatus.FAILED):
            self.completed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert task record to dictionary."""
        return {
            "task_id": self.task_id,
            "skill_name": self.skill_name,
            "goal": self.goal,
            "priority": self.priority.value,
            "status": self.status.value,
            "status_history": self.status_history,
        }


@dataclass
class TaskLedger:
    """The canonical task queue/ledger."""
    tasks: Dict[str, TaskRecord] = field(default_factory=dict)
    completed_task_ids: List[str] = field(default_factory=list)
    failed_task_ids: List[str] = field(default_factory=list)

    def add_task(self, task: TaskRecord) -> None:
        """Add a task to the ledger."""
        self.tasks[task.task_id] = task
        task.discovered_at = datetime.now()
        task.transition_to(TaskStatus.DISCOVERED)

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Get a task by ID."""
        return self.tasks.get(task_id)

    def get_pending_tasks(self) -> List[TaskRecord]:
        """Get all pending tasks sorted by priority."""
        pending = [
            t for t in self.tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.DISCOVERED)
        ]
        return sorted(pending, key=lambda t: t.priority.value)

    def get_active_tasks(self) -> List[TaskRecord]:
        """Get tasks currently in progress."""
        return [
            t for t in self.tasks.values()
            if t.status in (TaskStatus.IN_PROGRESS, TaskStatus.VERIFYING, TaskStatus.AWAITING_REVIEW)
        ]

    def select_next_task(self) -> Optional[TaskRecord]:
        """Select the next task to execute based on priority."""
        pending = self.get_pending_tasks()
        return pending[0] if pending else None

    def complete_task(self, task_id: str, success: bool) -> None:
        """Mark a task as completed."""
        task = self.tasks.get(task_id)
        if task:
            if success:
                task.transition_to(TaskStatus.COMMITTED)
                self.completed_task_ids.append(task_id)
            else:
                task.transition_to(TaskStatus.FAILED)
                self.failed_task_ids.append(task_id)


class BudgetReservationStatus(Enum):
    """Status of a budget reservation."""
    RESERVED = "reserved"
    COMMITTED = "committed"
    RELEASED = "released"
    EXHAUSTED = "exhausted"


@dataclass
class BudgetReservation:
    """A reservation of budget for a specific task."""
    reservation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: Optional[str] = None
    reserved_tokens: int = 0
    reserved_cost: float = 0.0
    reserved_steps: int = 0
    used_tokens: int = 0
    used_cost: float = 0.0
    used_steps: int = 0
    status: BudgetReservationStatus = BudgetReservationStatus.RESERVED
    created_at: datetime = field(default_factory=datetime.now)

    def is_exhausted(self) -> bool:
        """Check if reserved budget is exhausted."""
        return (
            self.used_tokens >= self.reserved_tokens or
            self.used_cost >= self.reserved_cost or
            self.used_steps >= self.reserved_steps
        )


class VerificationVerdict(Enum):
    """Verdict from the verification phase."""
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    ABSTAIN = "abstain"


@dataclass
class GateOutcomeData:
    """Outcome data of a deterministic gate check."""
    gate_name: str
    passed: bool
    message: str
    severity: str = "error"
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationOutcome:
    """Complete outcome of the verification phase."""
    task_id: str = ""
    pre_gate_outcomes: List[GateOutcomeData] = field(default_factory=list)
    post_gate_outcomes: List[GateOutcomeData] = field(default_factory=list)
    all_gates_passed: bool = False
    evaluator_score: float = 0.0
    evaluator_passed: bool = False
    evaluator_feedback: str = ""
    checkpoint_id: Optional[str] = None
    human_decision: Optional[str] = None
    human_feedback: Optional[str] = None
    verdict: VerificationVerdict = VerificationVerdict.PENDING
    verdict_timestamp: Optional[datetime] = None

    def compute_verdict(self) -> VerificationVerdict:
        """Compute final verdict from all inputs."""
        failed_mandatory = any(
            not g.passed and g.severity == "error"
            for g in self.pre_gate_outcomes + self.post_gate_outcomes
        )
        if failed_mandatory:
            self.verdict = VerificationVerdict.FAIL
            self.verdict_timestamp = datetime.now()
            return self.verdict

        if not self.evaluator_passed:
            self.verdict = VerificationVerdict.FAIL
            self.verdict_timestamp = datetime.now()
            return self.verdict

        if self.human_decision == "REJECT":
            self.verdict = VerificationVerdict.FAIL
            self.verdict_timestamp = datetime.now()
            return self.verdict

        if self.human_decision in ("APPROVE", "MODIFY") or self.human_decision is None:
            self.all_gates_passed = True
            self.verdict = VerificationVerdict.PASS
            self.verdict_timestamp = datetime.now()
            return self.verdict

        if self.human_decision in ("RETRY", "PAUSE"):
            self.verdict = VerificationVerdict.NEEDS_REVIEW
            self.verdict_timestamp = datetime.now()
            return self.verdict

        return VerificationVerdict.ABSTAIN


@dataclass
class DiscoveryConfig:
    """Configuration for the discovery phase."""
    skills_dir: Path = field(default_factory=lambda: Path(".claude/skills"))
    auto_reload_skills: bool = True
    state_dir: Path = field(default_factory=lambda: Path(".loop_state"))
    load_latest_on_start: bool = True
    max_concurrent_tasks: int = 1
    default_priority: TaskPriority = TaskPriority.NORMAL


@dataclass
class HandoffConfig:
    """Configuration for the handoff phase."""
    default_token_budget: int = 100_000
    default_cost_budget: float = 10.0
    default_step_budget: int = 50
    worktrees_dir: Path = field(default_factory=lambda: Path(".loop_worktrees"))
    auto_cleanup_worktrees: bool = True
    generator_config_id: Optional[str] = None


@dataclass
class VerificationConfig:
    """Configuration for the verification phase."""
    enable_pre_gates: bool = True
    enable_post_gates: bool = True
    mandatory_gates: List[str] = field(default_factory=lambda: ["syntax", "security"])
    evaluator_config_id: Optional[str] = None
    evaluator_threshold: float = 0.8
    checkpoint_preset: str = "production"
    auto_approve_passing: bool = False


@dataclass
class PersistenceConfig:
    """Configuration for the persistence phase."""
    state_dir: Path = field(default_factory=lambda: Path(".loop_state"))
    format: str = "json"
    auto_save: bool = True
    save_interval_seconds: int = 30
    max_history: int = 10


@dataclass
class SchedulingConfig:
    """Configuration for the scheduling phase."""
    poll_interval_seconds: int = 60
    max_idle_iterations: int = 10
    exit_on_no_tasks: bool = True
    exit_on_budget_exhausted: bool = True
    schedule_file: Path = field(default_factory=lambda: Path(".loop_schedule.json"))


@dataclass
class RuntimeConfig:
    """Complete runtime configuration."""
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    handoff: HandoffConfig = field(default_factory=HandoffConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    scheduling: SchedulingConfig = field(default_factory=SchedulingConfig)
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: Optional[str] = None
    log_level: str = "INFO"
    dry_run: bool = False


@dataclass
class PhaseState:
    """State tracking for each runtime phase."""
    discovery: DiscoveryStatus = DiscoveryStatus.IDLE
    handoff: HandoffStatus = HandoffStatus.IDLE
    verification: VerificationStatus = VerificationStatus.IDLE
    persistence: PersistenceStatus = PersistenceStatus.IDLE
    scheduling: SchedulingStatus = SchedulingStatus.IDLE

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "discovery": self.discovery.value,
            "handoff": self.handoff.value,
            "verification": self.verification.value,
            "persistence": self.persistence.value,
            "scheduling": self.scheduling.value,
        }


@dataclass
class RuntimeState:
    """Unified runtime state for Loop Runtime V1."""
    runtime_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: Optional[str] = None
    schema_version: str = "1.0.0"
    status: "LoopStatus" = field(default_factory=lambda: __import__("loop_engine.types", fromlist=["LoopStatus"]).LoopStatus.PENDING)
    current_phase: Optional[RuntimePhase] = None
    phase_states: PhaseState = field(default_factory=PhaseState)
    task_ledger: TaskLedger = field(default_factory=TaskLedger)
    current_task_id: Optional[str] = None
    active_reservation: Optional[BudgetReservation] = None
    current_iteration: int = 0
    max_iterations: int = 100
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_current_task(self) -> Optional[TaskRecord]:
        """Get the currently executing task."""
        if self.current_task_id:
            return self.task_ledger.get_task(self.current_task_id)
        return None

    def set_phase(self, phase: RuntimePhase) -> None:
        """Set the current runtime phase."""
        self.current_phase = phase
        self.last_updated = datetime.now()

    def set_phase_status(self, phase: RuntimePhase, status: Enum) -> None:
        """Update status for a specific phase."""
        phase_name = phase.value
        if hasattr(self.phase_states, phase_name):
            setattr(self.phase_states, phase_name, status)
        self.last_updated = datetime.now()

    def increment_iteration(self) -> None:
        """Increment iteration counter."""
        self.current_iteration += 1
        self.last_updated = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "schema_version": self.schema_version,
            "runtime_id": self.runtime_id,
            "trace_id": self.trace_id,
            "status": self.status.name if hasattr(self.status, 'name') else str(self.status),
            "current_phase": self.current_phase.value if self.current_phase else None,
            "phase_states": self.phase_states.to_dict(),
            "task_ledger": self.task_ledger.to_dict(),
            "current_task_id": self.current_task_id,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
        }


class EventType(Enum):
    """Types of runtime events for structured tracing."""
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    TASK_DISCOVERED = "task_discovered"
    TASK_RESERVED = "task_reserved"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    BUDGET_RESERVED = "budget_reserved"
    BUDGET_COMMITTED = "budget_committed"
    BUDGET_RELEASED = "budget_released"
    BUDGET_EXHAUSTED = "budget_exhausted"
    WORKTREE_CREATED = "worktree_created"
    WORKTREE_MERGED = "worktree_merged"
    WORKTREE_CLEANED = "worktree_cleaned"
    GATE_PASSED = "gate_passed"
    GATE_FAILED = "gate_failed"
    EVALUATION_STARTED = "evaluation_started"
    EVALUATION_COMPLETED = "evaluation_completed"
    CHECKPOINT_TRIGGERED = "checkpoint_triggered"
    CHECKPOINT_RESOLVED = "checkpoint_resolved"
    STATE_SAVED = "state_saved"
    STATE_LOADED = "state_loaded"
    FAILURE_OCCURRED = "failure_occurred"
    RECOVERY_ATTEMPTED = "recovery_attempted"
    RECOVERY_SUCCEEDED = "recovery_succeeded"
    RECOVERY_FAILED = "recovery_failed"


@dataclass
class RuntimeEvent:
    """A structured event for runtime tracing."""
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.now)
    trace_id: str = ""
    task_id: Optional[str] = None
    phase: Optional[RuntimePhase] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "phase": self.phase.value if self.phase else None,
            "details": self.details,
        }


@dataclass
class PhaseResult:
    """Result of executing a single phase."""
    phase: RuntimePhase
    success: bool
    state: RuntimeState
    events: List[RuntimeEvent] = field(default_factory=list)
    error: Optional[str] = None
    next_phase: Optional[RuntimePhase] = None


@dataclass
class RuntimeResult:
    """Final result of a runtime execution."""
    runtime_id: str
    trace_id: str
    status: "LoopStatus"
    tasks_discovered: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    iterations: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_tokens_used: int = 0
    total_cost: float = 0.0
    events: List[RuntimeEvent] = field(default_factory=list)

    def get_duration_seconds(self) -> Optional[float]:
        """Get total execution duration."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "runtime_id": self.runtime_id,
            "trace_id": self.trace_id,
            "status": self.status.name if hasattr(self.status, 'name') else str(self.status),
            "tasks_discovered": self.tasks_discovered,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "iterations": self.iterations,
            "duration_seconds": self.get_duration_seconds(),
        }
