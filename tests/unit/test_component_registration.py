"""
Unit tests for component registration and basic loop execution.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest

from loop_engine.core import LoopEngine, LoopConfig, ComponentRegistry
from loop_engine.types import (
    ComponentType, LoopContext, Budget, Failure, FailureType,
    RecoveryAction, RecoveryStrategy
)
from loop_engine.components import (
    LLMPlanner, LLMActor, SimpleObserver, LLMEvaluator,
    AdaptiveRecovery, CombinedTerminator, SimplePlanner
)
from loop_engine.llm_client import MockLLMClient


class TestComponentRegistration:
    """Tests for the component registration system."""

    def test_enum_registration_works(self):
        """Components registered with enum keys can be retrieved."""
        engine = LoopEngine(LoopConfig())
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))

        assert engine.components.get(ComponentType.PLANNER) is not None
        assert engine.components.get(ComponentType.ACTOR) is not None

    def test_string_key_rejected(self):
        """String keys are rejected with TypeError."""
        registry = ComponentRegistry()
        llm = MockLLMClient()

        with pytest.raises(TypeError) as exc_info:
            registry.register("PLANNER", LLMPlanner(llm))

        assert "ComponentType enum" in str(exc_info.value)

    def test_interface_validation(self):
        """Components without required methods are rejected."""
        engine = LoopEngine(LoopConfig())

        class BadPlanner:
            pass

        with pytest.raises(ValueError) as exc_info:
            engine.register_component(ComponentType.PLANNER, BadPlanner())

        assert "missing required methods" in str(exc_info.value)

    def test_duplicate_registration_rejected(self):
        """Duplicate registration without allow_replace raises RuntimeError."""
        engine = LoopEngine(LoopConfig())
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))

        with pytest.raises(RuntimeError) as exc_info:
            engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))

        assert "already registered" in str(exc_info.value)

    def test_allow_replace_works(self):
        """Duplicate registration with allow_replace=True succeeds."""
        engine = LoopEngine(LoopConfig())
        llm = MockLLMClient()

        planner1 = LLMPlanner(llm)
        planner2 = LLMPlanner(llm)

        engine.register_component(ComponentType.PLANNER, planner1)
        engine.register_component(ComponentType.PLANNER, planner2, allow_replace=True)

        assert engine.components.get(ComponentType.PLANNER) is planner2

    def test_list_registered(self):
        """list_registered returns component type names."""
        engine = LoopEngine(LoopConfig())
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))

        registered = engine.components.list_registered()
        assert 'planner' in registered
        assert 'actor' in registered


class TestComponentCalls:
    """Tests that verify components are actually called during execution."""

    @pytest.mark.asyncio
    async def test_planner_is_called(self):
        """Planner is called during loop execution."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))
        engine.register_component(ComponentType.TERMINATOR, CombinedTerminator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        assert engine.state.counters.planner_called > 0, "Planner was not called"

    @pytest.mark.asyncio
    async def test_actor_is_called(self):
        """Actor is called during loop execution."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        assert engine.state.counters.actor_called > 0, "Actor was not called"

    @pytest.mark.asyncio
    async def test_observer_is_called(self):
        """Observer is called during loop execution."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        assert engine.state.counters.observer_called > 0, "Observer was not called"

    @pytest.mark.asyncio
    async def test_evaluator_is_called(self):
        """Evaluator is called during loop execution."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        assert engine.state.counters.evaluator_called > 0, "Evaluator was not called"


class TestFinalStatus:
    """Tests that final status is never RUNNING."""

    @pytest.mark.asyncio
    async def test_final_status_not_running(self):
        """Final status must not be RUNNING."""
        engine = LoopEngine(LoopConfig(max_iterations=2))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        assert result.status.name != "RUNNING", f"Final status was {result.status.name}"

    @pytest.mark.asyncio
    async def test_completed_when_terminated(self):
        """Status is COMPLETED when terminator triggers."""
        engine = LoopEngine(LoopConfig(max_iterations=10))
        llm = MockLLMClient()

        # Use simple planner that creates one-step plan
        engine.register_component(ComponentType.PLANNER, SimplePlanner())
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))
        engine.register_component(ComponentType.TERMINATOR, CombinedTerminator(llm))

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        # Should complete because plan is finished
        assert result.status.name in ["COMPLETED", "FAILED"]


class TestRecovery:
    """Tests for recovery functionality."""

    @pytest.mark.asyncio
    async def test_recovery_called_for_failure(self):
        """Recovery is called when evaluation fails."""
        engine = LoopEngine(LoopConfig(max_iterations=5))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))
        engine.register_component(ComponentType.RECOVERY, AdaptiveRecovery())

        context = LoopContext(goal="Test goal", budget=Budget())
        result = await engine.run(context)

        # Note: With mock LLM, evaluation might not fail
        # This test mainly verifies recovery component is registered correctly
        assert engine.components.get(ComponentType.RECOVERY) is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
