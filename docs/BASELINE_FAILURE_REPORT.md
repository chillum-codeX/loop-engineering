# Baseline Failure Report

**Report Date**: 2026-06-24
**Framework Version**: 0.1.0 (pre-correction)
**Repository**: /home/novix/workspace/project

## Commands Executed

```bash
cd /home/novix/workspace/project

# Diagnostic test for component registration
python3 -c "
from loop_engine.core import LoopEngine, LoopConfig
from loop_engine.types import ComponentType
from loop_engine.components import LLMPlanner, LLMActor
from loop_engine.llm_client import MockLLMClient

engine = LoopEngine(LoopConfig())
llm = MockLLMClient()

# Register with STRING keys (as runner.py does)
engine.components['Planner'] = LLMPlanner(llm)
engine.components['Actor'] = LLMActor(llm)

print('Registered keys:', list(engine.components.keys()))
print('Looking up PLANNER enum:', engine.components.get(ComponentType.PLANNER))
print('Looking up ACTOR enum:', engine.components.get(ComponentType.ACTOR))
"

# Output:
# Registered keys: ['Planner', 'Actor']
# Looking up PLANNER enum: None
# Looking up ACTOR enum: None
```

```bash
# Diagnostic test for recovery logic
python3 -c "
from loop_engine.types import Failure, FailureType

failures = [Failure(type=FailureType.EXECUTION_ERROR, message='test', recoverable=True)]

# The broken logic from core.py lines 341-343:
recent_failures = [f for f in failures
                  if f.recoverable and f not in [r.get('failure') for r in
                  [{'failure': fa} for fa in failures]]]

print(f'Input failures: {len(failures)}')
print(f'Recent failures found: {len(recent_failures)}')
print(f'Expected: 1, Actual: {len(recent_failures)}')
"

# Output:
# Input failures: 1
# Recent failures found: 0
# Expected: 1, Actual: 0
```

```bash
# Full loop execution test
timeout 30 python3 -c "
import asyncio
from experiments.runner import ExperimentRunner, ExperimentConfig

config = ExperimentConfig(llm_provider='mock', num_runs=1)
runner = ExperimentRunner(config)

async def test():
    from benchmarks.tasks.multihop import MultiHopReasoningTask
    task = MultiHopReasoningTask(0)
    result = await runner.run_single_task(task, 'loop_engine', 0)
    for k, v in result.items():
        print(f'{k}: {v}')

asyncio.run(test())
"

# Output:
# INFO:loop_engine.core:Max iterations reached
# task_id: multihop_000
# task_name: Multi-Hop Reasoning
# method: loop_engine
# run_id: 0
# success: False
# score: 0.0
# execution_time: 0.0005
# iterations: 100
# token_usage: 0
# metadata: {'actual': 'None', ...}
```

## Confirmed Defects

### CRITICAL DEFECT 1: Component Registration Mismatch

**File**: `experiments/runner.py` lines 71-76
**Root Cause**: Type mismatch between registration keys and retrieval keys

**Registration** (in runner.py):
```python
engine.components['Planner'] = LLMPlanner(...)  # STRING key
engine.components['Actor'] = LLMActor(...)      # STRING key
```

**Retrieval** (in core.py line 236):
```python
planner = self.components.get(ComponentType.PLANNER)  # ENUM key
```

**Impact**: Components are registered but NEVER found during execution. The loop runs with no planner, actor, observer, evaluator, recovery, or terminator.

**Evidence**:
- Registered keys: `['Planner', 'Actor']`
- Lookup by enum returns: `None` for all components

### CRITICAL DEFECT 2: Recovery Logic Broken

**File**: `loop_engine/core.py` lines 341-343
**Root Cause**: Flawed list comprehension comparing objects incorrectly

**Defective Code**:
```python
recent_failures = [f for f in self.state.failures
                  if f.recoverable and f not in [r.get('failure') for r in
                  [{'failure': fa} for fa in self.state.failures]]]
```

**Problem**: The inner list creates `[{'failure': fa} for fa in failures]` (list of dicts), then extracts `[r.get('failure') for r in ...]` (list of Failure objects). The comparison `f not in [...]` should find `f` in the list, making the condition False.

**Impact**: `recent_failures` is ALWAYS empty. Recovery NEVER executes, even when failures occur.

**Evidence**:
- Input failures: 1
- Recent failures found: 0
- Expected: 1

### CRITICAL DEFECT 3: Missing Component Integration

**Files**: `loop_engine/core.py`, `loop_engine/verification/`, `loop_engine/memory/`, `loop_engine/safety/`, `loop_engine/budget/`

**Issue**: The following components exist but are NOT integrated into the main execution loop:
- `CrossVerifier` - never called
- `SafetyMonitor` - never started
- `MultiTierMemory` - never read/written
- `BudgetManager` - instantiated but not used for enforcement
- `AnomalyDetector` - never called
- `CircuitBreaker` - never used

**Configuration Flags** (all decorative):
- `enable_verification` - skips integration entirely
- `enable_memory` - never checked
- `enable_safety` - never checked

### DEFECT 4: No Explicit State Machine

**File**: `loop_engine/core.py`

**Issue**: Status is loosely managed. The engine can return `RUNNING` after execution completes.

**Evidence**:
- No state transition validation
- Final status determined by heuristic, not explicit state
- Line 402: `return self.state.status` can return RUNNING

### DEFECT 5: Hardcoded Paths

**File**: `experiments/runner.py` line 18
```python
sys.path.insert(0, '/home/novix/workspace/project')  # MACHINE-SPECIFIC
```

**File**: `experiments/runner.py` line 48
```python
output_dir: str = "/home/novix/workspace/project/experiments/results"
```

### DEFECT 6: Incomplete Benchmark Tasks

**Files**: `benchmarks/tasks/*.py`

**Issue**: Most `evaluate()` methods contain stub implementations that don't actually validate task completion.

**Example** (multihop.py):
```python
def evaluate(self, output: Any, metadata: Optional[Dict] = None) -> BenchmarkResult:
    # This will be implemented with actual execution results
    pass
```

### DEFECT 7: No Automated Test Suite

**Status**: Zero automated tests exist
**Impact**: No proof that any component is called, no regression protection

## Suspected Defects (To Be Verified)

1. **Budget Enforcement**: Budget checks happen but budget is never actually consumed (no token counting)
2. **Termination Logic**: Terminator component not found (None), falls back to simple progress check
3. **Plan Progress**: Always returns 0.0 because steps never complete (actor never executes)
4. **Safety Claims**: 100% security defense rate in existing results - unverified due to mock model

## Existing Claims Invalidated

From `HANDOFF_TO_WRITER.md`:

| Claim | Status | Reason |
|-------|--------|--------|
| "Verification components are implemented and integrated" | INVALID | Components exist but never called |
| "AdaptiveRecovery component implements... strategies" | INVALID | Recovery never executes |
| "Four out of four prompt injection attacks blocked (100%)" | INVALID | Mock model, not real security test |
| "All 5 security attack attempts were successfully blocked" | INVALID | No actual security execution |
| "Multi-tier memory system... implemented" | PARTIAL | Implemented but not integrated |
| "BudgetManager tracks tokens, steps, time, and cost" | PARTIAL | Tracks but doesn't enforce limits |
| "H1-H5: Framework validated" | UNSUPPORTED | No empirical validation possible |

## Files Requiring Correction

1. `loop_engine/core.py` - Fix component retrieval, recovery logic, state machine, integration
2. `experiments/runner.py` - Fix component registration, remove hardcoded paths
3. `loop_engine/types.py` - Add missing failure lifecycle tracking
4. `loop_engine/components.py` - Fix recovery interface
5. `benchmarks/tasks/*.py` - Implement evaluate() methods
6. `loop_engine/verification/verifier.py` - Connect to main loop
7. `loop_engine/memory/memory.py` - Connect to main loop
8. `loop_engine/safety/safety_monitor.py` - Connect to main loop
9. `loop_engine/budget/budget_manager.py` - Connect to main loop

## Initial Correction Plan

### Phase 1: Component Registry Fix
- Establish canonical registration API using ComponentType enum ONLY
- Reject string keys
- Add interface validation
- Add registration tests

### Phase 2: Recovery Tracking Fix
- Implement explicit failure identity tracking
- Define failure lifecycle states
- Fix recovery selection logic
- Add recovery tests

### Phase 3: State Machine
- Implement explicit execution states
- Define valid transitions
- Ensure final status correctness

### Phase 4: Configuration Connection
- Connect enable_* flags to actual behavior
- Ensure safety controls are immutable
- Add configuration integration tests

### Phase 5: Full Runtime Integration
- Integrate verification into loop
- Integrate memory read/write
- Integrate safety checks
- Add component call counters

### Phase 6: Deterministic Model
- Replace MockLLMClient with ScriptedModel
- Support controlled test scenarios
- Enable deterministic testing

### Phase 7: Test Suite
- Create comprehensive pytest suite
- Cover all critical paths
- Include adversarial tests

### Phase 8: Benchmark Validity
- Audit existing results
- Move invalid results to invalidated/
- Implement evaluate() methods
- Create valid benchmark comparison

### Phase 9: Multi-Agent
- Implement orchestrator
- Create deterministic multi-agent demo
- Test conflict detection

### Phase 10: Packaging
- Remove hardcoded paths
- Use pathlib
- Validate clean installation

## Acceptance Criteria for Correction Phase

Before declaring completion:
- [ ] Component registration uses enum keys exclusively
- [ ] Test proves planner, actor, observer, evaluator are called
- [ ] Engine never returns RUNNING after execution
- [ ] Recovery executes for eligible failures (test proves)
- [ ] Recovery doesn't repeat indefinitely (test proves)
- [ ] Verification affects completion (test proves)
- [ ] Memory affects execution when enabled (test proves)
- [ ] Budgets enforced with pre-action checks (test proves)
- [ ] Existing invalid benchmark results labeled
- [ ] `pytest -q` passes all tests
- [ ] Research claims match evidence
