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
    RecoveryStrategy,
    Step,
    StepStatus,
    VerificationResult,
)
from .recovery import RecoveryRegistry

logger = logging.getLogger(__name__)


class MultiAgentOrchestrator:
    """
    Orchestrates multiple agents in multi-agent execution mode.

    Manages agent coordination, message routing, and collective decision-making.
    """

    def __init__(self, engine: 'LoopEngine'):
        self.engine = engine
        self.agents: Dict[str, Any] = {}
        self.agent_roles: Dict[str, str] = {}
        self.message_queue: List[AgentMessage] = []

    def register_agent(self, agent_id: str, agent: Any, role: str = "worker") -> None:
        """Register an agent with the orchestrator."""
        self.agents[agent_id] = agent
        self.agent_roles[agent_id] = role
        logger.debug(f"Registered agent {agent_id} with role {role}")

    async def coordinate_planning(self, context: LoopContext) -> Plan:
        """Collective planning across multiple agents."""
        # Aggregate plans from all agents
        plans = []
        for agent_id, agent in self.agents.items():
            if hasattr(agent, 'create_plan'):
                try:
                    plan = await agent.create_plan(context.goal, context.initial_context)
                    plans.append((agent_id, plan))
                except Exception as e:
                    logger.warning(f"Agent {agent_id} planning failed: {e}")

        if not plans:
            # Fallback to single planner if registered
            planner = self.engine.components.get(ComponentType.PLANNER)
            if planner:
                return await planner.create_plan(context.goal, context.initial_context)
            raise RuntimeError("No agents available for planning")

        # Merge plans or select best (simple: select first for now)
        # TODO: Implement plan merging/consensus
        return plans[0][1]

    async def coordinate_action(self, step: Step, context: LoopContext) -> Any:
        """Execute action with agent coordination."""
        # Route to appropriate agent based on step metadata
        agent_id = step.metadata.get('assigned_agent')

        if agent_id and agent_id in self.agents:
            agent = self.agents[agent_id]
            if hasattr(agent, 'execute'):
                return await agent.execute(step, self.engine.state.observations, context)

        # Fallback to primary actor
        actor = self.engine.components.get(ComponentType.ACTOR)
        if actor:
            return await actor.execute(step, self.engine.state.observations, context)

        raise RuntimeError(f"No agent available to execute step {step.id}")

    async def broadcast_message(self, sender: str, content: Any, message_type: str = "info") -> None:
        """Broadcast a message to all agents."""
        message = AgentMessage(
            sender=sender,
            recipient="",  # Broadcast
            content=content,
            message_type=message_type
        )
        self.message_queue.append(message)
        self.engine.state.messages.append(message)

    async def send_message(self, sender: str, recipient: str, content: Any, message_type: str = "info") -> None:
        """Send a message to a specific agent."""
        message = AgentMessage(
            sender=sender,
            recipient=recipient,
            content=content,
            message_type=message_type
        )
        self.message_queue.append(message)
        self.engine.state.messages.append(message)

    async def collect_evaluations(self, plan: Plan, context: LoopContext) -> List[Evaluation]:
        """Collect evaluations from all agents."""
        evaluations = []
        for agent_id, agent in self.agents.items():
            if hasattr(agent, 'evaluate'):
                try:
                    eval_result = await agent.evaluate(
                        plan,
                        self.engine.state.observations,
                        context.goal,
                        context
                    )
                    evaluations.append(eval_result)
                except Exception as e:
                    logger.warning(f"Agent {agent_id} evaluation failed: {e}")

        # Fallback to registered evaluator
        if not evaluations:
            evaluator = self.engine.components.get(ComponentType.EVALUATOR)
            if evaluator:
                eval_result = await evaluator.evaluate(
                    plan,
                    self.engine.state.observations,
                    context.goal,
                    context
                )
                evaluations.append(eval_result)

        return evaluations


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
            ComponentType.VERIFIER: ['verify'],
            ComponentType.RECOVERY: ['recover'],
            ComponentType.TERMINATOR: ['should_terminate'],
            ComponentType.MEMORY: ['read', 'write'],
            ComponentType.SAFETY: ['check'],
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
        self.recovery_registry = RecoveryRegistry()
        self.orchestrator: Optional[MultiAgentOrchestrator] = None
        self.state: Optional[LoopState] = None
        self.budget: Optional[Budget] = None
        self._setup_logging()

        # Initialize orchestrator for multi-agent mode
        if self.config.execution_mode == ExecutionMode.MULTI_AGENT:
            self.orchestrator = MultiAgentOrchestrator(self)

    def _setup_logging(self):
        """Configure logging."""
        level = getattr(logging, self.config.log_level, logging.INFO)
        logging.basicConfig(level=level)

    # Valid state transitions for the execution state machine
    _VALID_TRANSITIONS: Dict[ExecutionState, Set[ExecutionState]] = {
        # Normal path
        ExecutionState.INITIALIZED: {ExecutionState.PLANNING, ExecutionState.FAILED},
        ExecutionState.PLANNING: {ExecutionState.ACTING, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.ACTING: {ExecutionState.OBSERVING, ExecutionState.EVALUATING, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.OBSERVING: {ExecutionState.EVALUATING, ExecutionState.ITERATION_COMPLETE, ExecutionState.RECOVERING, ExecutionState.FAILED},
        ExecutionState.EVALUATING: {ExecutionState.VERIFYING, ExecutionState.ITERATION_COMPLETE, ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.FAILED},
        ExecutionState.VERIFYING: {ExecutionState.ITERATION_COMPLETE, ExecutionState.RECOVERING, ExecutionState.FAILED},

        # Iteration boundary
        ExecutionState.ITERATION_COMPLETE: {
            ExecutionState.PLANNING,  # Next iteration
            ExecutionState.COMPLETED,  # All done
            ExecutionState.REPLANNING,  # Plan needs update
            ExecutionState.RECOVERING,  # Handle failures
            ExecutionState.WAITING_FOR_HUMAN,  # Escalate
            ExecutionState.BUDGET_EXHAUSTED,  # Out of budget
            ExecutionState.FAILED,  # Unrecoverable
        },

        # Recovery paths
        ExecutionState.RECOVERING: {ExecutionState.REPLANNING, ExecutionState.ITERATION_COMPLETE, ExecutionState.WAITING_FOR_HUMAN, ExecutionState.FAILED, ExecutionState.PARTIALLY_COMPLETED},
        ExecutionState.REPLANNING: {ExecutionState.PLANNING, ExecutionState.FAILED},
        ExecutionState.WAITING_FOR_HUMAN: {ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.FAILED},

        # Terminal states (no outgoing transitions)
        ExecutionState.COMPLETED: set(),
        ExecutionState.PARTIALLY_COMPLETED: set(),
        ExecutionState.ABSTAINED: set(),
        ExecutionState.BUDGET_EXHAUSTED: set(),
        ExecutionState.POLICY_TERMINATED: set(),
        ExecutionState.FAILED: set(),
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

        # Check if current state is terminal
        if current_state in {
            ExecutionState.COMPLETED,
            ExecutionState.PARTIALLY_COMPLETED,
            ExecutionState.ABSTAINED,
            ExecutionState.BUDGET_EXHAUSTED,
            ExecutionState.POLICY_TERMINATED,
            ExecutionState.FAILED,
        }:
            raise RuntimeError(
                f"Cannot transition from terminal state {current_state.value}"
            )

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
        llm = getattr(component, "llm", None)
        if llm is not None and hasattr(llm, "set_usage_callback"):
            llm.set_usage_callback(self._consume_llm_usage)

    def _consume_llm_usage(self, usage: Any) -> None:
        """Apply provider-reported usage to the active loop budget."""
        if self.budget is None:
            return
        self.budget.tokens_used += int(getattr(usage, "total_tokens", 0))
        self.budget.cost_used += float(getattr(usage, "cost", 0.0))

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
            # Main execution loop with iteration boundary
            while True:
                self.state.current_iteration += 1
                iteration_start = time.time()

                if self.config.verbose:
                    logger.info(f"=== Iteration {self.state.current_iteration} ===")

                # Execute one iteration
                await self._execute_iteration(context)

                # At ITERATION_COMPLETE, decide next state
                next_state = await self._handle_iteration_complete(context)

                if next_state in {
                    ExecutionState.COMPLETED,
                    ExecutionState.PARTIALLY_COMPLETED,
                    ExecutionState.ABSTAINED,
                    ExecutionState.BUDGET_EXHAUSTED,
                    ExecutionState.POLICY_TERMINATED,
                    ExecutionState.FAILED,
                }:
                    # Terminal state - break loop
                    self._transition_to(next_state)
                    break
                elif next_state == ExecutionState.PLANNING:
                    # Continue to next iteration
                    self._transition_to(ExecutionState.PLANNING)
                    # Update budget before next iteration
                    if self.budget:
                        self.budget.steps_used += 1
                        self.budget.time_used += time.time() - iteration_start
                    continue
                elif next_state == ExecutionState.RECOVERING:
                    # Handle recovery
                    await self._execute_recovery(context)
                    # After recovery, continue to next iteration or fail
                    if self.state.execution_state == ExecutionState.FAILED:
                        break
                    # Update budget
                    if self.budget:
                        self.budget.steps_used += 1
                        self.budget.time_used += time.time() - iteration_start
                    continue
                elif next_state == ExecutionState.REPLANNING:
                    # Replan and continue
                    self._transition_to(ExecutionState.REPLANNING)
                    await self._execute_replanning(context)
                    # Update budget
                    if self.budget:
                        self.budget.steps_used += 1
                        self.budget.time_used += time.time() - iteration_start
                    continue

            # Build final result
            result = self._build_result(start_time)

        except Exception as e:
            logger.error(f"Loop execution failed: {e}")
            self._handle_exception(e)
            result = self._build_result(start_time)

        return result

    async def _handle_iteration_complete(self, context: LoopContext) -> ExecutionState:
        """
        Decide next state at iteration boundary.

        Returns:
            ExecutionState to transition to
        """
        # 1. Check budget
        if self.budget and not self.budget.check_budget():
            logger.info("Budget exhausted at iteration boundary")
            return ExecutionState.BUDGET_EXHAUSTED

        # 2. Check max iterations
        if self.state.current_iteration >= self.config.max_iterations:
            logger.info("Max iterations reached at iteration boundary")
            return ExecutionState.BUDGET_EXHAUSTED

        # 3. Check for terminal failures
        if any(f.status == FailureStatus.TERMINAL for f in self.state.failures):
            logger.info("Terminal failure detected at iteration boundary")
            return ExecutionState.FAILED

        # 4. Check for unhandled failures requiring recovery
        unhandled_failures = [
            f for f in self.state.failures
            if f.status == FailureStatus.UNHANDLED
        ]
        if unhandled_failures:
            if self.config.enable_recovery:
                logger.info(f"Unhandled failures detected, entering recovery")
                return ExecutionState.RECOVERING
            else:
                logger.info("Unhandled failures with recovery disabled")
                return ExecutionState.FAILED

        # 5. Honor the configured terminator component.
        if self.config.enable_terminator and await self._check_termination(context):
            logger.info("Terminator accepted the completion condition")
            return ExecutionState.COMPLETED

        # 6. Check if plan is complete
        if self.state.current_plan and self._is_plan_complete():
            logger.info("Plan complete - all steps verified")
            return ExecutionState.COMPLETED

        # 7. Continue to next iteration
        return ExecutionState.PLANNING

    def _is_plan_complete(self) -> bool:
        """Check if plan is complete (all required steps verified)."""
        if not self.state.current_plan:
            return False

        for step in self.state.current_plan.steps:
            # Count only VERIFIED_COMPLETED steps
            if step.status != StepStatus.VERIFIED_COMPLETED:
                return False

        return True

    def _build_result(self, start_time: float) -> LoopResult:
        """Build final result from state."""
        result = LoopResult()

        # Determine final status
        if self.state.execution_state == ExecutionState.COMPLETED:
            result.status = LoopStatus.COMPLETED
        elif self.state.execution_state in {
            ExecutionState.BUDGET_EXHAUSTED,
            ExecutionState.FAILED,
            ExecutionState.POLICY_TERMINATED,
        }:
            result.status = LoopStatus.FAILED
        else:
            # Should not happen - force to FAILED
            logger.warning(f"Unexpected final state {self.state.execution_state}, marking as FAILED")
            result.status = LoopStatus.FAILED
            self.state.execution_state = ExecutionState.FAILED

        result.output = self._extract_output()
        result.plan = self.state.current_plan
        result.iterations = self.state.current_iteration
        result.execution_time = time.time() - start_time
        result.failures = self.state.failures.copy()
        result.recoveries = self.state.recoveries.copy()
        result.evaluations = self.state.evaluations.copy()

        # Calculate overall verification status
        if self.state.current_plan:
            verified_steps = [s for s in self.state.current_plan.steps
                            if s.status == StepStatus.VERIFIED_COMPLETED]
            if verified_steps and len(verified_steps) == len(self.state.current_plan.steps):
                result.verification_status = True
            elif verified_steps:
                result.verification_status = None  # Partial
            else:
                result.verification_status = False  # None verified

        if self.budget:
            result.token_usage = self.budget.tokens_used
            result.cost = self.budget.cost_used

        return result

    def _handle_exception(self, e: Exception) -> None:
        """Handle exception during execution."""
        # Create failure record
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message=str(e),
            recoverable=False,
            max_recovery_attempts=self.config.max_recovery_attempts
        )
        failure.mark_terminal()
        self.state.failures.append(failure)

        # Transition to FAILED
        self.state.execution_state = ExecutionState.FAILED
        self.state.status = LoopStatus.FAILED

    async def _execute_replanning(self, context: LoopContext) -> None:
        """Execute replanning after recovery."""
        planner = self.components.get(ComponentType.PLANNER)
        if not planner:
            return

        try:
            plan = await planner.revise_plan(
                self.state.current_plan,
                self.state.observations,
                self.state.evaluations
            )
            self.state.current_plan = plan
            if self.config.verbose:
                logger.info(f"Revised plan to version {plan.version}")
        except Exception as e:
            logger.error(f"Replanning failed: {e}")
            failure = Failure(
                type=FailureType.PLANNING_FAILURE,
                message=f"Replanning failed: {e}",
                recoverable=False,
                max_recovery_attempts=self.config.max_recovery_attempts
            )
            failure.mark_terminal()
            self.state.failures.append(failure)
            self.state.execution_state = ExecutionState.FAILED

    def _should_continue(self) -> bool:
        """Check if the loop should continue executing."""
        # This method is deprecated - iteration control is now in run()
        if self.state.current_iteration >= self.config.max_iterations:
            logger.info("Max iterations reached")
            return False

        if self.budget and not self.budget.check_budget():
            logger.info("Budget exhausted")
            self.state.failures.append(Failure(
                type=FailureType.BUDGET_EXCEEDED,
                message="Execution budget has been exhausted",
                recoverable=False,
                max_recovery_attempts=self.config.max_recovery_attempts
            ))
            self.state.execution_state = ExecutionState.BUDGET_EXHAUSTED
            return False

        if self.state.status in [LoopStatus.TERMINATED, LoopStatus.FAILED]:
            return False

        return True

    async def _execute_iteration(self, context: LoopContext):
        """Execute a single iteration of the loop with state transitions."""
        # Handle entry from ITERATION_COMPLETE -> PLANNING
        if self.state.execution_state == ExecutionState.ITERATION_COMPLETE:
            self._transition_to(ExecutionState.PLANNING)

        # 1. PLANNING: Create or revise plan
        # Safety check before planning
        if self.config.enable_safety:
            if not await self._execute_safety_check(context, 'planning'):
                logger.warning("Safety check failed at planning phase")
                self._transition_to(ExecutionState.FAILED)
                return

        # Read memory before planning if enabled
        if self.config.enable_memory:
            memories = await self._execute_memory_read(context)
            if memories and self.config.verbose:
                logger.debug(f"Loaded {len(memories)} memories for planning")

        if self.config.enable_planner:
            if self.state.execution_state in [ExecutionState.INITIALIZED, ExecutionState.ITERATION_COMPLETE]:
                self._transition_to(ExecutionState.PLANNING)
            elif self.state.execution_state == ExecutionState.REPLANNING:
                # Coming from recovery replanning
                pass
            await self._execute_planning(context)
        else:
            # Without planner, we need a fixed plan or direct execution
            if self.config.verbose:
                logger.debug("Planner disabled - using direct execution or fixed plan")

        # 2. ACTION: Execute current step
        # Safety check before acting
        if self.config.enable_safety:
            if not await self._execute_safety_check(context, 'acting'):
                logger.warning("Safety check failed at acting phase")
                self._transition_to(ExecutionState.FAILED)
                return

        self._transition_to(ExecutionState.ACTING)
        action_result = await self._execute_action(context)

        # Do not evaluate a failed action. Recovery must operate on the
        # original failure evidence instead of creating duplicate failures.
        if self.state.current_step and self.state.current_step.status == StepStatus.FAILED:
            if self.config.enable_recovery:
                await self._execute_recovery(context)
            if self.state.execution_state == ExecutionState.ACTING:
                self._transition_to(ExecutionState.ITERATION_COMPLETE)
            elif self.state.execution_state == ExecutionState.RECOVERING:
                self._transition_to(ExecutionState.ITERATION_COMPLETE)
            if self.config.enable_memory:
                await self._execute_memory_write(context)
            return

        # 3. OBSERVATION: Capture results (if enabled)
        if self.config.enable_observer:
            self._transition_to(ExecutionState.OBSERVING)
            await self._execute_observation(action_result, context)
        else:
            # Observer disabled - skip to evaluation or iteration complete
            if self.config.verbose:
                logger.debug("Observer disabled - skipping observation")

        # 4. EVALUATION: Assess progress (if enabled)
        evaluation = None
        if self.config.enable_evaluator:
            if self.state.execution_state == ExecutionState.OBSERVING:
                self._transition_to(ExecutionState.EVALUATING)
            elif self.state.execution_state == ExecutionState.ACTING:
                # Observer was disabled
                self._transition_to(ExecutionState.EVALUATING)

            evaluation = await self._execute_evaluation(context)

            # 5. RECOVERY: Handle failures if needed
            if self.config.enable_recovery and evaluation and not evaluation.passed:
                await self._execute_recovery(context, evaluation)
                # After recovery, we'll be in RECOVERING or REPLANNING state
        else:
            # Evaluator disabled - skip to verification or iteration complete
            if self.config.verbose:
                logger.debug("Evaluator disabled - skipping evaluation")

        # 6. VERIFICATION: Final verification check (if enabled)
        verification = None
        if self.config.enable_verification and self.state.execution_state == ExecutionState.EVALUATING:
            if evaluation and evaluation.passed:
                self._transition_to(ExecutionState.VERIFYING)
                verification = await self._execute_verification(context)

                # Handle verification failure
                if self.config.enable_recovery and verification and not verification.verified:
                    await self._execute_recovery(context)
        elif self.config.enable_verification and self.state.execution_state not in [
            ExecutionState.RECOVERING, ExecutionState.REPLANNING, ExecutionState.FAILED
        ]:
            # If we skipped evaluation but verification is enabled, we still need to verify
            # This handles the case where observer is disabled but verifier is enabled
            if self.state.current_step and self.state.current_step.status == StepStatus.EXECUTED:
                self._transition_to(ExecutionState.VERIFYING)
                verification = await self._execute_verification(context)

                # Handle verification failure
                if self.config.enable_recovery and verification and not verification.verified:
                    await self._execute_recovery(context)

        # Transition to ITERATION_COMPLETE at end of iteration
        # Determine the correct path based on current state
        if self.state.execution_state == ExecutionState.VERIFYING:
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        elif self.state.execution_state == ExecutionState.EVALUATING:
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        elif self.state.execution_state == ExecutionState.OBSERVING:
            # Evaluator disabled path
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        elif self.state.execution_state == ExecutionState.ACTING:
            # Both observer and evaluator disabled path
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        elif self.state.execution_state == ExecutionState.RECOVERING:
            # After recovery, transition to ITERATION_COMPLETE
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        elif self.state.execution_state == ExecutionState.REPLANNING:
            # After replanning, transition to ITERATION_COMPLETE
            self._transition_to(ExecutionState.ITERATION_COMPLETE)
        else:
            # Already in terminal state or unexpected state
            if self.config.verbose:
                logger.debug(f"Iteration ending in state {self.state.execution_state.value}")

        # Write memory at end of iteration if enabled
        if self.config.enable_memory:
            await self._execute_memory_write(context)

    async def _execute_planning(self, context: LoopContext):
        """Execute planning phase."""
        # Multi-agent mode: use orchestrator
        if self.config.execution_mode == ExecutionMode.MULTI_AGENT and self.orchestrator:
            self.state.counters.planner_called += 1
            try:
                if not self.state.current_plan:
                    plan = await self.orchestrator.coordinate_planning(context)
                    self.state.current_plan = plan
                    if self.config.verbose:
                        logger.info(f"Created multi-agent plan with {len(plan.steps)} steps")
                else:
                    # Revise plan
                    planner = self.components.get(ComponentType.PLANNER)
                    if planner:
                        plan = await planner.revise_plan(
                            self.state.current_plan,
                            self.state.observations,
                            self.state.evaluations
                        )
                        if plan.version != self.state.current_plan.version:
                            self.state.current_plan = plan
                            if self.config.verbose:
                                logger.info(f"Revised plan to version {plan.version}")
            except Exception as e:
                logger.error(f"Multi-agent planning failed: {e}")
                raise
            return

        # Single-agent mode: use registered planner
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
        """Execute action phase with proper step lifecycle."""
        # Multi-agent mode: use orchestrator
        if self.config.execution_mode == ExecutionMode.MULTI_AGENT and self.orchestrator:
            self.state.counters.actor_called += 1

            # Get next step from plan
            if self.state.current_plan:
                step = self.state.current_plan.get_next_step()
                self.state.current_step = step
            else:
                step = None

            if step:
                step.status = StepStatus.IN_PROGRESS
                step.start_time = time.time()

                try:
                    result = await self.orchestrator.coordinate_action(step, context)
                    step.output = result
                    step.status = StepStatus.EXECUTED
                    step.end_time = time.time()

                    if self.config.verbose:
                        logger.info(f"Executed step {step.id}: {step.description[:50]}...")

                except Exception as e:
                    step.status = StepStatus.FAILED
                    failure = Failure(
                        type=FailureType.EXECUTION_ERROR,
                        message=str(e),
                        step_id=step.id,
                        recoverable=True,
                        max_recovery_attempts=self.config.max_recovery_attempts
                    )
                    self.state.failures.append(failure)
                    return None
            else:
                # No steps available
                result = None

            return result

        # Single-agent mode: use registered actor
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
            # Actor sets IN_PROGRESS when starting
            step.status = StepStatus.IN_PROGRESS
            step.start_time = time.time()

            try:
                result = await actor.execute(step, self.state.observations, context)
                step.output = result

                # Actor sets EXECUTED when completing (NOT completed - that's for evaluator/verifier)
                step.status = StepStatus.EXECUTED
                step.end_time = time.time()

                if self.config.verbose:
                    logger.info(f"Executed step {step.id}: {step.description[:50]}...")

            except Exception as e:
                # Actor failure creates FAILURE status
                step.status = StepStatus.FAILED
                failure = Failure(
                    type=FailureType.EXECUTION_ERROR,
                    message=str(e),
                    step_id=step.id,
                    recoverable=True,
                    max_recovery_attempts=self.config.max_recovery_attempts
                )
                self.state.failures.append(failure)
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
        """Execute evaluation phase with proper step lifecycle."""
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

        # Update current step status based on evaluation
        if self.state.current_step and evaluation:
            self.state.current_step.evaluation_passed = evaluation.passed

            if evaluation.passed:
                # Evaluator sets EVALUATED (verification will set VERIFIED_COMPLETED)
                self.state.current_step.status = StepStatus.EVALUATED

                # If verification disabled, auto-promote to VERIFIED_COMPLETED
                if not self.config.enable_verification:
                    self.state.current_step.status = StepStatus.VERIFIED_COMPLETED
                    self.state.current_step.verification_passed = True
                    if self.config.verbose:
                        logger.info(f"Step {self.state.current_step.id} completed (verification disabled)")
            else:
                # Evaluator sets EVALUATION_FAILED
                self.state.current_step.status = StepStatus.EVALUATION_FAILED

                # Create failure record
                failure = Failure(
                    type=FailureType.VERIFICATION_FAILED,
                    message=f"Evaluation failed: {evaluation.feedback}",
                    step_id=self.state.current_step.id,
                    recoverable=True,
                    max_recovery_attempts=self.config.max_recovery_attempts
                )
                self.state.failures.append(failure)

        if self.config.verbose:
            logger.info(f"Evaluation: score={evaluation.score:.2f}, passed={evaluation.passed}")

        return evaluation

    async def _execute_verification(self, context: LoopContext) -> Optional[VerificationResult]:
        """Execute verification phase with proper step lifecycle."""
        verifier = self.components.get(ComponentType.VERIFIER)
        if not verifier:
            return None

        self.state.counters.verifier_called += 1

        verification = await verifier.verify(
            self.state.current_step,
            self.state.current_plan,
            self.state.observations,
            context
        )

        # Update current step status based on verification
        if self.state.current_step and verification:
            self.state.current_step.verification_passed = verification.verified

            if verification.verified:
                # Verification passed - step is complete
                self.state.current_step.status = StepStatus.VERIFIED_COMPLETED
                if self.config.verbose:
                    logger.info(f"Step {self.state.current_step.id} verified and completed")
            else:
                # Verification failed
                self.state.current_step.status = StepStatus.VERIFICATION_FAILED

                # Create failure record
                failure = Failure(
                    type=FailureType.VERIFICATION_FAILED,
                    message=f"Verification failed: {verification.issues}",
                    step_id=self.state.current_step.id,
                    recoverable=True,
                    max_recovery_attempts=self.config.max_recovery_attempts
                )
                self.state.failures.append(failure)

        if self.config.verbose:
            logger.info(f"Verification: verified={verification.verified}, confidence={verification.confidence:.2f}")

        return verification

    async def _execute_memory_read(self, context: LoopContext) -> List[Any]:
        """Execute memory read phase."""
        memory = self.components.get(ComponentType.MEMORY)
        if not memory:
            return []

        self.state.counters.memory_read += 1

        try:
            memories = await memory.read(
                query=context.goal,
                context=context,
                limit=10
            )
            if self.config.verbose:
                logger.debug(f"Memory read: {len(memories)} entries retrieved")
            return memories
        except Exception as e:
            logger.warning(f"Memory read failed: {e}")
            return []

    async def _execute_memory_write(self, context: LoopContext) -> bool:
        """Execute memory write phase."""
        memory = self.components.get(ComponentType.MEMORY)
        if not memory:
            return False

        self.state.counters.memory_write += 1

        try:
            # Write relevant execution context to memory
            entry = {
                'goal': context.goal,
                'iteration': self.state.current_iteration,
                'observations': [obs.content for obs in self.state.observations[-3:]],
                'evaluations': [{'score': e.score, 'passed': e.passed} for e in self.state.evaluations[-3:]],
            }

            success = await memory.write(
                content=entry,
                memory_type="working",
                context=context
            )
            if self.config.verbose:
                logger.debug(f"Memory write: {'succeeded' if success else 'failed'}")
            return success
        except Exception as e:
            logger.warning(f"Memory write failed: {e}")
            return False

    async def _execute_safety_check(self, context: LoopContext, phase: str) -> bool:
        """Execute safety check at a specific phase.

        Args:
            context: Loop context
            phase: The phase being checked ('planning', 'acting', 'completion')

        Returns:
            True if safety check passes, False if blocked
        """
        safety = self.components.get(ComponentType.SAFETY)
        if not safety:
            return True

        self.state.counters.safety_check_called += 1

        try:
            check = await safety.check(
                state=self.state,
                phase=phase,
                context=context
            )

            if self.config.verbose:
                logger.info(f"Safety check ({phase}): passed={check.passed}, severity={check.severity}")

            if not check.passed:
                # Create failure record for safety violation
                failure = Failure(
                    type=FailureType.GOAL_HIJACKING if phase == 'planning' else FailureType.EXECUTION_ERROR,
                    message=f"Safety check failed at {phase}: {check.message}",
                    recoverable=False,  # Safety violations are not recoverable
                    max_recovery_attempts=self.config.max_recovery_attempts
                )
                failure.mark_terminal()
                self.state.failures.append(failure)
                return False

            return True
        except Exception as e:
            logger.warning(f"Safety check failed with error: {e}")
            # Fail open - if safety check errors, we allow execution
            return True

    async def _execute_recovery(self, context: LoopContext, evaluation: Optional[Evaluation] = None):
        """
        Execute recovery phase with real recovery handlers.

        The failure lifecycle:
        UNHANDLED -> RECOVERY_PLANNED -> RECOVERY_IN_PROGRESS -> RECOVERED/RECOVERY_FAILED
        """
        # Get unhandled failures
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
            # Use recovery registry to execute strategy
            result = await self.recovery_registry.execute(
                strategy=RecoveryStrategy.RETRY,  # Default to retry
                failure=failure,
                step=self.state.current_step,
                state=self.state,
                context=context
            )

            # Create recovery action record
            from .types import RecoveryAction
            recovery_action = RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                failure_id=failure.failure_id,
                executed=True,
                success=result.success
            )

            # Record the recovery attempt on the failure
            failure.record_recovery_attempt(recovery_action.action_id)

            self.state.recoveries.append(recovery_action)
            self.state.counters.recovery_called += 1

            # Handle result
            if result.success:
                failure.mark_recovered()
                if result.new_state:
                    self._transition_to(result.new_state)
                if self.config.verbose:
                    logger.info(f"Recovery succeeded for failure {failure.failure_id}: {result.message}")
            else:
                # Check if max attempts reached
                if not failure.can_recover():
                    failure.mark_terminal()
                    self.state.execution_state = ExecutionState.FAILED
                    if self.config.verbose:
                        logger.warning(f"Recovery failed for failure {failure.failure_id}: max attempts reached")

        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            failure.record_recovery_attempt(f"error_{str(uuid.uuid4())[:8]}")
            if not failure.can_recover():
                failure.mark_terminal()
                self.state.execution_state = ExecutionState.FAILED

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
            # Get VERIFIED_COMPLETED steps
            completed_steps = [s for s in self.state.current_plan.steps
                             if s.status == StepStatus.VERIFIED_COMPLETED and s.output is not None]
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
