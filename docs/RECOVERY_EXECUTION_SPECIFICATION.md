# Recovery Execution Specification

**Document Date**: 2026-06-24
**Framework Version**: 0.3.0
**Status**: IMPLEMENTATION SPECIFICATION

## 1. Overview

This document specifies the recovery execution system for the Loop Engineering Framework. Recovery must not stop at generating a `RecoveryAction` object—it must perform actual state-changing operations.

## 2. Recovery Architecture

Recovery separates four concerns:
1. **Decision**: Select appropriate recovery strategy
2. **Execution**: Perform the recovery operation
3. **Validation**: Verify postconditions
4. **State Update**: Update runtime state based on outcome

## 3. Recovery Strategies

### 3.1 RETRY

**Purpose**: Re-execute the failed step with same parameters.

**Preconditions**:
- Step is in EVALUATION_FAILED or VERIFICATION_FAILED state
- Retry count < max_retry_attempts

**Execution**:
1. Mark step as RETRY_PENDING
2. Increment retry counter
3. Reset step execution fields (clear output, timestamps)
4. Transition step to READY
5. Schedule for re-execution

**Postconditions**:
- Step.status == READY
- Step.retry_count incremented
- Step.output is None
- Step.start_time is None

**Success Criteria**:
- Step successfully transitioned to READY
- Step is picked up by next planning phase

**Failure Criteria**:
- Max retries exceeded
- Step cannot be reset

### 3.2 RETRY_WITH_BACKOFF

**Purpose**: Retry with delay policy to avoid rapid failure loops.

**Preconditions**:
- Same as RETRY
- Injectable clock available for testing

**Execution**:
1. Calculate delay: `delay = backoff_base * (2 ** retry_count)`
2. Record delay policy in step metadata
3. Wait via injectable clock (NOT asyncio.sleep in production)
4. Execute RETRY logic

**Postconditions**:
- Delay recorded in step.metadata['backoff_delay']
- Retry only after delay condition satisfied

**Testing**:
- Use mock clock that advances time explicitly
- Do NOT use real time delays in tests

### 3.3 REPLAN_STEP

**Purpose**: Replace failed step with corrected version.

**Preconditions**:
- Planner component available
- Step has failed (EVALUATION_FAILED or VERIFICATION_FAILED)

**Execution**:
1. Preserve failure evidence in step.metadata['failure_evidence']
2. Call planner.revise_step() with failure context
3. Create new step version with:
   - New step.id
   - Same dependencies
   - Corrected description/action
   - Version incremented
4. Replace failed step in plan.steps (preserve order)
5. Mark unaffected completed steps as unchanged

**Postconditions**:
- Failed step replaced with corrected version
- New step.status == PENDING
- Plan.version incremented
- Completed steps remain completed

**Success Criteria**:
- New step created with corrected parameters
- Plan updated

### 3.4 REPLAN_REMAINING_TASK

**Purpose**: Replan remaining uncompleted steps.

**Preconditions**:
- Planner component available
- Some steps completed, some failed/pending

**Execution**:
1. Preserve completed steps
2. Identify remaining task scope
3. Call planner.revise_plan() with:
   - Current plan
   - Observations
   - Evaluations
   - Failure context
4. Merge new plan with completed steps

**Postconditions**:
- Completed steps unchanged
- Remaining steps revised
- Plan.version incremented

### 3.5 ROLLBACK

**Purpose**: Restore previous artifact snapshot.

**Preconditions**:
- Snapshot system available
- Previous valid state exists

**Execution**:
1. Identify rollback target (last VERIFIED_COMPLETED step)
2. Restore artifact snapshot
3. Verify rollback success (checksum/state hash)
4. Mark rollback in trace
5. Reset subsequent steps to PENDING

**Postconditions**:
- Artifacts restored to previous state
- Subsequent steps reset
- Rollback recorded in trace

### 3.6 CHANGE_TOOL

**Purpose**: Use alternative tool for same task.

**Preconditions**:
- Alternative tools available
- Tool registry accessible

**Execution**:
1. Select alternative tool from registry
2. Update step.tool field
3. Reset step to READY
4. Mark tool change in metadata

### 3.7 CHANGE_MODEL

**Purpose**: Use different model for same task.

**Preconditions**:
- Multiple models available
- Model switcher accessible

**Execution**:
1. Select alternative model
2. Update step.model field
3. Reset step to READY
4. Mark model change in metadata

### 3.8 REDUCE_SCOPE

**Purpose**: Reduce task scope to achievable subset.

**Preconditions**:
- Scope reduction policy defined
- Partial completion acceptable

**Execution**:
1. Identify minimum viable scope
2. Mark optional steps as SKIPPED
3. Replan remaining required steps
4. Update goal description

**Postconditions**:
- Some steps marked SKIPPED
- Reduced scope documented

### 3.9 REQUEST_HUMAN

**Purpose**: Escalate to human operator.

**Preconditions**:
- Human escalation configured
- Escalation channel available

**Execution**:
1. Transition to WAITING_FOR_HUMAN state
2. Include decision context:
   - Failed step details
   - Recovery attempts made
   - Options for human
3. Wait for human response
4. Resume based on human instruction

**Postconditions**:
- State == WAITING_FOR_HUMAN
- Human context prepared

### 3.10 ABSTAIN

**Purpose**: Intentionally stop without completing.

**Preconditions**:
- Safe abstention policy allows
- No critical requirements violated

**Execution**:
1. Transition to ABSTAINED state
2. Document abstention reason
3. Preserve partial results
4. Terminate gracefully

### 3.11 TERMINATE

**Purpose**: Stop with failure status.

**Preconditions**:
- Non-recoverable failure
- Max attempts exceeded

**Execution**:
1. Mark failure as TERMINAL
2. Transition to FAILED state
3. Preserve failure evidence
4. Terminate with error result

## 4. Recovery Handler Interface

```python
class RecoveryHandler(ABC):
    """Base class for recovery strategy handlers."""

    @abstractmethod
    async def execute(
        self,
        failure: Failure,
        step: Step,
        state: LoopState,
        context: LoopContext
    ) -> RecoveryResult:
        """
        Execute recovery strategy.

        Returns:
            RecoveryResult with success/failure and state changes
        """
        pass

    @abstractmethod
    def validate_postconditions(
        self,
        step: Step,
        state: LoopState
    ) -> bool:
        """Verify recovery produced valid state."""
        pass


@dataclass
class RecoveryResult:
    """Result of recovery execution."""
    success: bool
    new_state: Optional[ExecutionState] = None
    step_status: Optional[StepStatus] = None
    message: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
```

## 5. Recovery Registry

```python
class RecoveryRegistry:
    """Registry of recovery strategy handlers."""

    def __init__(self):
        self._handlers: Dict[RecoveryStrategy, RecoveryHandler] = {}

    def register(self, strategy: RecoveryStrategy, handler: RecoveryHandler):
        self._handlers[strategy] = handler

    async def execute(
        self,
        strategy: RecoveryStrategy,
        failure: Failure,
        step: Step,
        state: LoopState,
        context: LoopContext
    ) -> RecoveryResult:
        handler = self._handlers.get(strategy)
        if not handler:
            return RecoveryResult(
                success=False,
                message=f"No handler for strategy {strategy}"
            )

        # Execute recovery
        result = await handler.execute(failure, step, state, context)

        # Validate postconditions
        if result.success:
            valid = handler.validate_postconditions(step, state)
            if not valid:
                result.success = False
                result.message = "Recovery postconditions not met"

        return result
```

## 6. Integration with Loop Engine

### 6.1 Recovery Execution Flow

```python
async def _execute_recovery(self, context: LoopContext, evaluation: Optional[Evaluation] = None):
    """Execute recovery with real handlers."""
    recovery = self.components.get(ComponentType.RECOVERY)
    if not recovery:
        return

    # Get unhandled failures
    recent_failures = [
        f for f in self.state.failures
        if f.status == FailureStatus.UNHANDLED and f.can_recover()
    ]

    if not recent_failures:
        return

    failure = recent_failures[-1]
    failure.status = FailureStatus.RECOVERY_PLANNED

    # Get recovery action (decision)
    recovery_action = await recovery.recover(
        failure,
        self.state,
        context
    )

    # Execute recovery strategy (real execution)
    result = await self._recovery_registry.execute(
        strategy=recovery_action.strategy,
        failure=failure,
        step=self.state.current_step,
        state=self.state,
        context=context
    )

    # Update based on result
    recovery_action.executed = True
    recovery_action.success = result.success
    failure.record_recovery_attempt(recovery_action.action_id)

    if result.success:
        failure.mark_recovered()
        # Transition to appropriate state
        if result.new_state:
            self._transition_to(result.new_state)
    else:
        if not failure.can_recover():
            failure.mark_terminal()
            self.state.execution_state = ExecutionState.FAILED
```

### 6.2 State Transitions After Recovery

| Recovery Result | Next State | Conditions |
|-----------------|------------|------------|
| RETRY success | ITERATION_COMPLETE | Step reset to READY |
| REPLAN success | REPLANNING | Plan revised |
| ROLLBACK success | REPLANNING | State restored |
| HUMAN requested | WAITING_FOR_HUMAN | Escalation needed |
| Failure | FAILED | Max attempts or unrecoverable |

## 7. Required Tests

### 7.1 Retry Tests
- First retry succeeds
- Retry increments counter
- Step fields reset properly
- Step returns to READY

### 7.2 Replan Tests
- Failed step replaced
- Completed steps preserved
- Plan version incremented
- New step has correct dependencies

### 7.3 Rollback Tests
- Snapshot restored
- Verification passes
- Subsequent steps reset
- Rollback recorded in trace

### 7.4 Limit Tests
- Max attempts enforced
- New failure creates new ID
- Recovered failures not reprocessed
- Terminal failures stop recovery

### 7.5 State Transition Tests
- Recovery success → valid state
- Recovery failure → FAILED
- Postcondition validation works

## 8. Implementation Plan

### 8.1 Files to Create
- `loop_engine/recovery/handlers.py` - Recovery handlers
- `loop_engine/recovery/registry.py` - Recovery registry
- `loop_engine/recovery/__init__.py` - Package init

### 8.2 Files to Modify
- `loop_engine/core.py` - Integrate recovery registry
- `loop_engine/components.py` - Update recovery interface
- `tests/unit/test_recovery.py` - Recovery tests

### 8.3 Default Handlers
Implement handlers for:
- RETRY (essential)
- REPLAN_STEP (essential)
- REQUEST_HUMAN (essential)
- TERMINATE (essential)

Optional handlers (future):
- RETRY_WITH_BACKOFF
- ROLLBACK
- CHANGE_TOOL
- CHANGE_MODEL
- REDUCE_SCOPE
