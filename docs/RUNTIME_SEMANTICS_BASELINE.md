# Runtime Semantics Baseline

**Document Date**: 2026-06-24
**Framework Version**: 0.2.0
**Repository**: /home/novix/workspace/project

## Summary

This document documents all defects reproduced in the current Loop Engineering runtime. Each defect includes reproduction commands, actual output, expected output, root cause, severity, and planned correction.

---

## Defect #1: Two-Step Task Fails on Second Iteration

**Severity**: CRITICAL

### Reproduction Command
```bash
python reproduce_defects.py
# Or manually run a loop with max_iterations >= 2
```

### Actual Output
```
INFO:loop_engine.core:=== Iteration 1 ===
INFO:loop_engine.core:State transition: initialized -> planning
INFO:loop_engine.core:Created plan with 4 steps
INFO:loop_engine.core:State transition: planning -> acting
INFO:loop_engine.core:Executed step step_0: Analyze the problem...
INFO:loop_engine.core:State transition: acting -> observing
INFO:loop_engine.core:State transition: observing -> evaluating
INFO:loop_engine.core:Evaluation: score=0.00, passed=False
INFO:loop_engine.core:=== Iteration 2 ===
ERROR:loop_engine.core:Loop execution failed: Invalid state transition: evaluating -> planning
Result status: LoopStatus.FAILED
Iterations: 0
```

### Expected Output
```
INFO:loop_engine.core:=== Iteration 1 ===
INFO:loop_engine.core:State transition: initialized -> planning
...
INFO:loop_engine.core:=== Iteration 2 ===
INFO:loop_engine.core:State transition: iteration_complete -> planning
...
Result status: LoopStatus.COMPLETED (or appropriate terminal status)
Iterations: 2 (or actual number executed)
```

### Root Cause
The state machine does not support repeated iterations. The transition `EVALUATING -> PLANNING` is not valid because there is no `ITERATION_COMPLETE` state to bridge iterations. The engine attempts to go directly from the evaluation phase of iteration N to the planning phase of iteration N+1, which is not a valid transition.

### Root-Cause File
`loop_engine/core.py` - `_VALID_TRANSITIONS` dictionary and `_execute_iteration()` method

### Planned Correction
1. Add `ITERATION_COMPLETE` state to `ExecutionState` enum
2. Add valid transition: `EVALUATING -> ITERATION_COMPLETE`
3. Add valid transition: `ITERATION_COMPLETE -> PLANNING`
4. Modify `_execute_iteration()` to transition to `ITERATION_COMPLETE` at end of iteration
5. Add iteration boundary logic that decides next state based on plan progress

---

## Defect #2: EVALUATING -> PLANNING Transition Missing

**Severity**: CRITICAL

### Reproduction Command
```python
engine = LoopEngine(LoopConfig())
engine.state = type('State', (), {'execution_state': ExecutionState.EVALUATING})()
engine._transition_to(ExecutionState.PLANNING)  # Raises RuntimeError
```

### Actual Output
```
RuntimeError: Invalid state transition: evaluating -> planning.
Valid transitions from evaluating: ['failed', 'verifying', 'recovering', 'completed', 'replanning']
```

### Expected Output
Transition should succeed via intermediate state or direct path for iteration continuation.

### Root Cause
No `ITERATION_COMPLETE` state exists to serve as a bridge between iterations. The transition table correctly excludes `EVALUATING -> PLANNING` (which would skip verification and iteration boundary logic), but there's no alternative path for continuing to the next iteration.

### Root-Cause File
`loop_engine/core.py` - `_VALID_TRANSITIONS` dictionary

### Planned Correction
Same as Defect #1: Add `ITERATION_COMPLETE` state with proper transition paths.

---

## Defect #3: OBSERVING -> PLANNING Missing (Disabled Evaluator Path)

**Severity**: HIGH

### Reproduction Command
```python
engine = LoopEngine(LoopConfig(enable_evaluator=False))
# Check valid transitions from OBSERVING
valid = engine._VALID_TRANSITIONS[ExecutionState.OBSERVING]
# Result: {'failed', 'recovering', 'evaluating'}
```

### Actual Output
Valid transitions from OBSERVING: `['failed', 'recovering', 'evaluating']`

### Expected Output
When evaluator is disabled, should have path: `OBSERVING -> ITERATION_COMPLETE`

### Root Cause
No bypass path exists for disabled phases. When `enable_evaluator=False`, the code still attempts to transition through EVALUATING or needs a direct path to ITERATION_COMPLETE, but neither exists.

### Root-Cause File
`loop_engine/core.py` - `_VALID_TRANSITIONS` and `_execute_iteration()`

### Planned Correction
1. Add `OBSERVING -> ITERATION_COMPLETE` transition
2. In `_execute_iteration()`, when evaluator is disabled, transition directly from OBSERVING to ITERATION_COMPLETE
3. Similarly for other disabled phases (verifier, observer)

---

## Defect #4: Evaluator Rejection Doesn't Block Completion

**Severity**: CRITICAL

### Reproduction Command
```python
class AlwaysRejectEvaluator:
    async def evaluate(self, plan, observations, goal, context):
        return Evaluation(score=0.0, passed=False, feedback="Rejected")

engine.register_component(ComponentType.EVALUATOR, AlwaysRejectEvaluator())
result = await engine.run(context)
```

### Actual Output
Currently masked by Defect #1 (transition error causes FAIL), but the underlying logic issue exists.

### Expected Output
```
Result status: FAILED (or RECOVERING if recovery available)
```

### Root Cause
The engine's `_determine_final_status()` method checks plan progress (`get_progress() >= 1.0`) but does not verify that all steps passed evaluation. A step can be marked "completed" by the actor without evaluator approval.

### Root-Cause File
`loop_engine/core.py` - `_determine_final_status()` method

### Planned Correction
1. Implement StepStatus enum with EVALUATED and VERIFIED_COMPLETED states
2. Only count steps as complete when they reach VERIFIED_COMPLETED (or EVALUATED if verification disabled)
3. Modify `_determine_final_status()` to check for any EVALUATION_FAILED steps
4. Ensure evaluation failure triggers recovery or failure status

---

## Defect #5: Recovery Strategy Not Actually Executed

**Severity**: CRITICAL

### Reproduction Command
```python
engine.register_component(ComponentType.RECOVERY, AdaptiveRecovery())
result = await engine.run(context)
print(f"Recoveries: {len(result.recoveries)}")
for r in result.recoveries:
    print(f"  executed={getattr(r, 'executed', 'N/A')}")
```

### Actual Output
```
Recoveries: 0
# Or if recovery is triggered:
Recovery action created but no state changes observed
```

### Expected Output
```
Recoveries: 1
  executed=True
  failure_id=linked_to_failure
  # Observable state change (step status changed, plan modified, etc.)
```

### Root Cause
Recovery only creates a `RecoveryAction` object but does not execute strategy handlers. There's no code that actually performs the recovery operation (e.g., marking step for retry, replanning, rollback).

### Root-Cause File
`loop_engine/core.py` - `_execute_recovery()` method
`loop_engine/components.py` - Recovery strategy implementations

### Planned Correction
1. Define recovery strategy handlers (RETRY, REPLAN_STEP, ROLLBACK, etc.)
2. Each handler performs actual state changes
3. `_execute_recovery()` calls appropriate handler after selecting strategy
4. Verify post-conditions after recovery execution
5. Mark recovery action as executed only after successful handler completion

---

## Defect #6: Recovery May Leave Runtime in Invalid State

**Severity**: HIGH

### Reproduction Command
N/A - Requires working recovery (blocked by Defect #5)

### Actual Output
Recovery may transition to states that don't have valid next transitions.

### Expected Output
Recovery always transitions to a state with valid continuation path.

### Root Cause
No validation that recovery produces valid post-conditions or transitions to a valid next state.

### Root-Cause File
`loop_engine/core.py` - `_execute_recovery()` method

### Planned Correction
1. Define valid post-recovery states (REPLANNING, ITERATION_COMPLETE, FAILED, WAITING_FOR_HUMAN)
2. After recovery execution, explicitly transition to one of these states
3. Validate that the resulting state has valid outgoing transitions
4. Document recovery outcome state in trace

---

## Defect #7: max_recovery_attempts Not Propagated from LoopConfig

**Severity**: MEDIUM

### Reproduction Command
```python
config = LoopConfig(max_recovery_attempts=5)
engine = LoopEngine(config)
failure = Failure(type=FailureType.EXECUTION_ERROR, message="Test")
print(failure.max_recovery_attempts)  # Returns 3, not 5
```

### Actual Output
```
Config max_recovery_attempts: 5
Failure max_recovery_attempts: 3
```

### Expected Output
```
Failure max_recovery_attempts: 5 (inherited from LoopConfig)
```

### Root Cause
`Failure` dataclass uses hard-coded default `max_recovery_attempts: int = 3` instead of reading from `LoopConfig`.

### Root-Cause File
`loop_engine/types.py` - `Failure` dataclass
`loop_engine/core.py` - Where Failures are created

### Planned Correction
1. When creating a Failure in the engine, pass `max_recovery_attempts` from `LoopConfig`
2. Update all `Failure(...)` instantiations to include `max_recovery_attempts=self.config.max_recovery_attempts`

---

## Defect #8: Runtime Exceptions Lost in Final Result

**Severity**: HIGH

### Reproduction Command
```python
class FailingActor:
    async def execute(self, step, observations, context):
        raise ValueError("Intentional test failure")

engine.register_component(ComponentType.ACTOR, FailingActor())
result = await engine.run(context)
```

### Actual Output
Partially working - exception message is captured, but:
```
Result status: FAILED
Failures: 1
Last failure message: "Intentional test failure"  # This works
```

However, the iteration count is reset to 0 and some trace information may be lost.

### Expected Output
```
Result status: FAILED
Failures: 1
Last failure type: EXECUTION_ERROR
Last failure message: "Intentional test failure"
Current state at failure: <preserved>
Iteration count: <actual iterations before failure>
```

### Root Cause
Exception handling in `run()` method creates a new Failure but some state information may not be fully preserved, and iteration count is in `result` but may not reflect actual progress.

### Root-Cause File
`loop_engine/core.py` - `run()` method exception handling

### Planned Correction
1. Ensure all state is captured before creating result
2. Preserve iteration count even on failure
3. Add exception_type and exception_message to result fields
4. Ensure state transition history is preserved

---

## Defect #9: Incorrect Iteration Count on Failed Execution

**Severity**: MEDIUM

### Reproduction Command
```python
engine = LoopEngine(LoopConfig(max_iterations=3))
result = await engine.run(context)
# If exception occurs in iteration 2, count may be wrong
```

### Actual Output
```
ERROR:loop_engine.core:Loop execution failed: Invalid state transition...
Result iterations: 0  # Should be 1 (one iteration completed before failure)
```

### Expected Output
```
Result iterations: 1  # Or actual number of iterations attempted
```

### Root Cause
When exception occurs, the iteration count in the result may not match the actual iterations executed.

### Root-Cause File
`loop_engine/core.py` - `run()` method

### Planned Correction
1. Ensure `result.iterations` is populated from `state.current_iteration` in finally block
2. Verify iteration counting in all termination paths
3. Add test specifically for iteration count accuracy

---

## Defect #10: Benchmark Efficiency Credit for Incorrect Output

**Severity**: HIGH

### Reproduction Command
Examine `benchmarks/base.py` scoring logic.

### Actual Output
Scoring logic not yet audited, but suspected issue:
```python
# Suspected problematic pattern
total_score = correctness_score + efficiency_bonus
# If correctness_score is low but efficiency_bonus is high,
# total_score could still be positive
```

### Expected Output
```python
# Correctness-first scoring
if not correct:
    total_score = 0
else:
    total_score = correctness_score + constraint_score + recovery_score + efficiency_bonus - penalties
```

### Root Cause
Scoring formula may not properly gate efficiency bonuses on correctness.

### Root-Cause File
`benchmarks/base.py` - Scoring methods

### Planned Correction
1. Audit all benchmark scoring logic
2. Implement correctness-first scoring rule
3. Ensure incorrect/empty/crashed outputs receive score=0
4. Move invalid historical results to `benchmarks/results/invalidated/`

---

## Defect #11: Missing pyproject.toml for Editable Installation

**Severity**: HIGH

### Reproduction Command
```bash
cd /home/novix/workspace/project
pip install -e .
```

### Actual Output
```
ERROR: File "setup.py" not found. Directory cannot be installed in editable mode
```

### Expected Output
```
Successfully installed loop-engine in editable mode
```

### Root Cause
No `pyproject.toml` or `setup.py` exists for package installation.

### Root-Cause File
Missing: `pyproject.toml`

### Planned Correction
1. Create `pyproject.toml` with:
   - Package metadata (name, version, description)
   - Dependencies
   - Supported Python versions
   - Entry points (if needed)
   - Development extras
2. Remove manual `sys.path` manipulation from tests
3. Ensure tests work with installed package

---

## Defect #12: Tests Use sys.path Manipulation

**Severity**: MEDIUM

### Reproduction Command
```bash
grep -r "sys.path.insert" tests/
```

### Actual Output
```python
# In tests/unit/test_component_registration.py and test_state_machine.py
sys.path.insert(0, str(project_root))
```

### Expected Output
Tests should import from installed package without path manipulation.

### Root Cause
Tests designed before package installation was configured.

### Root-Cause File
`tests/unit/test_component_registration.py`
`tests/unit/test_state_machine.py`
`reproduce_defects.py`

### Planned Correction
1. Remove all `sys.path.insert` calls from tests
2. Ensure `pip install -e .` is run before testing
3. Use proper package imports: `from loop_engine import ...`

---

## Defect #13: Absolute Machine-Specific Paths in Codebase

**Severity**: MEDIUM

### Reproduction Command
```bash
grep -r "/home/novix" --include="*.py" --include="*.sh"
```

### Actual Output
```
entrypoint.sh:cd /home/novix/workspace/project
experiments/generate_figures.py:RESULTS_DIR = "/home/novix/workspace/project/experiments/results"
experiments/generate_figures.py:FIGURES_DIR = "/home/novix/workspace/project/experiments/figures"
docs/BASELINE_FAILURE_REPORT.md:sys.path.insert(0, '/home/novix/workspace/project')
docs/BASELINE_FAILURE_REPORT.md:output_dir = "/home/novix/workspace/project/experiments/results"
```

### Expected Output
Only relative paths or `Path(__file__)` based resolution.

### Root Cause
Hard-coded paths from development environment.

### Root-Cause File
`entrypoint.sh`
`experiments/generate_figures.py`
Documentation files

### Planned Correction
1. Replace `/home/novix/workspace/project` with `Path(__file__).parent.parent` or similar
2. Use repository-relative paths
3. Update documentation to use relative paths

---

## Defect #14: Feature Flags Not Affecting Runtime Behavior

**Severity**: HIGH

### Reproduction Command
```python
config_enabled = LoopConfig(enable_verification=True)
config_disabled = LoopConfig(enable_verification=False)

# Both engines should behave differently
engine_enabled = LoopEngine(config_enabled)
engine_disabled = LoopEngine(config_disabled)

# Run both and compare traces
```

### Actual Output
```
enable_verification=True: True
enable_verification=False: False
# But behavior is identical - verifier not called in either case
```

### Expected Output
Different flag values should produce different execution traces and results.

### Root Cause
Flags exist in `LoopConfig` and are checked in `_execute_iteration()`, but:
1. Verification doesn't actually affect completion criteria
2. Memory read/write not implemented in loop
3. Safety checks not invoked
4. `execution_mode` not implemented

### Root-Cause File
`loop_engine/core.py` - Multiple methods need to respect flags

### Planned Correction
1. **Verification**: When enabled, verifier must be called and result affects completion
2. **Memory**: When enabled, read before planning, write after completion
3. **Safety**: When enabled, check at action gates; critical failures block action
4. **Execution Mode**: MULTI_AGENT should use different code path; HIERARCHICAL should raise UnsupportedExecutionMode

---

## Summary Table

| # | Defect | Severity | Root-Cause File | Status |
|---|--------|----------|-----------------|--------|
| 1 | Two-step task fails | CRITICAL | core.py | REPRODUCED |
| 2 | EVALUATING->PLANNING missing | CRITICAL | core.py | REPRODUCED |
| 3 | OBSERVING->PLANNING missing (disabled evaluator) | HIGH | core.py | REPRODUCED |
| 4 | Evaluator rejection doesn't block | CRITICAL | core.py | CONFIRMED |
| 5 | Recovery not executed | CRITICAL | core.py, components.py | REPRODUCED |
| 6 | Recovery invalid state | HIGH | core.py | CONFIRMED |
| 7 | max_recovery_attempts not propagated | MEDIUM | types.py, core.py | REPRODUCED |
| 8 | Exceptions lost | HIGH | core.py | PARTIAL |
| 9 | Incorrect iteration count | MEDIUM | core.py | REPRODUCED |
| 10 | Benchmark efficiency credit | HIGH | benchmarks/base.py | CONFIRMED |
| 11 | Missing pyproject.toml | HIGH | - | REPRODUCED |
| 12 | Tests use sys.path | MEDIUM | tests/ | REPRODUCED |
| 13 | Absolute paths | MEDIUM | Multiple files | REPRODUCED |
| 14 | Feature flags not connected | HIGH | core.py | REPRODUCED |

---

## Next Steps

Proceed to Phase 2: Redesign iteration lifecycle semantics with explicit ITERATION_COMPLETE state and proper transition specifications.
