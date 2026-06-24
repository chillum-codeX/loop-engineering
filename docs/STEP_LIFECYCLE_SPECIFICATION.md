# Step Lifecycle Specification

**Document Date**: 2026-06-24
**Framework Version**: 0.3.0
**Status**: IMPLEMENTATION SPECIFICATION

## 1. Overview

This document specifies the complete lifecycle of a step within the Loop Engineering Framework, replacing ambiguous string statuses with a typed `StepStatus` enum and defining clear semantics for execution, evaluation, verification, and completion.

## 2. StepStatus Enum

```python
class StepStatus(Enum):
    """Explicit step lifecycle states."""

    # Initial states
    PENDING = "pending"           # Step created, not yet ready
    READY = "ready"               # Step ready for execution

    # Execution states
    IN_PROGRESS = "in_progress"   # Currently executing
    EXECUTED = "executed"         # Actor completed, awaiting evaluation

    # Evaluation states
    EVALUATION_FAILED = "evaluation_failed"  # Evaluation rejected
    EVALUATED = "evaluated"       # Evaluation passed, awaiting verification

    # Verification states
    VERIFICATION_FAILED = "verification_failed"  # Verification rejected
    VERIFIED_COMPLETED = "verified_completed"    # Fully complete

    # Recovery states
    RECOVERY_PENDING = "recovery_pending"  # Awaiting recovery action
    RETRY_PENDING = "retry_pending"        # Ready for retry after recovery

    # Terminal states
    BLOCKED = "blocked"           # Cannot proceed (dependencies)
    SKIPPED = "skipped"           # Intentionally skipped
    FAILED = "failed"             # Permanently failed
    CANCELLED = "cancelled"       # Cancelled before completion
```

## 3. Normal Lifecycle

```
PENDING
    ↓ (dependencies satisfied)
READY
    ↓ (actor starts)
IN_PROGRESS
    ↓ (actor completes)
EXECUTED
    ↓ (evaluator passes)
EVALUATED
    ↓ (verifier passes) OR (verification disabled)
VERIFIED_COMPLETED
```

## 4. Permission Matrix

| Component | Can Set Status | Can Transition From | Can Transition To |
|-----------|----------------|---------------------|-------------------|
| **Planner** | PENDING, READY, BLOCKED | - | PENDING, READY, BLOCKED |
| **Actor** | IN_PROGRESS, EXECUTED | READY | IN_PROGRESS, EXECUTED |
| **Evaluator** | EVALUATED, EVALUATION_FAILED | EXECUTED | EVALUATED, EVALUATION_FAILED |
| **Verifier** | VERIFIED_COMPLETED, VERIFICATION_FAILED | EVALUATED | VERIFIED_COMPLETED, VERIFICATION_FAILED |
| **Recovery** | RECOVERY_PENDING, RETRY_PENDING | EVALUATION_FAILED, VERIFICATION_FAILED | RECOVERY_PENDING, RETRY_PENDING |
| **Recovery** | READY | RETRY_PENDING | READY |

## 5. Step Lifecycle States Detailed

### 5.1 PENDING
- **Entry**: Step created by planner
- **Exit**: When dependencies satisfied → READY
- **Permissions**: Planner can set

### 5.2 READY
- **Entry**: PENDING with dependencies satisfied
- **Exit**: When actor starts → IN_PROGRESS
- **Permissions**: Planner can set; Recovery can set after RETRY_PENDING

### 5.3 IN_PROGRESS
- **Entry**: Actor starts execution
- **Exit**: When actor returns → EXECUTED
- **Permissions**: Only Actor can set
- **Side Effects**: step.start_time recorded

### 5.4 EXECUTED
- **Entry**: Actor completed successfully
- **Exit**: Evaluation result → EVALUATED or EVALUATION_FAILED
- **Permissions**: Only Actor can set
- **Side Effects**: step.end_time recorded; step.output stored

### 5.5 EVALUATION_FAILED
- **Entry**: Evaluator rejected step
- **Exit**: Recovery → RECOVERY_PENDING or RETRY_PENDING
- **Permissions**: Only Evaluator can set
- **Blocking**: YES - does not count as complete

### 5.6 EVALUATED
- **Entry**: Evaluator approved step
- **Exit**:
  - If verification enabled → VERIFYING (via verifier)
  - If verification disabled → VERIFIED_COMPLETED
- **Permissions**: Only Evaluator can set
- **Blocking**: NO (unless verification required)

### 5.7 VERIFICATION_FAILED
- **Entry**: Verifier rejected step
- **Exit**: Recovery → RECOVERY_PENDING or RETRY_PENDING
- **Permissions**: Only Verifier can set
- **Blocking**: YES - does not count as complete

### 5.8 VERIFIED_COMPLETED
- **Entry**: Verifier approved step (or evaluation sufficient when verification disabled)
- **Exit**: Terminal
- **Permissions**: Verifier sets; or auto-set when verification disabled
- **Blocking**: NO - counts as complete

### 5.9 RECOVERY_PENDING
- **Entry**: Recovery system processing failure
- **Exit**: Recovery complete → RETRY_PENDING
- **Permissions**: Recovery component sets
- **Blocking**: YES

### 5.10 RETRY_PENDING
- **Entry**: Recovery ready for retry
- **Exit**: Replanning complete → READY
- **Permissions**: Recovery component sets
- **Blocking**: YES

### 5.11 BLOCKED
- **Entry**: Dependencies not satisfied
- **Exit**: Dependencies satisfied → READY
- **Permissions**: Planner sets
- **Blocking**: YES

### 5.12 SKIPPED
- **Entry**: Intentionally skipped (e.g., optional step)
- **Exit**: Terminal
- **Permissions**: Planner or recovery sets
- **Blocking**: Depends on skip policy

### 5.13 FAILED
- **Entry**: Permanently failed (max retries, terminal error)
- **Exit**: Terminal
- **Permissions**: Recovery or system sets
- **Blocking**: YES - prevents completion

### 5.14 CANCELLED
- **Entry**: Cancelled by user or system
- **Exit**: Terminal
- **Permissions**: System sets
- **Blocking**: YES

## 6. Plan Progress Calculation

Plan progress counts ONLY steps in completion states:

```python
def get_progress(self) -> float:
    """Calculate plan completion progress."""
    if not self.steps:
        return 0.0

    COMPLETION_STATES = {
        StepStatus.VERIFIED_COMPLETED,
        StepStatus.SKIPPED,  # If skip policy allows
    }

    completed = sum(1 for s in self.steps if s.status in COMPLETION_STATES)
    return completed / len(self.steps)
```

Steps in these states do NOT count:
- PENDING
- READY
- IN_PROGRESS
- EXECUTED
- EVALUATION_FAILED
- EVALUATED (when verification required)
- VERIFICATION_FAILED
- RECOVERY_PENDING
- RETRY_PENDING
- BLOCKED
- FAILED
- CANCELLED

## 7. Disabled Verification Policy

When `enable_verification=False`:

```python
# After EVALUATED, auto-promote to VERIFIED_COMPLETED
if not self.config.enable_verification:
    step.status = StepStatus.VERIFIED_COMPLETED
    # Record unverified completion in trace
    step.metadata['verification'] = 'disabled'
```

Result must indicate:
```python
result.verification_status = "DISABLED"
# NOT claim independently verified completion
```

## 8. Required Tests

### 8.1 Actor Tests
- Actor sets IN_PROGRESS when starting
- Actor sets EXECUTED when completing
- Actor cannot set EVALUATED
- Actor cannot set VERIFIED_COMPLETED
- Actor cannot complete step (EXECUTED ≠ complete)

### 8.2 Evaluator Tests
- Evaluator can set EVALUATED from EXECUTED
- Evaluator can set EVALUATION_FAILED from EXECUTED
- Evaluator cannot set VERIFIED_COMPLETED
- Evaluation failure blocks progress
- Evaluation pass allows progress (with verification disabled)

### 8.3 Verifier Tests
- Verifier can set VERIFIED_COMPLETED from EVALUATED
- Verifier can set VERIFICATION_FAILED from EVALUATED
- Verification failure blocks completion
- Verification pass enables completion

### 8.4 Progress Tests
- EXECUTED steps don't count as complete
- EVALUATION_FAILED steps don't count as complete
- EVALUATED steps don't count (when verification required)
- VERIFICATION_FAILED steps don't count as complete
- VERIFIED_COMPLETED steps count as complete
- Progress calculation is accurate

### 8.5 Recovery Tests
- Failed steps remain available for recovery
- Recovery can reset to READY
- Completed unaffected steps remain after replanning
- RETRY_PENDING properly bridges to READY

## 9. Implementation Changes

### 9.1 types.py
- Add `StepStatus` enum
- Change `Step.status` from `str` to `StepStatus`
- Add `Step.evaluation_passed: Optional[bool]`
- Add `Step.verification_passed: Optional[bool]`

### 9.2 core.py
- Update `_execute_action()` to set `StepStatus.IN_PROGRESS` then `StepStatus.EXECUTED`
- Update `_execute_evaluation()` to set `StepStatus.EVALUATED` or `StepStatus.EVALUATION_FAILED`
- Update `_execute_verification()` to set `StepStatus.VERIFIED_COMPLETED` or `StepStatus.VERIFICATION_FAILED`
- Update `Plan.get_progress()` to use completion states
- Update `_is_plan_complete()` to check for VERIFIED_COMPLETED

### 9.3 components.py
- Update all component interfaces to use `StepStatus`
- Ensure components respect permission matrix

## 10. Migration from String Statuses

Current string statuses:
- `"pending"` → `StepStatus.PENDING`
- `"in_progress"` → `StepStatus.IN_PROGRESS`
- `"completed"` → `StepStatus.VERIFIED_COMPLETED` (when verified)
- `"failed"` → `StepStatus.EVALUATION_FAILED` or `StepStatus.FAILED`

Migration:
1. Replace all string comparisons with enum comparisons
2. Update serialization to use enum values
3. Add validation that only valid transitions occur
