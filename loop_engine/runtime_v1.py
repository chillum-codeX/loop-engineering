"""Executable five-phase runtime for Loop Engineering.

The runtime deliberately keeps external side effects behind future adapters.
Its built-in execution mode discovers skill contracts, reserves bounded work,
verifies those contracts deterministically, persists the ledger, and schedules
the next task. This gives the CLI a safe, real execution path without claiming
to perform GitHub, Slack, or model actions that were not configured.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .runtime_contracts import (
    BudgetReservation,
    BudgetReservationStatus,
    DiscoveryStatus,
    EventType,
    GateOutcomeData,
    HandoffStatus,
    PersistenceStatus,
    RuntimeConfig,
    RuntimeEvent,
    RuntimePhase,
    RuntimeResult,
    RuntimeState,
    SchedulingStatus,
    TaskPriority,
    TaskRecord,
    TaskStatus,
    VerificationOutcome,
    VerificationStatus,
)
from .runtime_persistence import RuntimePersistenceConfig, RuntimeStatePersistence
from .skills import SkillDefinition, SkillLoader, SkillValidator
from .types import LoopStatus


class LoopRuntime:
    """Coordinate discovery, handoff, verification, persistence, and scheduling."""

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        task_handlers: Optional[Dict[str, Callable[[TaskRecord], Any]]] = None,
    ):
        self.config = config or RuntimeConfig()
        self.config.discovery.skills_dir = Path(self.config.discovery.skills_dir)
        self.config.discovery.state_dir = Path(self.config.discovery.state_dir)
        self.config.persistence.state_dir = Path(self.config.persistence.state_dir)
        self.config.handoff.worktrees_dir = Path(self.config.handoff.worktrees_dir)
        persistence_backend = self.config.persistence.format.lower()
        self.persistence = RuntimeStatePersistence(
            RuntimePersistenceConfig(
                state_dir=self.config.persistence.state_dir,
                backend=persistence_backend,
                auto_save=self.config.persistence.auto_save,
                save_interval_seconds=self.config.persistence.save_interval_seconds,
                max_history=self.config.persistence.max_history,
            )
        )
        self.skill_loader = SkillLoader(self.config.discovery.skills_dir)
        self.events: List[RuntimeEvent] = []
        loaded_state = None
        if self.config.trace_id and self.config.discovery.load_latest_on_start:
            loaded_state = self.persistence.load(self.config.trace_id)
        self.state = loaded_state or RuntimeState(
            runtime_id=self.config.runtime_id,
            trace_id=self.config.trace_id or str(uuid.uuid4())[:8],
        )
        if loaded_state is not None:
            self._event(
                EventType.STATE_LOADED,
                trace_id=self.config.trace_id,
            )
        self._skills: Dict[str, SkillDefinition] = {}
        self.task_handlers = task_handlers or {}

    def _event(
        self,
        event_type: EventType,
        *,
        phase: Optional[RuntimePhase] = None,
        task_id: Optional[str] = None,
        **details,
    ) -> None:
        self.events.append(
            RuntimeEvent(
                event_type=event_type,
                trace_id=self.state.trace_id or "",
                task_id=task_id,
                phase=phase,
                details=details,
            )
        )

    def _set_phase(self, phase: RuntimePhase) -> None:
        self.state.set_phase(phase)
        self._event(EventType.PHASE_STARTED, phase=phase)

    def _complete_phase(self, phase: RuntimePhase) -> None:
        self._event(EventType.PHASE_COMPLETED, phase=phase)

    def _discover(self) -> None:
        phase = RuntimePhase.DISCOVERY
        self._set_phase(phase)
        self.state.set_phase_status(phase, DiscoveryStatus.LOADING_SKILLS)
        self._skills = self.skill_loader.load_all()

        self.state.set_phase_status(phase, DiscoveryStatus.BUILDING_LEDGER)
        existing = {
            task.skill_name
            for task in self.state.task_ledger.tasks.values()
            if task.skill_name
        }
        for skill in self._skills.values():
            if skill.name in existing:
                continue
            task = TaskRecord(
                skill_name=skill.name,
                goal=skill.output or skill.judge or f"Validate skill {skill.name}",
                priority=self.config.discovery.default_priority,
                context={
                    "source_file": str(skill.source_file) if skill.source_file else None,
                    "execution_mode": "contract_validation",
                },
            )
            self.state.task_ledger.add_task(task)
            self._event(
                EventType.TASK_DISCOVERED,
                phase=phase,
                task_id=task.task_id,
                skill_name=skill.name,
            )

        status = (
            DiscoveryStatus.COMPLETE
            if self.state.task_ledger.get_pending_tasks()
            else DiscoveryStatus.NO_TASKS
        )
        self.state.set_phase_status(phase, status)
        self._complete_phase(phase)

    def _handoff(self, task: TaskRecord) -> None:
        phase = RuntimePhase.HANDOFF
        self._set_phase(phase)
        self.state.set_phase_status(phase, HandoffStatus.RESERVING_BUDGET)
        reservation = BudgetReservation(
            task_id=task.task_id,
            reserved_tokens=self.config.handoff.default_token_budget,
            reserved_cost=self.config.handoff.default_cost_budget,
            reserved_steps=self.config.handoff.default_step_budget,
        )
        self.state.active_reservation = reservation
        task.budget_reservation_id = reservation.reservation_id
        task.transition_to(TaskStatus.RESERVED)
        self._event(
            EventType.BUDGET_RESERVED,
            phase=phase,
            task_id=task.task_id,
            reservation_id=reservation.reservation_id,
        )
        self._event(EventType.TASK_RESERVED, phase=phase, task_id=task.task_id)
        self.state.set_phase_status(phase, HandoffStatus.READY)
        self._complete_phase(phase)

    def _verify(self, task: TaskRecord) -> bool:
        phase = RuntimePhase.VERIFICATION
        self._set_phase(phase)
        task.transition_to(TaskStatus.IN_PROGRESS)
        self._event(EventType.TASK_STARTED, phase=phase, task_id=task.task_id)
        task.transition_to(TaskStatus.VERIFYING)
        self.state.set_phase_status(phase, VerificationStatus.PRE_GATES)

        skill = self._skills.get(task.skill_name or "")
        outcomes: List[GateOutcomeData] = []
        if skill is None:
            outcomes.append(
                GateOutcomeData(
                    gate_name="skill_exists",
                    passed=False,
                    message=f"Skill {task.skill_name!r} was not loaded",
                )
            )
        else:
            validation = SkillValidator.validate(skill)
            outcomes.append(
                GateOutcomeData(
                    gate_name="skill_contract",
                    passed=validation.is_valid,
                    message=(
                        "Skill contract is valid"
                        if validation.is_valid
                        else "; ".join(validation.issues)
                    ),
                    details={"warnings": validation.warnings},
                )
            )
            if "security" in self.config.verification.mandatory_gates:
                outcomes.append(
                    GateOutcomeData(
                        gate_name="security_boundaries",
                        passed=bool(skill.stop),
                        message=(
                            "STOP boundaries are declared"
                            if skill.stop
                            else "Skill has no STOP boundaries"
                        ),
                    )
                )

            handler = self.task_handlers.get(skill.name)
            if handler and all(outcome.passed for outcome in outcomes):
                try:
                    output = handler(task)
                    task.context["execution_output"] = output
                    outcomes.append(
                        GateOutcomeData(
                            gate_name="task_handler",
                            passed=True,
                            message=f"Handler executed for {skill.name}",
                        )
                    )
                except Exception as exc:
                    task.context["execution_error"] = str(exc)
                    outcomes.append(
                        GateOutcomeData(
                            gate_name="task_handler",
                            passed=False,
                            message=f"Handler failed: {exc}",
                        )
                    )

        for outcome in outcomes:
            self._event(
                EventType.GATE_PASSED if outcome.passed else EventType.GATE_FAILED,
                phase=phase,
                task_id=task.task_id,
                gate=outcome.gate_name,
                message=outcome.message,
            )

        self.state.set_phase_status(phase, VerificationStatus.EVALUATING)
        all_passed = all(outcome.passed for outcome in outcomes)
        verification = VerificationOutcome(
            task_id=task.task_id,
            pre_gate_outcomes=outcomes,
            evaluator_score=1.0 if all_passed else 0.0,
            evaluator_passed=all_passed,
        )
        verdict = verification.compute_verdict()
        task.context["verification"] = {
            "verdict": verdict.value,
            "gates": [
                {
                    "name": outcome.gate_name,
                    "passed": outcome.passed,
                    "message": outcome.message,
                }
                for outcome in outcomes
            ],
        }

        if all_passed:
            task.transition_to(TaskStatus.APPROVED)
            self.state.set_phase_status(phase, VerificationStatus.APPROVED)
        else:
            task.transition_to(TaskStatus.REJECTED)
            self.state.set_phase_status(phase, VerificationStatus.REJECTED)
        self._complete_phase(phase)
        return all_passed

    def _persist(self, task: TaskRecord, success: bool) -> None:
        phase = RuntimePhase.PERSISTENCE
        self._set_phase(phase)
        self.state.set_phase_status(phase, PersistenceStatus.UPDATING_LEDGER)
        self.state.task_ledger.complete_task(task.task_id, success=success)
        reservation = self.state.active_reservation
        if reservation:
            reservation.used_steps += 1
            reservation.status = (
                BudgetReservationStatus.COMMITTED
                if success
                else BudgetReservationStatus.RELEASED
            )
            self._event(
                EventType.BUDGET_COMMITTED
                if success
                else EventType.BUDGET_RELEASED,
                phase=phase,
                task_id=task.task_id,
                reservation_id=reservation.reservation_id,
            )
        self.state.set_phase_status(phase, PersistenceStatus.SAVING_STATE)
        if self.config.persistence.auto_save and not self.config.dry_run:
            path = self.persistence.save(self.state, self.state.trace_id)
            if path is None:
                raise RuntimeError("Runtime state could not be persisted")
            self._event(
                EventType.STATE_SAVED,
                phase=phase,
                task_id=task.task_id,
                path=str(path),
            )
        self.state.set_phase_status(phase, PersistenceStatus.COMPLETE)
        self._event(
            EventType.TASK_COMPLETED if success else EventType.TASK_FAILED,
            phase=phase,
            task_id=task.task_id,
        )
        self._complete_phase(phase)

    def _schedule(self) -> bool:
        phase = RuntimePhase.SCHEDULING
        self._set_phase(phase)
        self.state.set_phase_status(phase, SchedulingStatus.EVALUATING_QUEUE)
        has_more = bool(self.state.task_ledger.get_pending_tasks())
        self.state.set_phase_status(
            phase,
            SchedulingStatus.SCHEDULING_NEXT
            if has_more
            else SchedulingStatus.COMPLETE,
        )
        self._complete_phase(phase)
        return has_more

    async def run(self) -> RuntimeResult:
        start_time = datetime.now()
        self.state.started_at = start_time
        self.state.status = LoopStatus.RUNNING
        self.state.max_iterations = max(1, self.state.max_iterations)

        try:
            self._discover()
            while self.state.task_ledger.get_pending_tasks():
                if self.state.current_iteration >= self.state.max_iterations:
                    self.state.status = LoopStatus.FAILED
                    break
                task = self.state.task_ledger.select_next_task()
                if task is None:
                    break
                self.state.current_task_id = task.task_id
                self.state.increment_iteration()
                self._handoff(task)
                success = self._verify(task)
                self._persist(task, success)
                if not self._schedule():
                    break

            failures = len(self.state.task_ledger.failed_task_ids)
            self.state.status = (
                LoopStatus.COMPLETED
                if failures == 0
                else LoopStatus.FAILED
            )
            if self.config.persistence.auto_save and not self.config.dry_run:
                self.persistence.save(self.state, self.state.trace_id)
        except Exception as exc:
            self.state.status = LoopStatus.FAILED
            self.state.metadata["runtime_error"] = str(exc)
            self._event(EventType.PHASE_FAILED, error=str(exc))

        end_time = datetime.now()
        return RuntimeResult(
            runtime_id=self.state.runtime_id,
            trace_id=self.state.trace_id or "",
            status=self.state.status,
            tasks_discovered=len(self.state.task_ledger.tasks),
            tasks_completed=len(self.state.task_ledger.completed_task_ids),
            tasks_failed=len(self.state.task_ledger.failed_task_ids),
            iterations=self.state.current_iteration,
            start_time=start_time,
            end_time=end_time,
            total_tokens_used=sum(
                task.context.get("tokens_used", 0)
                for task in self.state.task_ledger.tasks.values()
            ),
            total_cost=sum(
                task.context.get("cost", 0.0)
                for task in self.state.task_ledger.tasks.values()
            ),
            events=self.events.copy(),
        )


def create_runtime(
    *,
    skills_dir: Optional[str] = None,
    state_dir: Optional[str] = None,
    checkpoint_preset: Optional[str] = None,
    max_iterations: int = 100,
    persistence_backend: Optional[str] = None,
    runtime_config: Optional[RuntimeConfig] = None,
    task_handlers: Optional[Dict[str, Callable[[TaskRecord], Any]]] = None,
    dry_run: bool = False,
) -> LoopRuntime:
    """Create a configured runtime for the public CLI and Python API."""
    config = runtime_config or RuntimeConfig()
    if skills_dir is not None:
        config.discovery.skills_dir = Path(skills_dir)
    if state_dir is not None:
        config.discovery.state_dir = Path(state_dir)
        config.persistence.state_dir = Path(state_dir)
    if persistence_backend is not None:
        config.persistence.format = persistence_backend
    if checkpoint_preset is not None:
        config.verification.checkpoint_preset = checkpoint_preset
    config.dry_run = dry_run
    runtime = LoopRuntime(config, task_handlers=task_handlers)
    runtime.state.max_iterations = max_iterations
    return runtime


__all__ = ["LoopRuntime", "create_runtime"]
