"""
Recovery strategy handlers for the Loop Engineering Framework.

This module implements executable handlers for recovery strategies,
ensuring recovery actions perform actual state changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING
import logging

from ..types import (
    ExecutionState,
    Failure,
    LoopContext,
    RecoveryStrategy,
    Step,
    StepStatus,
)

if TYPE_CHECKING:
    from ..core import LoopState

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Result of recovery execution."""
    success: bool
    new_state: Optional[ExecutionState] = None
    step_status: Optional[StepStatus] = None
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)


class RecoveryHandler(ABC):
    """Base class for recovery strategy handlers."""

    @abstractmethod
    async def execute(
        self,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """
        Execute recovery strategy.

        Args:
            failure: The failure being recovered from
            step: The step that failed (if applicable)
            state: Current loop state
            context: Loop execution context

        Returns:
            RecoveryResult with success/failure and state changes
        """
        pass

    @abstractmethod
    def validate_postconditions(
        self,
        step: Optional[Step],
        state: 'LoopState'
    ) -> bool:
        """Verify recovery produced valid state."""
        pass


class RetryHandler(RecoveryHandler):
    """Handler for RETRY strategy - re-execute the failed step."""

    async def execute(
        self,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """Reset step for retry."""
        if not step:
            return RecoveryResult(
                success=False,
                message="No step to retry"
            )

        logger.info(f"RetryHandler: Resetting step {step.id} for retry")

        # Preserve failure evidence
        if 'retry_count' not in step.metadata:
            step.metadata['retry_count'] = 0
        step.metadata['retry_count'] += 1
        step.metadata['last_failure'] = failure.message

        # Check max retries
        max_retries = context.budget.max_steps if context.budget else 3
        if step.metadata['retry_count'] >= max_retries:
            return RecoveryResult(
                success=False,
                message=f"Max retries ({max_retries}) exceeded"
            )

        # Reset step fields
        step.status = StepStatus.RETRY_PENDING
        step.output = None
        step.start_time = None
        step.end_time = None

        # Transition to READY
        step.status = StepStatus.READY

        return RecoveryResult(
            success=True,
            new_state=ExecutionState.ITERATION_COMPLETE,
            step_status=StepStatus.READY,
            message=f"Step {step.id} reset for retry (attempt {step.metadata['retry_count']})",
            evidence={'retry_count': step.metadata['retry_count']}
        )

    def validate_postconditions(
        self,
        step: Optional[Step],
        state: 'LoopState'
    ) -> bool:
        """Verify step is ready for re-execution."""
        if not step:
            return False
        return step.status == StepStatus.READY and step.output is None


class ReplanStepHandler(RecoveryHandler):
    """Handler for PLAN_REVISION strategy - replan the failed step."""

    async def execute(
        self,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """Replace failed step with corrected version."""
        if not step or not state.current_plan:
            return RecoveryResult(
                success=False,
                message="No step or plan to replan"
            )

        logger.info(f"ReplanStepHandler: Replanning step {step.id}")

        # Preserve failure evidence
        step.metadata['failure_evidence'] = {
            'failure_id': failure.failure_id,
            'message': failure.message,
            'type': failure.type.value,
        }
        step.metadata['replanned'] = True

        # Find step index in plan
        try:
            step_index = state.current_plan.steps.index(step)
        except ValueError:
            return RecoveryResult(
                success=False,
                message=f"Step {step.id} not found in plan"
            )

        # Create corrected step
        from ..types import Step as StepClass
        new_step = StepClass(
            description=f"[Corrected] {step.description}",
            dependencies=step.dependencies,
            metadata={
                'replaces': step.id,
                'correction_reason': failure.message,
                'version': step.metadata.get('version', 1) + 1,
            }
        )

        # Replace step in plan
        state.current_plan.steps[step_index] = new_step

        # Increment plan version
        state.current_plan.version += 1

        return RecoveryResult(
            success=True,
            new_state=ExecutionState.REPLANNING,
            step_status=StepStatus.PENDING,
            message=f"Step {step.id} replaced with {new_step.id}",
            evidence={
                'old_step_id': step.id,
                'new_step_id': new_step.id,
                'plan_version': state.current_plan.version,
            }
        )

    def validate_postconditions(
        self,
        step: Optional[Step],
        state: 'LoopState'
    ) -> bool:
        """Verify plan was revised correctly."""
        if not state.current_plan:
            return False
        return state.current_plan.version > 1


class RequestHumanHandler(RecoveryHandler):
    """Handler for HUMAN_HANDOFF strategy - escalate to human."""

    async def execute(
        self,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """Transition to WAITING_FOR_HUMAN state."""
        logger.info(f"RequestHumanHandler: Escalating failure {failure.failure_id} to human")

        # Prepare human context
        human_context = {
            'failure_id': failure.failure_id,
            'failure_type': failure.type.value,
            'message': failure.message,
            'step_id': step.id if step else None,
            'recovery_attempts': failure.recovery_attempts,
            'options': [
                'retry',
                'replan',
                'skip',
                'abort',
            ]
        }

        # Store in state metadata
        state.metadata['human_escalation'] = human_context

        return RecoveryResult(
            success=True,
            new_state=ExecutionState.WAITING_FOR_HUMAN,
            message="Escalated to human operator",
            evidence=human_context
        )

    def validate_postconditions(
        self,
        step: Optional[Step],
        state: 'LoopState'
    ) -> bool:
        """Verify human escalation recorded."""
        return 'human_escalation' in state.metadata


class TerminateHandler(RecoveryHandler):
    """Handler for TERMINATE strategy - stop with failure."""

    async def execute(
        self,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """Mark failure as terminal and transition to FAILED."""
        logger.info(f"TerminateHandler: Marking failure {failure.failure_id} as terminal")

        failure.mark_terminal()

        return RecoveryResult(
            success=True,  # The termination itself succeeded
            new_state=ExecutionState.FAILED,
            message=f"Execution terminated: {failure.message}",
            evidence={'failure_id': failure.failure_id}
        )

    def validate_postconditions(
        self,
        step: Optional[Step],
        state: 'LoopState'
    ) -> bool:
        """Verify terminal state reached."""
        return state.execution_state == ExecutionState.FAILED


class RecoveryRegistry:
    """Registry of recovery strategy handlers."""

    def __init__(self):
        self._handlers: Dict[RecoveryStrategy, RecoveryHandler] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register built-in handlers."""
        self.register(RecoveryStrategy.RETRY, RetryHandler())
        self.register(RecoveryStrategy.PLAN_REVISION, ReplanStepHandler())
        self.register(RecoveryStrategy.HUMAN_HANDOFF, RequestHumanHandler())

    def register(self, strategy: RecoveryStrategy, handler: RecoveryHandler):
        """Register a handler for a strategy."""
        self._handlers[strategy] = handler

    def get_handler(self, strategy: RecoveryStrategy) -> Optional[RecoveryHandler]:
        """Get handler for strategy."""
        return self._handlers.get(strategy)

    async def execute(
        self,
        strategy: RecoveryStrategy,
        failure: Failure,
        step: Optional[Step],
        state: 'LoopState',
        context: LoopContext
    ) -> RecoveryResult:
        """
        Execute recovery strategy with validation.

        Args:
            strategy: Recovery strategy to execute
            failure: Failure being recovered from
            step: Failed step (if applicable)
            state: Current loop state
            context: Loop context

        Returns:
            RecoveryResult with outcome
        """
        handler = self._handlers.get(strategy)
        if not handler:
            return RecoveryResult(
                success=False,
                message=f"No handler for strategy {strategy.value}"
            )

        logger.info(f"RecoveryRegistry: Executing {strategy.value} for failure {failure.failure_id}")

        # Execute recovery
        try:
            result = await handler.execute(failure, step, state, context)
        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            return RecoveryResult(
                success=False,
                message=f"Recovery execution failed: {e}"
            )

        # Validate postconditions if execution succeeded
        if result.success:
            valid = handler.validate_postconditions(step, state)
            if not valid:
                result.success = False
                result.message = f"Recovery postconditions not met: {result.message}"
                logger.warning(f"Recovery postconditions failed for {strategy.value}")

        return result
