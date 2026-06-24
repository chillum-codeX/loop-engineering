# State Machine Specification

**Document Date**: 2026-06-24
**Framework Version**: 0.3.0
**Status**: IMPLEMENTATION SPECIFICATION

## 1. Overview

This document specifies the complete execution state machine for the Loop Engineering Framework, including explicit iteration lifecycle semantics, transition rules, and disabled-phase bypass paths.

## 2. State Definitions

### 2.1 Active States (Non-Terminal)

| State | Description | Entry Criteria | Exit Criteria |
|-------|-------------|----------------|---------------|
| `INITIALIZED` | Engine created, ready to start | Engine instantiation | First iteration begins |
| `SPECIFYING` | Task specification phase | Before planning | Task understood, ready to plan |
| `PLANNING` | Creating or revising plan | SPECIFYING or ITERATION_COMPLETE | Plan created/revised |
| `ACTING` | Executing current step | PLANNING | Step execution complete |
| `OBSERVING` | Capturing execution results | ACTING | Observation recorded |
| `EVALUATING` | Assessing step quality | OBSERVING | Evaluation complete |
| `VERIFYING` | Independent verification | EVALUATING | Verification complete |
| `ITERATION_COMPLETE` | End of iteration boundary | EVALUATING or VERIFYING | Next state determined |
| `RECOVERING` | Handling failure | EVALUATING or VERIFYING | Recovery action complete |
| `REPLANNING` | Correcting plan after failure | RECOVERING | New plan ready |
| `WAITING_FOR_HUMAN` | Awaiting human input | RECOVERING or policy trigger | Human response received |

### 2.2 Terminal States

| State | Description | When Reached |
|-------|-------------|--------------|
| `COMPLETED` | Successful termination | All steps verified, goal achieved |
| `PARTIALLY_COMPLETED` | Partial success | Required steps done, optional skipped |
| `ABSTAINED` | Intentional non-completion | Policy decision to not complete |
| `BUDGET_EXHAUSTED` | Budget limit reached | Steps/time/tokens exceeded |
| `POLICY_TERMINATED` | Policy violation | Safety or policy termination |
| `FAILED` | Failure termination | Unrecoverable error or max attempts |

## 3. Normal Lifecycle

```
INITIALIZED
    ↓
SPECIFYING
    ↓
PLANNING
    ↓
ACTING
    ↓
OBSERVING
    ↓
EVALUATING
    ↓
VERIFYING
    ↓
ITERATION_COMPLETE
```

At `ITERATION_COMPLETE`, the runtime explicitly decides:

```
ITERATION_COMPLETE
    ├──→ COMPLETED (all steps done)
    ├──→ PLANNING (next iteration)
    ├──→ REPLANNING (plan correction needed)
    ├──→ RECOVERING (failure handling)
    ├──→ WAITING_FOR_HUMAN (escalation)
    ├──→ ABSTAINED (intentional stop)
    ├──→ FAILED (unrecoverable)
    └──→ BUDGET_EXHAUSTED (resource limit)
```

## 4. Transition Specification Table

### 4.1 Normal Path Transitions

| Source | Destination | Preconditions | Trigger | Side Effects | Invalid Behavior |
|--------|-------------|---------------|---------|--------------|------------------|
| INITIALIZED | SPECIFYING | Engine ready | run() called | state.initialized | Raise if already started |
| INITIALIZED | FAILED | Engine error | Setup failure | Log error | - |
| SPECIFYING | PLANNING | Task understood | Spec complete | - | Raise if no goal |
| SPECIFYING | FAILED | Spec error | Unparseable task | Log error | - |
| PLANNING | ACTING | Plan exists | Plan ready | Increment plan version | Raise if no steps |
| PLANNING | FAILED | Plan error | Unplannable | Create failure | - |
| ACTING | OBSERVING | Step executed | Actor returned | Step.status = EXECUTED | Raise on exception |
| ACTING | RECOVERING | Step failed | Actor exception | Create failure | - |
| ACTING | FAILED | Critical error | Unrecoverable | Create failure | - |
| OBSERVING | EVALUATING | Observation recorded | Observer done | - | Raise if no observation |
| EVALUATING | VERIFYING | Evaluation passed | passed=True | Step.status = EVALUATED | - |
| EVALUATING | RECOVERING | Evaluation failed | passed=False | Step.status = EVALUATION_FAILED | - |
| EVALUATING | REPLANNING | Evaluation requires change | Needs replan | - | - |
| VERIFYING | ITERATION_COMPLETE | Verification passed | verified=True | Step.status = VERIFIED_COMPLETED | - |
| VERIFYING | RECOVERING | Verification failed | verified=False | - | - |
| ITERATION_COMPLETE | PLANNING | More steps pending | has_next_step=True | Increment iteration | - |
| ITERATION_COMPLETE | COMPLETED | All steps verified | plan.complete=True | Finalize result | - |
| ITERATION_COMPLETE | REPLANNING | Plan needs update | plan.stale=True | - | - |
| ITERATION_COMPLETE | RECOVERING | Failure pending | has_unhandled_failure=True | - | - |
| ITERATION_COMPLETE | BUDGET_EXHAUSTED | Budget check | budget.exhausted=True | Set terminal | - |
| ITERATION_COMPLETE | FAILED | Unrecoverable | terminal_failure=True | Set terminal | - |

### 4.2 Recovery Path Transitions

| Source | Destination | Preconditions | Trigger | Side Effects |
|--------|-------------|---------------|---------|--------------|
| RECOVERING | REPLANNING | Recovery = replan | Strategy selected | Preserve evidence |
| RECOVERING | ITERATION_COMPLETE | Recovery = retry succeeded | Step ready | Step.status = RETRY_PENDING → READY |
| RECOVERING | WAITING_FOR_HUMAN | Recovery = escalate | Human needed | - |
| RECOVERING | FAILED | Recovery failed | Max attempts reached | Mark terminal |
| REPLANNING | PLANNING | New plan ready | Plan revised | Keep completed steps |
| REPLANNING | FAILED | Replan failed | Cannot replan | Create failure |
| WAITING_FOR_HUMAN | RECOVERING | Human responded | Continue recovery | - |
| WAITING_FOR_HUMAN | REPLANNING | Human instructed replan | Follow instruction | - |
| WAITING_FOR_HUMAN | FAILED | Human aborted | Abort requested | Set terminal |

### 4.3 Disabled Phase Bypass Transitions

When `enable_observer=False`:

| Source | Destination | Preconditions | Trigger |
|--------|-------------|---------------|---------|
| ACTING | EVALUATING | Observer disabled | Skip observation |

When `enable_evaluator=False`:

| Source | Destination | Preconditions | Trigger |
|--------|-------------|---------------|---------|
| OBSERVING | ITERATION_COMPLETE | Evaluator disabled | Direct to boundary |
| ACTING | ITERATION_COMPLETE | Both disabled | Direct to boundary |

When `enable_verification=False`:

| Source | Destination | Preconditions | Trigger |
|--------|-------------|---------------|---------|
| EVALUATING | ITERATION_COMPLETE | Verifier disabled | Evaluation sufficient |

When `enable_planner=False` (fixed plan):

| Source | Destination | Preconditions | Trigger |
|--------|-------------|---------------|---------|
| SPECIFYING | ACTING | Planner disabled | Execute fixed plan |

## 5. Terminal State Immutability

Terminal states have no valid outgoing transitions:

```python
_VALID_TRANSITIONS = {
    ExecutionState.COMPLETED: set(),
    ExecutionState.PARTIALLY_COMPLETED: set(),
    ExecutionState.ABSTAINED: set(),
    ExecutionState.BUDGET_EXHAUSTED: set(),
    ExecutionState.POLICY_TERMINATED: set(),
    ExecutionState.FAILED: set(),
}
```

Any attempt to transition from a terminal state raises:
```
RuntimeError: Invalid state transition: {terminal} -> {target}.
Terminal states cannot transition.
```

## 6. Transition Validation

All transitions must pass validation:

```python
def _transition_to(self, new_state: ExecutionState) -> None:
    if self.state is None:
        raise RuntimeError("Cannot transition: state is None")

    current_state = self.state.execution_state

    # Terminal check
    if current_state in TERMINAL_STATES:
        raise RuntimeError(
            f"Cannot transition from terminal state {current_state.value}"
        )

    # Valid transition check
    valid_next_states = self._VALID_TRANSITIONS.get(current_state, set())
    if new_state not in valid_next_states:
        raise RuntimeError(
            f"Invalid state transition: {current_state.value} -> {new_state.value}. "
            f"Valid transitions: {[s.value for s in valid_next_states]}"
        )

    # Log transition
    if self.config.verbose:
        logger.info(f"State transition: {current_state.value} -> {new_state.value}")

    self.state.execution_state = new_state
```

## 7. Iteration Boundary Logic

The `ITERATION_COMPLETE` state serves as an explicit boundary between iterations.

### 7.1 Boundary Decision Logic

```python
async def _handle_iteration_complete(self, context: LoopContext) -> ExecutionState:
    """
    Decide next state at iteration boundary.
    Returns the state to transition to.
    """
    # 1. Check budget
    if self.budget and not self.budget.check_budget():
        return ExecutionState.BUDGET_EXHAUSTED

    # 2. Check for terminal failures
    if any(f.status == FailureStatus.TERMINAL for f in self.state.failures):
        return ExecutionState.FAILED

    # 3. Check for unhandled failures requiring recovery
    unhandled_failures = [
        f for f in self.state.failures
        if f.status == FailureStatus.UNHANDLED
    ]
    if unhandled_failures:
        return ExecutionState.RECOVERING

    # 4. Check if plan is complete
    if self.state.current_plan and self.state.current_plan.is_complete():
        # Verify all required steps passed
        if self._all_steps_verified():
            return ExecutionState.COMPLETED
        else:
            return ExecutionState.FAILED

    # 5. Continue to next iteration
    return ExecutionState.PLANNING
```

### 7.2 Main Loop Structure

```python
async def run(self, context: LoopContext) -> LoopResult:
    self.state = LoopState(execution_state=ExecutionState.INITIALIZED)

    try:
        while True:
            # Execute one iteration
            await self._execute_iteration(context)

            # At ITERATION_COMPLETE, decide next state
            next_state = await self._handle_iteration_complete(context)

            if next_state in TERMINAL_STATES:
                self._transition_to(next_state)
                break
            elif next_state == ExecutionState.PLANNING:
                self._transition_to(ExecutionState.PLANNING)
                # Continue loop
            elif next_state == ExecutionState.RECOVERING:
                await self._execute_recovery(context)
                # Recovery will transition to appropriate state
            # ... etc

    except Exception as e:
        self._handle_exception(e)

    return self._build_result()
```

## 8. Test Requirements

### 8.1 Valid Transition Tests

For every transition in `_VALID_TRANSITIONS`:
- Test that transition succeeds when preconditions met
- Test that resulting state is correct
- Test that side effects occur

### 8.2 Invalid Transition Tests

For representative invalid transitions:
- `COMPLETED -> PLANNING`
- `FAILED -> ACTING`
- `EVALUATING -> PLANNING` (direct - should go through ITERATION_COMPLETE)
- `INITIALIZED -> COMPLETED`

### 8.3 Disabled Phase Tests

For each `enable_*=False`:
- Observer disabled: Verify `ACTING -> EVALUATING` path
- Evaluator disabled: Verify `OBSERVING -> ITERATION_COMPLETE` path
- Verifier disabled: Verify `EVALUATING -> ITERATION_COMPLETE` path

### 8.4 Iteration Boundary Tests

- Two consecutive iterations complete successfully
- Three consecutive iterations complete successfully
- Iteration boundary correctly counts iterations
- Iteration boundary respects budget
- Iteration boundary detects completion

## 9. Implementation Notes

### 9.1 Required Code Changes

1. **types.py**:
   - Add `ITERATION_COMPLETE` to `ExecutionState`
   - Verify all states from section 2 are present

2. **core.py**:
   - Update `_VALID_TRANSITIONS` with complete table
   - Add `_handle_iteration_complete()` method
   - Modify `run()` to use iteration boundary logic
   - Add bypass logic for disabled phases
   - Update `_transition_to()` for terminal state check

3. **tests/**:
   - Add `test_state_transitions.py` with all valid transitions
   - Add `test_invalid_transitions.py` with invalid cases
   - Add `test_iteration_boundary.py` with boundary tests
   - Add `test_disabled_phases.py` with bypass tests

### 9.2 Migration from Current Implementation

Current problematic transitions:
- `EVALUATING -> PLANNING` (invalid, causes crash)

New correct path:
- `EVALUATING -> ITERATION_COMPLETE -> PLANNING`

Migration:
1. Replace direct iteration loop with boundary-based loop
2. Insert `ITERATION_COMPLETE` transition at end of `_execute_iteration()`
3. Add boundary decision logic
4. Update transition table

## 10. Acceptance Criteria

The state machine implementation is complete when:

- [ ] All states from section 2 are defined
- [ ] All transitions from section 4 are implemented
- [ ] Terminal states are immutable
- [ ] Invalid transitions raise `RuntimeError`
- [ ] Two consecutive iterations work
- [ ] Three consecutive iterations work
- [ ] Disabled phases have valid bypass paths
- [ ] Iteration count is accurate
- [ ] Boundary decision logic respects budget
- [ ] All tests pass
