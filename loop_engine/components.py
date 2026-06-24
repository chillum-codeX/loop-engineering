"""
Loop Components

Core components that make up the loop architecture:
- Planner: Decomposes goals into executable steps
- Actor: Executes individual steps
- Observer: Captures execution results
- Evaluator: Assesses progress and quality
- Recovery: Handles failures
- Terminator: Determines when to stop
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .types import (
    Evaluation,
    Failure,
    FailureType,
    LoopContext,
    Observation,
    Plan,
    RecoveryAction,
    RecoveryStrategy,
    Step,
)
from .core import LoopState

logger = logging.getLogger(__name__)


class Planner(ABC):
    """Abstract planner component."""

    @abstractmethod
    async def create_plan(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Create a plan to achieve the goal."""
        pass

    @abstractmethod
    async def revise_plan(
        self,
        current_plan: Plan,
        observations: List[Observation],
        evaluations: List[Evaluation]
    ) -> Plan:
        """Revise the plan based on observations and evaluations."""
        pass


class LLMPlanner(Planner):
    """Planner that uses an LLM to create and revise plans."""

    def __init__(self, llm_client, model: str = "gpt-4"):
        self.llm = llm_client
        self.model = model

    async def create_plan(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Create a plan using LLM."""
        context_str = json.dumps(context, indent=2) if context else "None"

        prompt = f"""You are a task planner. Break down the following goal into concrete, actionable steps.

Goal: {goal}
Context: {context_str}

Create a plan with clear steps. Each step should have:
- A description of what to do
- Any dependencies on previous steps (by step number, 0-indexed)

Respond in this JSON format:
{{
    "steps": [
        {{"description": "step 1 description", "dependencies": []}},
        {{"description": "step 2 description", "dependencies": [0]}},
        ...
    ]
}}
"""

        try:
            response = await self.llm.generate(prompt, model=self.model)
            plan_data = json.loads(response)

            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                step = Step(
                    id=f"step_{i}",
                    description=step_data["description"],
                    dependencies=[f"step_{d}" for d in step_data.get("dependencies", [])]
                )
                steps.append(step)

            return Plan(goal=goal, steps=steps, context=context)

        except Exception as e:
            logger.error(f"Plan creation failed: {e}")
            # Fallback: single-step plan
            return Plan(
                goal=goal,
                steps=[Step(id="step_0", description=goal)],
                context=context
            )

    async def revise_plan(
        self,
        current_plan: Plan,
        observations: List[Observation],
        evaluations: List[Evaluation]
    ) -> Plan:
        """Revise plan based on feedback."""
        # Simple heuristic: if recent evaluation failed, we might need revision
        if not evaluations or evaluations[-1].passed:
            return current_plan

        # Create revised plan with LLM
        obs_str = json.dumps([{"content": str(o.content)} for o in observations[-3:]], indent=2)
        eval_str = json.dumps([{"score": e.score, "feedback": e.feedback} for e in evaluations[-2:]], indent=2)

        prompt = f"""Revise the following plan based on execution feedback.

Original Goal: {current_plan.goal}
Current Steps: {[{"id": s.id, "desc": s.description, "status": s.status} for s in current_plan.steps]}

Recent Observations: {obs_str}
Recent Evaluations: {eval_str}

Create a revised plan. Respond in JSON format:
{{
    "steps": [
        {{"description": "step description", "dependencies": []}},
        ...
    ]
}}
"""

        try:
            response = await self.llm.generate(prompt, model=self.model)
            plan_data = json.loads(response)

            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                step = Step(
                    id=f"step_{i}",
                    description=step_data["description"],
                    dependencies=[f"step_{d}" for d in step_data.get("dependencies", [])]
                )
                steps.append(step)

            new_plan = Plan(
                goal=current_plan.goal,
                steps=steps,
                context=current_plan.context,
                version=current_plan.version + 1
            )
            return new_plan

        except Exception as e:
            logger.error(f"Plan revision failed: {e}")
            return current_plan


class SimplePlanner(Planner):
    """Simple heuristic planner without LLM."""

    async def create_plan(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Create a simple single-step plan."""
        return Plan(
            goal=goal,
            steps=[Step(id="step_0", description=goal)],
            context=context
        )

    async def revise_plan(
        self,
        current_plan: Plan,
        observations: List[Observation],
        evaluations: List[Evaluation]
    ) -> Plan:
        """No revision for simple planner."""
        return current_plan


class Actor(ABC):
    """Abstract actor component for executing steps."""

    @abstractmethod
    async def execute(
        self,
        step: Step,
        observations: List[Observation],
        context: LoopContext
    ) -> Any:
        """Execute a step."""
        pass

    @abstractmethod
    async def execute_direct(self, goal: str, context: LoopContext) -> Any:
        """Execute without a plan step."""
        pass


class LLMActor(Actor):
    """Actor that uses an LLM to execute steps."""

    def __init__(self, llm_client, model: str = "gpt-4"):
        self.llm = llm_client
        self.model = model

    async def execute(
        self,
        step: Step,
        observations: List[Observation],
        context: LoopContext
    ) -> Any:
        """Execute a step using LLM."""
        obs_context = "\n".join([
            f"- {o.source}: {str(o.content)[:200]}"
            for o in observations[-5:]
        ])

        prompt = f"""Execute the following step in the context of the overall goal.

Overall Goal: {context.goal}
Current Step: {step.description}

Previous Observations:
{obs_context}

Execute this step and provide a clear, actionable result.
"""

        response = await self.llm.generate(prompt, model=self.model)
        return response.strip()

    async def execute_direct(self, goal: str, context: LoopContext) -> Any:
        """Execute the goal directly."""
        prompt = f"""Execute the following task directly:

Task: {goal}

Provide a clear, actionable result.
"""
        response = await self.llm.generate(prompt, model=self.model)
        return response.strip()


class ToolActor(Actor):
    """Actor that can use tools."""

    def __init__(self, llm_client, tools: Dict[str, Any], model: str = "gpt-4"):
        self.llm = llm_client
        self.tools = tools
        self.model = model

    async def execute(
        self,
        step: Step,
        observations: List[Observation],
        context: LoopContext
    ) -> Any:
        """Execute with tool use."""
        # Check if step mentions any tools
        for tool_name, tool_func in self.tools.items():
            if tool_name.lower() in step.description.lower():
                try:
                    result = await tool_func(step.description)
                    return f"Tool '{tool_name}' result: {result}"
                except Exception as e:
                    return f"Tool '{tool_name}' failed: {e}"

        # Fall back to LLM
        actor = LLMActor(self.llm, self.model)
        return await actor.execute(step, observations, context)

    async def execute_direct(self, goal: str, context: LoopContext) -> Any:
        """Execute directly with potential tool use."""
        for tool_name, tool_func in self.tools.items():
            if tool_name.lower() in goal.lower():
                try:
                    result = await tool_func(goal)
                    return f"Tool '{tool_name}' result: {result}"
                except Exception as e:
                    return f"Tool '{tool_name}' failed: {e}"

        actor = LLMActor(self.llm, self.model)
        return await actor.execute_direct(goal, context)


class Observer(ABC):
    """Abstract observer component."""

    @abstractmethod
    async def observe(
        self,
        action_result: Any,
        step: Optional[Step],
        context: LoopContext
    ) -> Observation:
        """Create an observation from action results."""
        pass


class SimpleObserver(Observer):
    """Simple observer that captures raw results."""

    async def observe(
        self,
        action_result: Any,
        step: Optional[Step],
        context: LoopContext
    ) -> Observation:
        """Create simple observation."""
        return Observation(
            content=action_result,
            source="actor",
            step_id=step.id if step else None
        )


class StructuredObserver(Observer):
    """Observer that structures observations."""

    async def observe(
        self,
        action_result: Any,
        step: Optional[Step],
        context: LoopContext
    ) -> Observation:
        """Create structured observation."""
        structured = {
            "raw_result": str(action_result)[:1000],
            "length": len(str(action_result)),
            "step_description": step.description if step else None,
        }

        return Observation(
            content=structured,
            source="structured_observer",
            step_id=step.id if step else None
        )


class Evaluator(ABC):
    """Abstract evaluator component."""

    @abstractmethod
    async def evaluate(
        self,
        plan: Optional[Plan],
        observations: List[Observation],
        goal: str,
        context: LoopContext
    ) -> Evaluation:
        """Evaluate progress toward goal."""
        pass


class SimpleEvaluator(Evaluator):
    """Simple evaluator using heuristics."""

    async def evaluate(
        self,
        plan: Optional[Plan],
        observations: List[Observation],
        goal: str,
        context: LoopContext
    ) -> Evaluation:
        """Simple heuristic evaluation."""
        if not observations:
            return Evaluation(score=0.0, passed=False, feedback="No observations yet")

        # Check plan progress
        if plan:
            progress = plan.get_progress()
            passed = progress >= 1.0
            return Evaluation(
                score=progress,
                passed=passed,
                feedback=f"Plan {progress*100:.1f}% complete",
                metrics={"progress": progress, "steps_total": len(plan.steps)}
            )

        # Fallback: check if we have results
        has_result = observations[-1].content is not None
        return Evaluation(
            score=1.0 if has_result else 0.0,
            passed=has_result,
            feedback="Has result" if has_result else "No result"
        )


class LLMEvaluator(Evaluator):
    """Evaluator using LLM for assessment."""

    def __init__(self, llm_client, model: str = "gpt-4"):
        self.llm = llm_client
        self.model = model

    async def evaluate(
        self,
        plan: Optional[Plan],
        observations: List[Observation],
        goal: str,
        context: LoopContext
    ) -> Evaluation:
        """Use LLM to evaluate progress."""
        if not observations:
            return Evaluation(score=0.0, passed=False, feedback="No observations yet")

        obs_str = "\n".join([
            f"- {str(o.content)[:300]}"
            for o in observations[-3:]
        ])

        prompt = f"""Evaluate the progress toward the goal based on observations.

Goal: {goal}

Recent Observations:
{obs_str}

Rate the progress from 0.0 to 1.0 and indicate if the goal appears complete.
Respond in this JSON format:
{{
    "score": 0.8,
    "complete": true,
    "feedback": "brief explanation"
}}
"""

        try:
            response = await self.llm.generate(prompt, model=self.model)
            eval_data = json.loads(response)

            return Evaluation(
                score=float(eval_data.get("score", 0.0)),
                passed=eval_data.get("complete", False),
                feedback=eval_data.get("feedback", ""),
                metrics={"raw_score": eval_data.get("score", 0.0)}
            )
        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return Evaluation(score=0.0, passed=False, feedback=f"Evaluation error: {e}")


class Recovery(ABC):
    """Abstract recovery component."""

    @abstractmethod
    async def recover(
        self,
        failure: Failure,
        state: LoopState,
        context: LoopContext
    ) -> RecoveryAction:
        """Determine recovery action for a failure."""
        pass


class SimpleRecovery(Recovery):
    """Simple recovery with backoff strategy."""

    async def recover(
        self,
        failure: Failure,
        state: LoopState,
        context: LoopContext
    ) -> RecoveryAction:
        """Simple recovery logic."""
        # Count recovery attempts for this failure type
        attempts = sum(1 for r in state.recoveries if r.params.get("failure_type") == failure.type.value)

        if attempts == 0:
            return RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                params={"failure_id": failure, "failure_type": failure.type.value},
                estimated_success=0.7
            )
        elif attempts == 1:
            return RecoveryAction(
                strategy=RecoveryStrategy.BACKOFF,
                params={"failure_id": failure, "failure_type": failure.type.value, "delay": 2.0},
                estimated_success=0.5
            )
        else:
            return RecoveryAction(
                strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                params={"failure_id": failure, "failure_type": failure.type.value},
                estimated_success=0.3
            )


class AdaptiveRecovery(Recovery):
    """Adaptive recovery with context-aware strategies."""

    async def recover(
        self,
        failure: Failure,
        state: LoopState,
        context: LoopContext
    ) -> RecoveryAction:
        """Context-aware recovery."""
        # Select strategy based on failure type
        if failure.type == FailureType.TIMEOUT:
            return RecoveryAction(
                strategy=RecoveryStrategy.BACKOFF,
                params={"delay": 5.0, "failure_id": id(failure)},
                estimated_success=0.6
            )
        elif failure.type == FailureType.VERIFICATION_FAILED:
            return RecoveryAction(
                strategy=RecoveryStrategy.PLAN_REVISION,
                params={"failure_id": id(failure)},
                estimated_success=0.5
            )
        elif failure.type == FailureType.INVALID_OUTPUT:
            return RecoveryAction(
                strategy=RecoveryStrategy.RETRY,
                params={"failure_id": id(failure)},
                estimated_success=0.7
            )
        elif failure.type in [FailureType.GOAL_HIJACKING, FailureType.SEMANTIC_DRIFT]:
            return RecoveryAction(
                strategy=RecoveryStrategy.CIRCUIT_BREAK,
                params={"failure_id": id(failure), "reason": "security_concern"},
                estimated_success=0.1
            )
        else:
            return RecoveryAction(
                strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                params={"failure_id": id(failure)},
                estimated_success=0.4
            )


class Terminator(ABC):
    """Abstract terminator component."""

    @abstractmethod
    async def should_terminate(
        self,
        state: LoopState,
        goal: str,
        context: LoopContext
    ) -> bool:
        """Determine if loop should terminate."""
        pass


class SimpleTerminator(Terminator):
    """Simple terminator based on plan completion."""

    async def should_terminate(
        self,
        state: LoopState,
        goal: str,
        context: LoopContext
    ) -> bool:
        """Check if plan is complete."""
        if not state.current_plan:
            return False

        return state.current_plan.get_progress() >= 1.0


class GoalBasedTerminator(Terminator):
    """Terminator that checks goal achievement."""

    def __init__(self, llm_client, threshold: float = 0.9, model: str = "gpt-4"):
        self.llm = llm_client
        self.threshold = threshold
        self.model = model

    async def should_terminate(
        self,
        state: LoopState,
        goal: str,
        context: LoopContext
    ) -> bool:
        """Check goal achievement with LLM."""
        if not state.evaluations:
            return False

        latest_eval = state.evaluations[-1]

        # Quick check: if evaluation passed, terminate
        if latest_eval.passed and latest_eval.score >= self.threshold:
            return True

        # Check if plan is complete
        if state.current_plan and state.current_plan.get_progress() >= 1.0:
            return True

        return False


class CombinedTerminator(Terminator):
    """Terminator combining multiple conditions."""

    def __init__(self, llm_client=None, threshold: float = 0.9, model: str = "gpt-4"):
        self.llm = llm_client
        self.threshold = threshold
        self.model = model

    async def should_terminate(
        self,
        state: LoopState,
        goal: str,
        context: LoopContext
    ) -> bool:
        """Check multiple termination conditions."""
        # Condition 1: Plan completed
        if state.current_plan and state.current_plan.get_progress() >= 1.0:
            return True

        # Condition 2: Recent evaluation passed with high score
        if state.evaluations:
            latest = state.evaluations[-1]
            if latest.passed and latest.score >= self.threshold:
                return True

        # Condition 3: Multiple consecutive high evaluations
        if len(state.evaluations) >= 2:
            recent = state.evaluations[-2:]
            if all(e.score >= self.threshold for e in recent):
                return True

        # Condition 4: Goal explicitly achieved in observation
        if state.observations:
            last_obs = str(state.observations[-1].content).lower()
            if "goal achieved" in last_obs or "task complete" in last_obs:
                return True

        return False
