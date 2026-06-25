"""
Human Checkpoint Module

Based on Anthropic's Loop Engineering paper (Section VII.C):
- "Keep One Door Open" principle
- "The human did not leave, but changed desks, from writing to reviewing"
- "One line - the loop can execute, but it cannot decide"
- "One must at least remain capable of saying 'this is wrong'"

Also addresses "Cognitive Surrender" from Section VIII:
- Guard against outsourcing judgment
- Force human review at critical points
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
import json

from .types import Failure, Step, StepStatus

# Import LoopState from core (not types) to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .core import LoopState


class CheckpointTrigger(Enum):
    """Conditions that trigger a human checkpoint."""
    ON_FAILURE = auto()  # Any failure
    ON_MAJOR_FAILURE = auto()  # Only terminal/unrecoverable failures
    ON_PLAN_COMPLETE = auto()  # When plan is complete
    ON_ITERATION_BOUNDARY = auto()  # Every N iterations
    ON_COST_THRESHOLD = auto()  # When cost exceeds threshold
    ON_EXTERNAL_REQUEST = auto()  # Manual trigger


class HumanDecision(Enum):
    """Possible human decisions at checkpoint."""
    APPROVE = auto()  # Continue execution
    REJECT = auto()  # Stop and fail
    RETRY = auto()  # Retry the current step
    MODIFY = auto()  # Continue with modifications
    PAUSE = auto()  # Pause for later review


@dataclass
class ReviewRequest:
    """A request for human review."""
    checkpoint_id: str
    trigger: CheckpointTrigger
    state_summary: Dict[str, Any]
    proposed_action: str
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Presentation
    format: str = "markdown"  # "markdown" or "json"

    def to_markdown(self) -> str:
        """Format review request as markdown."""
        trigger_name = self.trigger.name if self.trigger else "Manual"
        lines = [
            f"# Human Checkpoint: {self.checkpoint_id}",
            "",
            f"**Triggered by:** {trigger_name}",
            f"**Time:** {self.timestamp}",
            f"**Proposed Action:** {self.proposed_action}",
            "",
            "## State Summary",
            "",
            f"- **Iteration:** {self.state_summary.get('iteration', 'N/A')}",
            f"- **Status:** {self.state_summary.get('status', 'N/A')}",
            f"- **Failures:** {self.state_summary.get('failure_count', 0)}",
            f"- **Recoveries:** {self.state_summary.get('recovery_count', 0)}",
            "",
        ]

        # Current step info
        current_step = self.state_summary.get('current_step')
        if current_step:
            lines.extend([
                "## Current Step",
                "",
                f"**ID:** {current_step.get('id', 'N/A')}",
                f"**Description:** {current_step.get('description', 'N/A')}",
                f"**Status:** {current_step.get('status', 'N/A')}",
                "",
            ])

        # Recent failures
        recent_failures = self.state_summary.get('recent_failures', [])
        if recent_failures:
            lines.extend([
                "## Recent Failures",
                "",
            ])
            for failure in recent_failures[:3]:
                lines.append(f"- **{failure.get('type', 'Unknown')}:** {failure.get('message', 'No message')[:100]}")
            lines.append("")

        # Options
        lines.extend([
            "## Decision Options",
            "",
            "| Option | Description |",
            "|--------|-------------|",
            "| **APPROVE** | Continue with proposed action |",
            "| **REJECT** | Stop execution and mark as failed |",
            "| **RETRY** | Retry the current step |",
            "| **MODIFY** | Continue with modifications (specify below) |",
            "| **PAUSE** | Pause for later review |",
            "",
            "## Your Decision",
            "",
            "Please respond with one of: APPROVE, REJECT, RETRY, MODIFY, PAUSE",
            "",
        ])

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "trigger": self.trigger.name,
            "state_summary": self.state_summary,
            "proposed_action": self.proposed_action,
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class ReviewResponse:
    """Human response to a review request."""
    checkpoint_id: str
    decision: HumanDecision
    feedback: str = ""
    modifications: Dict[str, Any] = field(default_factory=dict)
    reviewer: str = "human"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "decision": self.decision.name,
            "feedback": self.feedback,
            "modifications": self.modifications,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp,
        }


@dataclass
class CheckpointConfig:
    """Configuration for human checkpoints."""
    enabled: bool = True

    # Triggers
    trigger_on_failure: bool = False
    trigger_on_major_failure: bool = True
    trigger_on_plan_complete: bool = False
    trigger_every_n_iterations: Optional[int] = None
    trigger_cost_threshold: Optional[float] = None

    # Auto-approve settings (for non-critical paths)
    auto_approve_retries: bool = False
    auto_approve_recoveries: bool = False

    # Persistence
    save_checkpoints: bool = True
    checkpoint_dir: Path = field(default_factory=lambda: Path(".loop_checkpoints"))


class HumanCheckpoint:
    """
    Pause loop for human review at critical points.

    Implements the "Keep One Door Open" principle from the paper:
    - The loop can execute, but it cannot decide
    - Human judgment remains the scarce resource
    """

    def __init__(self, config: Optional[CheckpointConfig] = None):
        self.config = config or CheckpointConfig()
        self._checkpoint_count = 0
        self._response_handler: Optional[Callable[[ReviewRequest], ReviewResponse]] = None

        if self.config.save_checkpoints:
            self.config.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def set_response_handler(
        self,
        handler: Callable[[ReviewRequest], ReviewResponse]
    ) -> None:
        """Set a custom handler for review responses."""
        self._response_handler = handler

    def should_pause(self, state: "LoopState") -> Optional[CheckpointTrigger]:
        """
        Determine if human review is required.

        Returns:
            CheckpointTrigger if pause needed, None otherwise
        """
        if not self.config.enabled:
            return None

        # Check failure triggers
        if self.config.trigger_on_major_failure:
            major_failures = [
                f for f in state.failures
                if f.status.value in ['terminal', 'recovery_failed']
            ]
            if major_failures:
                return CheckpointTrigger.ON_MAJOR_FAILURE

        if self.config.trigger_on_failure and state.failures:
            return CheckpointTrigger.ON_FAILURE

        # Check iteration trigger
        if self.config.trigger_every_n_iterations:
            if state.current_iteration % self.config.trigger_every_n_iterations == 0:
                return CheckpointTrigger.ON_ITERATION_BOUNDARY

        # Check plan completion
        if self.config.trigger_on_plan_complete:
            if state.current_plan and state.current_plan.is_complete():
                return CheckpointTrigger.ON_PLAN_COMPLETE

        return None

    def present_for_review(
        self,
        state: "LoopState",
        trigger: CheckpointTrigger,
        proposed_action: str = "Continue execution",
    ) -> ReviewRequest:
        """
        Format state for human review.

        Args:
            state: Current loop state
            trigger: What triggered the checkpoint
            proposed_action: What the loop wants to do next

        Returns:
            ReviewRequest ready for human review
        """
        self._checkpoint_count += 1
        checkpoint_id = f"checkpoint_{self._checkpoint_count:04d}"

        # Build state summary
        state_summary = {
            "iteration": state.current_iteration,
            "status": state.status.name,
            "execution_state": state.execution_state.value,
            "failure_count": len(state.failures),
            "recovery_count": len(state.recoveries),
        }

        # Add current step info
        if state.current_step:
            state_summary["current_step"] = {
                "id": state.current_step.id,
                "description": state.current_step.description,
                "status": state.current_step.status.value,
            }

        # Add recent failures
        recent_failures = [
            {
                "type": f.type.value,
                "message": f.message,
                "status": f.status.value,
            }
            for f in state.failures[-3:]
        ]
        state_summary["recent_failures"] = recent_failures

        # Add plan progress
        if state.current_plan:
            state_summary["plan_progress"] = state.current_plan.get_progress()
            state_summary["plan_steps_total"] = len(state.current_plan.steps)

        request = ReviewRequest(
            checkpoint_id=checkpoint_id,
            trigger=trigger,
            state_summary=state_summary,
            proposed_action=proposed_action,
        )

        # Save checkpoint record
        if self.config.save_checkpoints:
            self._save_checkpoint(request)

        return request

    async def await_decision(self, request: ReviewRequest) -> ReviewResponse:
        """
        Block until human provides decision.

        This is a placeholder - in practice this would:
        1. Display the request to the user
        2. Wait for input
        3. Return the response

        For automated testing, use set_response_handler().
        """
        if self._response_handler:
            return self._response_handler(request)

        # Default implementation - auto-approve for non-critical checkpoints
        return ReviewResponse(
            checkpoint_id=request.checkpoint_id,
            decision=HumanDecision.APPROVE,
            feedback="Auto-approved (no handler configured)",
        )

    def _save_checkpoint(self, request: ReviewRequest) -> None:
        """Save checkpoint to disk."""
        filepath = self.config.checkpoint_dir / f"{request.checkpoint_id}.md"
        filepath.write_text(request.to_markdown())

    def get_checkpoint_history(self) -> List[Dict[str, Any]]:
        """Get history of all checkpoints."""
        if not self.config.checkpoint_dir.exists():
            return []

        checkpoints = []
        for filepath in self.config.checkpoint_dir.glob("checkpoint_*.md"):
            checkpoints.append({
                "checkpoint_id": filepath.stem,
                "filepath": str(filepath),
                "timestamp": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
            })

        return sorted(checkpoints, key=lambda x: x["timestamp"])


# Pre-configured checkpoint presets

class CheckpointPresets:
    """Factory for common checkpoint configurations."""

    @staticmethod
    def manual_only() -> CheckpointConfig:
        """Only trigger on manual request."""
        return CheckpointConfig(
            enabled=True,
            trigger_on_failure=False,
            trigger_on_major_failure=False,
            trigger_on_plan_complete=False,
            trigger_every_n_iterations=None,
        )

    @staticmethod
    def conservative() -> CheckpointConfig:
        """Pause on any significant event."""
        return CheckpointConfig(
            enabled=True,
            trigger_on_failure=True,
            trigger_on_major_failure=True,
            trigger_on_plan_complete=True,
            trigger_every_n_iterations=5,
        )

    @staticmethod
    def production() -> CheckpointConfig:
        """Production setting - only major failures."""
        return CheckpointConfig(
            enabled=True,
            trigger_on_failure=False,
            trigger_on_major_failure=True,
            trigger_on_plan_complete=True,
            trigger_every_n_iterations=None,
            auto_approve_retries=True,
        )

    @staticmethod
    def disabled() -> CheckpointConfig:
        """Disable all checkpoints."""
        return CheckpointConfig(enabled=False)
