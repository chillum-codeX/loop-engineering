"""
Core Loop Engine

The main event loop and runtime for executing iterative AI systems.
This module implements the central orchestration logic that coordinates
all components during loop execution.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from .types import (
    AgentMessage,
    Budget,
    ComponentType,
    Evaluation,
    ExecutionMode,
    ExecutionState,
    Failure,
    FailureStatus,
    FailureType,
    LoopContext,
    LoopResult,
    LoopStatus,
    Observation,
    Plan,
    RecoveryAction,
    Step,
)

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    """Configuration for the loop engine."""
    # Execution parameters
    max_iterations: int = 100
    execution_mode: ExecutionMode = ExecutionMode.SINGLE_AGENT

    # Component toggles for ablation studies
    enable_planner: bool = True
    enable_observer: bool = True
    enable_evaluator: bool = True
    enable_recovery: bool = True
    enable_terminator: bool = True
    enable_verification: bool = True
    enable_memory: bool = True
    enable_safety: bool = True

    # Recovery settings
    max_recovery_attempts: int = 3
    recovery_backoff_base: float = 1.0
    circuit_breaker_threshold: int = 5

    # Termination settings
    early_termination_threshold: float = 0.95

    # Logging
    verbose: bool = False
    log_level: str = "INFO"


@dataclass
class ComponentCallCounters:
    """Counters for component calls to verify execution."""
    planner_called: int = 0
    actor_called: int = 0
    observer_called: int = 0
    evaluator_called: int = 0
    verifier_called: int = 0
    safety_check_called: int = 0
    recovery_called: int = 0
    rollback_called: int = 0
    memory_read: int = 0
    memory_write: int = 0
    budget_checked: int = 0
    termination_checked: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "planner_called": self.planner_called,
            "actor_called": self.actor_called,
            "observer_called": self.observer_called,
            "evaluator_called": self.evaluator_called,
            "verifier_called": self.verifier_called,
            "safety_check_called": self.safety_check_called,
            "recovery_called": self.recovery_called,
            "rollback_called": self.rollback_called,
            "memory_read": self.memory_read,
            "memory_write": self.memory_write,
            "budget_checked": self.budget_checked,
            "termination_checked": self.termination_checked,
        }


@dataclass
class LoopState:
    """State maintained during loop execution."""
    status: LoopStatus = LoopStatus.PENDING
    execution_state: ExecutionState = ExecutionState.INITIALIZED
    current_iteration: int = 0
    current_plan: Optional[Plan] = None
    current_step: Optional[Step] = None
    observations: List[Observation] = field(default_factory=list)
    evaluations: List[Evaluation] = field(default_factory=list)
    failures: List[Failure] = field(default_factory=list)
    recoveries: List[RecoveryAction] = field(default_factory=list)
    messages: List[AgentMessage] = field(default_factory=list)
    counters: ComponentCallCounters = field(default_factory=ComponentCallCounters)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "status": self.status.name,
            "execution_state": self.execution_state.value,
            "current_iteration": self.current_iteration,
            "current_plan_id": self.current_plan.id if self.current_plan else None,
            "current_step_id": self.current_step.id if self.current_step else None,
            "num_observations": len(self.observations),
            "num_evaluations": len(self.evaluations),
            "num_failures": len(self.failures),
            "num_recoveries": len(self.recoveries),
            "counters": self.counters.to_dict(),
        }


class ComponentRegistry:
    """
    Validated component registry that enforces type-safe component registration.

    - Accepts only ComponentType enum keys
    - Rejects string keys
    - Validates component implements expected interface
    - Rejects duplicate registration unless replacement is explicit
    """

    def __init__(self):
        self._components: Dict[ComponentType, Any] = {}
        self._interface_map = {
            ComponentType.PLANNER: ['create_plan', 'revise_plan'],
            ComponentType.ACTOR: ['execute', 'execute_direct'],
            ComponentType.OBSERVER: ['observe'],
            ComponentType.EVALUATOR: ['evaluate'],
            ComponentType.RECOVERY: ['recover'],
            ComponentType.TERMINATOR: ['should_terminate'],
        }

    def register(
        self,
        component_type: ComponentType,
        component: Any,
        allow_replace: bool = False
    ) -> None:
        """
        Register a component with strict validation.

        Args:
            component_type: ComponentType enum value
            component: Component instance implementing required interface
            allow_replace: If True, allows replacing existing component

        Raises:
            TypeError: If component_type is not a ComponentType enum
            ValueError: If component doesn't implement required interface
            RuntimeError: If component already registered and allow_replace=False
        """
        # Validate component_type is enum, not string
        if not isinstance(component_type, ComponentType):
            raise TypeError(
                f"Component type must be ComponentType enum, got {type(component_type).__name__}. "
                f"Use ComponentType.{str(component_type).upper()} instead of '{component_type}'"
            )

        # Check for duplicates
        if component_type in self._components and not allow_replace:
            raise RuntimeError(
                f"Component {component_type.value} already registered. "
                f"Use allow_replace=True to replace."
            )

        # Validate interface
        required_methods = self._interface_map.get(component_type, [])
        missing_methods = [
            method for method in required_methods
            if not hasattr(component, method) or not callable(getattr(component, method))
        ]
        if missing_methods:
            raise ValueError(
                f"Component {component_type.value} missing required methods: {missing_methods}"
            )

        self._components[component_type] = component
        logger.debug(f"Registered component: {component_type.value}")

    def get(self, component_type: ComponentType) -> Optional[Any]:
        """Get a registered component."""
        if not isinstance(component_type, ComponentType):
            raise TypeError(f"Component type must be ComponentType enum, got {type(component_type).__name__}")
        return self._components.get(component_type)

    def has(self, component_type: ComponentType) -> bool:
        """Check if component is registered."""
        if not isinstance(component_type, ComponentType):
            raise TypeError(f"Component type must be ComponentType enum, got {type(component_type).__name__}")
        return component_type in self._components

    def list_registered(self) -> List[str]:
        """List registered component type names."""
        return [ct.value for ct in self._components.keys()]

    def clear(self) -> None:
        """Clear all registrations."""
        self._components.clear()


class LoopEngine:
    """
    Main loop engine for executing iterative AI systems.

    The loop engine orchestrates the execution of planning, action, observation,
    evaluation, recovery, and termination components in a coordinated manner.

    Example:
        config = LoopConfig(max_iterations=50)
        engine = LoopEngine(config)

        # Register components using ComponentType enum
        engine.register_component(ComponentType.PLANNER, planner)
        engine.register_component(ComponentType.ACTOR, actor)

        context = LoopContext(goal="Solve a complex problem")
        result = await engine.run(context)
    """

    def __init__(self, config: Optional[LoopConfig] = None):
        self.config = config or LoopConfig()
        self.components = ComponentRegistry()
        self.state: Optional[LoopState] = None
        self.budget: Optional[Budget] = None
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging."""
        level = getattr(logging, self.config.log_level, logging.INFO)
        logging.basicConfig(level=level)

    # Valid state transitions for the execution state machine
    _VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
        ExecutionState.INITIALIZED: {ExecutionState.PLANNING, ExecutionState.FAILED},
        ExecutionState.PLANNING: {ExecutionState.ACTING, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.ACTING: {ExecutionState.OBSERVING, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.OBSERVING: {ExecutionState.EVALUATING, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.EVALUATING: {ExecutionState.VERIFYING, ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.COMPLETED, ExecutionState.FAILED},
        ExecutionState.VERIFYING: {ExecutionState.COMPLETED, ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.FAILED},
        ExecutionState.RECOVERING: {ExecutionState.REPLANNING, ExecutionState.ACTING, ExecutionState.FAILED, ExecutionState.PARTIALLY_COMPLETED},
        ExecutionState.REPLANNING: {ExecutionState.PLANNING, ExecutionState.FAILED},
        ExecutionState.COMPLETED: set(),  # Terminal state
        ExecutionState.PARTIALLY_COMPLETED: set(),  # Terminal state
        ExecutionState.ABSTAINED: set(),  # Terminal state
        ExecutionState.BUDGET_EXHAUSTED: set(),  # Terminal state
        ExecutionState.POLICY_TERMINATED: set(),  # Terminal state
        ExecutionState.FAILED: set(),  # Terminal state
        ExecutionState.WAITING_FOR_HUMAN: {ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.FAILED},
    }

    def _transition_to(self, new_state: ExecutionState) -> None:
        """
        Transition to a new execution state with validation.

        Args:
            new_state: The target execution state

        Raises:
            RuntimeError: If the transition is not valid
        """
        if self.state is None:
            raise RuntimeError("Cannot transition: state is None")

        current_state = self.state.execution_state

        # Check if transition is valid
        valid_next_states = self._VALID_TRANSITIONS.get(current_state, set())
        if new_state not in valid_next_states:
            raise RuntimeError(
                f"Invalid state transition: {current_state.value} -> {new_state.value}. "
                f"Valid transitions from {current_state.value}: {[s.value for s in valid_next_states]}"
            )

        if self.config.verbose:
            logger.info(f"State transition: {current_state.value} -> {new_state.value}")

        self.state.execution_state = new_state

    def register_component(self, component_type: ComponentType, component: Any, allow_replace: bool = False):
        """
        Register a component with the engine.

        Args:
            component_type: ComponentType enum (PLANNER, ACTOR, etc.)
            component: Component instance
            allow_replace: Allow replacing existing registration

        Raises:
            TypeError: If component_type is not ComponentType enum
            ValueError: If component doesn't implement required interface
        """
        self.components.register(component_type, component, allow_replace)

    def get_component(self, component_type: ComponentType) -> Optional[Any]:
        """Get a registered component."""
        return self.components.get(component_type)

    async def run(self, context: LoopContext) -> LoopResult:
        """
        Execute the main loop with explicit state machine tracking.

        Args:
            context: The loop execution context

        Returns:
            LoopResult containing the execution outcome
        """
        start_time = time.time()
        self.state = LoopState(status=LoopStatus.RUNNING, execution_state=ExecutionState.INITIALIZED)
        self.budget = context.budget

        result = LoopResult(status=LoopStatus.RUNNING)

        try:
            # Main execution loop
            while self._should_continue():
                self.state.current_iteration += 1
                iteration_start = time.time()

                if self.config.verbose:
                    logger.info(f"=== Iteration {self.state.current_iteration} ===")

                # Execute one iteration with state tracking
                await self._execute_iteration(context)

                # Update budget
                if self.budget:
                    self.budget.steps_used += 1
                    self.budget.time_used += time.time() - iteration_start

                # Check for termination
                if await self._check_termination(context):
                    break

            # Determine final status - must NOT be RUNNING
            result.status = self._determine_final_status()
            result.output = self._extract_output()
            result.plan = self.state.current_plan
            result.iterations = self.state.current_iteration

        except Exception as e:
            logger.error(f"Loop execution failed: {e}")
            result.status = LoopStatus.FAILED
            if self.state:
                self.state.execution_state = ExecutionState.FAILED
            result.failures.append(Failure(
                type=FailureType.EXECUTION_ERROR,
                message=str(e),
                recoverable=False
            ))
        finally:
            result.execution_time = time.time() - start_time
            result.failures = self.state.failures.copy() if self.state else []
            result.recoveries = self.state.recoveries.copy() if self.state else []
            result.evaluations = self.state.evaluations.copy() if self.state else []
            if self.budget:
                result.token_usage = self.budget.tokens_used
                result.cost = self.budget.cost_used

        return result

    def _should_continue(self) -> bool:
        """Check if the loop should continue executing."""
        if self.state.current_iteration >= self.config.max_iterations:
            logger.info("Max iterations reached")
            return False

        if self.budget and not self.budget.check_budget():
            logger.info("Budget exhausted")
            self.state.failures.append(Failure(
                type=FailureType.BUDGET_EXCEEDED,
                message="Execution budget has been exhausted",
                recoverable=False
            ))
            self.state.execution_state = ExecutionState.BUDGET_EXHAUSTED
            return False

        if self.state.status in [LoopStatus.TERMINATED, LoopStatus.FAILED]:
            return False

        return True

    async def _execute_iteration(self, context: LoopContext):
        """Execute a single iteration of the loop with state transitions."""
        # 1. PLANNING: Create or revise plan
        if self.config.enable_planner:
            self._transition_to(ExecutionState.PLANNING)
            await self._execute_planning(context)

        # 2. ACTION: Execute current step
        self._transition_to(ExecutionState.ACTING)
        action_result = await self._execute_action(context)

        # 3. OBSERVATION: Capture results
        if self.config.enable_observer:
            self._transition_to(ExecutionState.OBSERVING)
            await self._execute_observation(action_result, context)

        # 4. EVALUATION: Assess progress
        if self.config.enable_evaluator:
            self._transition_to(ExecutionState.EVALUATING)
            evaluation = await self._execute_evaluation(context)

            # 5. RECOVERY: Handle failures if needed
            if self.config.enable_recovery and evaluation and not evaluation.passed:
                await self._execute_recovery(context, evaluation)
                # After recovery, transition back to a valid state for next iteration
                if self.state.execution_state == ExecutionState.RECOVERING:
                    # Stay in recovering or transition to replanning
                    if self.state.failures and any(f.can_recover() for f in self.state.failures):
                        self._transition_to(ExecutionState.REPLANNING)

    async def _execute_planning(self, context: LoopContext):
        """Execute planning phase."""
        planner = self.components.get(ComponentType.PLANNER)
        if not planner:
            return

        self.state.counters.planner_called += 1

        # Create initial plan if none exists
        if not self.state.current_plan:
            plan = await planner.create_plan(context.goal, context.initial_context)
            self.state.current_plan = plan
            if self.config.verbose:
                logger.info(f"Created plan with {len(plan.steps)} steps")
        else:
            # Revise plan if needed
            plan = await planner.revise_plan(
                self.state.current_plan,
                self.state.observations,
                self.state.evaluations
            )
            if plan.version != self.state.current_plan.version:
                self.state.current_plan = plan
                if self.config.verbose:
                    logger.info(f"Revised plan to version {plan.version}")

    async def _execute_action(self, context: LoopContext) -> Any:
        """Execute action phase."""
        actor = self.components.get(ComponentType.ACTOR)
        if not actor:
            return None

        self.state.counters.actor_called += 1

        # Get next step from plan
        if self.state.current_plan:
            step = self.state.current_plan.get_next_step()
            self.state.current_step = step
        else:
            step = None

        if step:
            step.status = "in_progress"
            step.start_time = time.time()

            try:
                result = await actor.execute(step, self.state.observations, context)
                step.output = result
                step.status = "completed"
                step.end_time = time.time()

                if self.config.verbose:
                    logger.info(f"Executed step {step.id}: {step.description[:50]}...")

            except Exception as e:
                step.status = "failed"
                self.state.failures.append(Failure(
                    type=FailureType.EXECUTION_ERROR,
                    message=str(e),
                    step_id=step.id,
                    recoverable=True
                ))
                return None
        else:
            # No steps available - direct execution
            result = await actor.execute_direct(context.goal, context)

        return result

    async def _execute_observation(self, action_result: Any, context: LoopContext):
        """Execute observation phase."""
        observer = self.components.get(ComponentType.OBSERVER)
        if not observer:
            return

        self.state.counters.observer_called += 1

        observation = await observer.observe(
            action_result,
            self.state.current_step,
            context
        )
        self.state.observations.append(observation)

        if self.config.verbose:
            logger.debug(f"Observation recorded from {observation.source}")

    async def _execute_evaluation(self, context: LoopContext) -> Optional[Evaluation]:
        """Execute evaluation phase."""
        evaluator = self.components.get(ComponentType.EVALUATOR)
        if not evaluator:
            return None

        self.state.counters.evaluator_called += 1

        evaluation = await evaluator.evaluate(
            self.state.current_plan,
            self.state.observations,
            context.goal,
            context
        )
        self.state.evaluations.append(evaluation)

        if self.config.verbose:
            logger.info(f"Evaluation: score={evaluation.score:.2f}, passed={evaluation.passed}")

        return evaluation

    async def _execute_recovery(self, context: LoopContext, evaluation: Evaluation):
        """
        Execute recovery phase with explicit failure lifecycle tracking.

        The failure lifecycle:
        UNHANDLED -> RECOVERY_PLANNED -> RECOVERY_IN_PROGRESS -> RECOVERED/RECOVERY_FAILED
        """
        recovery = self.components.get(ComponentType.RECOVERY)
        if not recovery:
            return

        # Get recent UNHANDLED failures (using explicit FailureStatus)
        recent_failures = [
            f for f in self.state.failures
            if f.status == FailureStatus.UNHANDLED and f.can_recover()
        ]

        if not recent_failures:
            return

        # Get the most recent unhandled failure
        failure = recent_failures[-1]

        # Mark failure as having recovery planned
        failure.status = FailureStatus.RECOVERY_PLANNED

        # Transition to RECOVERING state
        self._transition_to(ExecutionState.RECOVERING)
        self.state.status = LoopStatus.RECOVERING

        try:
            recovery_action = await recovery.recover(
                failure,
                self.state,
                context
            )

            # Link recovery action to failure using failure_id
            recovery_action.failure_id = failure.failure_id
            recovery_action.executed = True

            # Record the recovery attempt on the failure
            failure.record_recovery_attempt(recovery_action.action_id)

            self.state.recoveries.append(recovery_action)
            self.state.counters.recovery_called += 1

            # Check if recovery action succeeded
            if recovery_action.success:
                failure.mark_recovered()
                if self.config.verbose:
                    logger.info(f"Recovery succeeded for failure {failure.failure_id}")
            else:
                # Check if max attempts reached
                if not failure.can_recover():
                    failure.mark_terminal()
                    if self.config.verbose:
                        logger.warning(f"Recovery failed for failure {failure.failure_id}: max attempts reached")

            if self.config.verbose:
                logger.info(f"Recovery action: {recovery_action.strategy.value} for failure {failure.failure_id}")

        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            failure.record_recovery_attempt(f"error_{str(uuid.uuid4())[:8]}")
            if not failure.can_recover():
                failure.mark_terminal()

    async def _check_termination(self, context: LoopContext) -> bool:
        """Check if loop should terminate."""
        self.state.counters.termination_checked += 1

        terminator = self.components.get(ComponentType.TERMINATOR)
        if not terminator:
            # Simple termination: goal achieved or plan completed
            if self.state.current_plan:
                progress = self.state.current_plan.get_progress()
                if progress >= 1.0:
                    return True
            return False

        should_terminate = await terminator.should_terminate(
            self.state,
            context.goal,
            context
        )

        if should_terminate:
            self.state.status = LoopStatus.TERMINATED
            # Don't set execution state here - let _determine_final_status do it

        return should_terminate

    def _determine_final_status(self) -> LoopStatus:
        """Determine the final status of the loop and set execution state."""
        # CRITICAL: Must never return RUNNING after execution completes
        if self.state.status == LoopStatus.TERMINATED:
            self.state.execution_state = ExecutionState.COMPLETED
            return LoopStatus.COMPLETED
        elif any(f.status == FailureStatus.TERMINAL for f in self.state.failures):
            self.state.execution_state = ExecutionState.FAILED
            return LoopStatus.FAILED
        elif self.state.current_plan and self.state.current_plan.get_progress() >= 1.0:
            self.state.execution_state = ExecutionState.COMPLETED
            return LoopStatus.COMPLETED
        elif self.state.execution_state == ExecutionState.BUDGET_EXHAUSTED:
            return LoopStatus.FAILED
        elif self.state.execution_state == ExecutionState.RECOVERING:
            # After recovery, check if we can complete
            if self.state.current_plan and self.state.current_plan.get_progress() >= 1.0:
                self.state.execution_state = ExecutionState.COMPLETED
                return LoopStatus.COMPLETED
            self.state.execution_state = ExecutionState.FAILED
            return LoopStatus.FAILED
        elif self.state.current_iteration >= self.config.max_iterations:
            self.state.execution_state = ExecutionState.BUDGET_EXHAUSTED
            return LoopStatus.FAILED
        else:
            # Default: if we exited the loop without termination, it's a failure
            self.state.execution_state = ExecutionState.FAILED
            return LoopStatus.FAILED

    def _extract_output(self) -> Any:
        """Extract the final output from execution state."""
        # Try to get output from completed plan
        if self.state.current_plan:
            completed_steps = [s for s in self.state.current_plan.steps
                             if s.status == "completed" and s.output is not None]
            if completed_steps:
                # Return the last completed step's output
                return completed_steps[-1].output

        # Try to get from observations
        if self.state.observations:
            return self.state.observations[-1].content

        return None

    async def pause(self):
        """Pause loop execution."""
        if self.state:
            self.state.status = LoopStatus.PAUSED
            logger.info("Loop paused")

    async def resume(self, context: LoopContext) -> LoopResult:
        """Resume loop execution."""
        if self.state and self.state.status == LoopStatus.PAUSED:
            self.state.status = LoopStatus.RUNNING
            return await self.run(context)
        else:
            raise RuntimeError("Cannot resume: loop not paused")

    async def abort(self):
        """Abort loop execution."""
        if self.state:
            self.state.status = LoopStatus.TERMINATED
            logger.info("Loop aborted")
