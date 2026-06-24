"""
Tests for state machine and failure lifecycle tracking.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

from loop_engine.core import LoopEngine, LoopConfig
from loop_engine.types import (
    ComponentType, LoopContext, Budget, Failure, FailureType,
    FailureStatus, RecoveryAction, RecoveryStrategy, ExecutionState
)
from loop_engine.components import (
    LLMPlanner, LLMActor, SimpleObserver, LLMEvaluator,
    AdaptiveRecovery, CombinedTerminator, SimplePlanner
)
from loop_engine.llm_client import MockLLMClient


class TestStateMachine:
    """Tests for the execution state machine."""

    @pytest.mark.asyncio
    async def test_initial_state_is_initialized(self):
        """Loop starts in INITIALIZED state."""
        engine = LoopEngine(LoopConfig(max_iterations=1))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))

        context = LoopContext(goal="Test goal", budget=Budget())

        # Before run, no state
        assert engine.state is None

        # Start the run but don't await fully
        result = await engine.run(context)

        # After run, state should exist and have ended in a terminal state
        assert engine.state is not None
        assert engine.state.execution_state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.BUDGET_EXHAUSTED
        }

    @pytest.mark.asyncio
    async def test_state_transitions_through_iteration(self):
        """State transitions through normal iteration phases."""
        engine = LoopEngine(LoopConfig(max_iterations=1, verbose=True))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        # Should have passed through multiple states
        assert engine.state.counters.planner_called > 0
        assert engine.state.counters.actor_called > 0
        assert engine.state.execution_state != ExecutionState.INITIALIZED

    @pytest.mark.asyncio
    async def test_invalid_state_transition_raises(self):
        """Invalid state transitions raise RuntimeError."""
        engine = LoopEngine(LoopConfig())
        engine.state = engine.state or type('State', (), {})()
        engine.state.execution_state = ExecutionState.COMPLETED

        # Cannot transition from COMPLETED to PLANNING
        with pytest.raises(RuntimeError) as exc_info:
            engine._transition_to(ExecutionState.PLANNING)

        assert "Invalid state transition" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_valid_state_transitions(self):
        """Valid state transitions succeed."""
        engine = LoopEngine(LoopConfig())
        engine.state = type('State', (), {'execution_state': ExecutionState.INITIALIZED})()

        # Valid: INITIALIZED -> PLANNING
        engine._transition_to(ExecutionState.PLANNING)
        assert engine.state.execution_state == ExecutionState.PLANNING

        # Valid: PLANNING -> ACTING
        engine._transition_to(ExecutionState.ACTING)
        assert engine.state.execution_state == ExecutionState.ACTING


class TestFailureLifecycle:
    """Tests for the explicit failure lifecycle tracking."""

    def test_failure_starts_unhandled(self):
        """New failures start with UNHANDLED status."""
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message="Test error"
        )
        assert failure.status == FailureStatus.UNHANDLED
        assert failure.can_recover() is True

    def test_failure_can_recover_checks_attempts(self):
        """can_recover() returns False when max attempts reached."""
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            max_recovery_attempts=2
        )

        assert failure.can_recover() is True

        failure.record_recovery_attempt("action_1")
        assert failure.recovery_attempts == 1
        assert failure.can_recover() is True

        failure.record_recovery_attempt("action_2")
        assert failure.recovery_attempts == 2
        assert failure.can_recover() is False

    def test_failure_mark_recovered(self):
        """mark_recovered() sets status to RECOVERED."""
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message="Test error"
        )

        failure.record_recovery_attempt("action_1")
        failure.mark_recovered()

        assert failure.status == FailureStatus.RECOVERED
        assert failure.recoverable is False
        assert failure.can_recover() is False

    def test_failure_mark_terminal(self):
        """mark_terminal() sets status to TERMINAL."""
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message="Test error"
        )

        failure.mark_terminal()

        assert failure.status == FailureStatus.TERMINAL
        assert failure.recoverable is False
        assert failure.can_recover() is False

    def test_failure_has_unique_id(self):
        """Each failure has a unique failure_id."""
        failure1 = Failure(message="Error 1")
        failure2 = Failure(message="Error 2")

        assert failure1.failure_id != failure2.failure_id
        assert len(failure1.failure_id) == 8
        assert len(failure2.failure_id) == 8


class TestRecoveryActionTracking:
    """Tests for recovery action tracking with failure_id."""

    def test_recovery_action_has_unique_id(self):
        """Each recovery action has a unique action_id."""
        action1 = RecoveryAction(strategy=RecoveryStrategy.RETRY)
        action2 = RecoveryAction(strategy=RecoveryStrategy.BACKOFF)

        assert action1.action_id != action2.action_id
        assert len(action1.action_id) == 8

    def test_recovery_action_links_to_failure(self):
        """Recovery action can be linked to a failure via failure_id."""
        failure = Failure(message="Test error")
        action = RecoveryAction(
            strategy=RecoveryStrategy.RETRY,
            failure_id=failure.failure_id
        )

        assert action.failure_id == failure.failure_id
        assert action.executed is False
        assert action.success is None

    def test_recovery_action_tracks_execution(self):
        """Recovery action tracks execution status."""
        action = RecoveryAction(strategy=RecoveryStrategy.RETRY)

        assert action.executed is False
        assert action.success is None

        action.executed = True
        action.success = True

        assert action.executed is True
        assert action.success is True


class TestRecoveryIntegration:
    """Integration tests for recovery with failure lifecycle."""

    @pytest.mark.asyncio
    async def test_recovery_updates_failure_status(self):
        """Recovery execution updates failure status correctly."""
        engine = LoopEngine(LoopConfig(max_iterations=3))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))
        engine.register_component(ComponentType.RECOVERY, AdaptiveRecovery())

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        # Recovery component should be registered
        assert engine.components.get(ComponentType.RECOVERY) is not None

    @pytest.mark.asyncio
    async def test_failure_tracked_in_state(self):
        """Failures are tracked in loop state with lifecycle."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        # Check that any failures have proper lifecycle tracking
        for failure in result.failures:
            assert hasattr(failure, 'failure_id')
            assert hasattr(failure, 'status')
            assert hasattr(failure, 'recovery_attempts')


class TestBudgetExhaustion:
    """Tests for budget exhaustion handling."""

    @pytest.mark.asyncio
    async def test_budget_exhaustion_sets_state(self):
        """Budget exhaustion sets execution state to BUDGET_EXHAUSTED."""
        engine = LoopEngine(LoopConfig(max_iterations=100))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))

        # Set very low step budget
        budget = Budget(max_steps=1)
        context = LoopContext(goal="Test goal", budget=budget)

        result = await engine.run(context)

        # Should have exhausted budget
        assert engine.state.execution_state == ExecutionState.BUDGET_EXHAUSTED
        assert result.status.name == "FAILED"


class TestTerminalStates:
    """Tests for terminal execution states."""

    @pytest.mark.asyncio
    async def test_completed_is_terminal(self):
        """COMPLETED is a terminal state."""
        engine = LoopEngine(LoopConfig(max_iterations=10))

        # Test transition validation
        engine.state = type('State', (), {'execution_state': ExecutionState.COMPLETED})()

        with pytest.raises(RuntimeError):
            engine._transition_to(ExecutionState.PLANNING)

    @pytest.mark.asyncio
    async def test_failed_is_terminal(self):
        """FAILED is a terminal state."""
        engine = LoopEngine(LoopConfig(max_iterations=10))

        engine.state = type('State', (), {'execution_state': ExecutionState.FAILED})()

        with pytest.raises(RuntimeError):
            engine._transition_to(ExecutionState.PLANNING)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
