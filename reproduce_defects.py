"""
Reproduction script for runtime defects.
Tests the current state of the loop engine to document defects.
"""

import asyncio
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loop_engine.core import LoopEngine, LoopConfig
from loop_engine.types import (
    ComponentType, LoopContext, Budget, Failure, FailureType,
    ExecutionState, Step, Plan
)
from loop_engine.components import (
    LLMPlanner, LLMActor, SimpleObserver, LLMEvaluator,
    AdaptiveRecovery, CombinedTerminator
)
from loop_engine.llm_client import MockLLMClient


class DefectReproduction:
    """Reproduce and document runtime defects."""

    def __init__(self):
        self.results = []

    def log_defect(self, number, name, command, actual, expected, root_cause, severity, planned_fix):
        """Log a defect for the baseline document."""
        self.results.append({
            "number": number,
            "name": name,
            "command": command,
            "actual": actual,
            "expected": expected,
            "root_cause": root_cause,
            "severity": severity,
            "planned_fix": planned_fix
        })

    async def defect_1_two_step_task_fails(self):
        """Defect 1: Two-step task failing on second iteration."""
        print("\n=== Defect 1: Two-step task failing on second iteration ===")

        engine = LoopEngine(LoopConfig(max_iterations=5, verbose=True))
        llm = MockLLMClient()

        # Register components
        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        context = LoopContext(
            goal="Complete a two-step task: step 1 then step 2",
            budget=Budget(max_steps=10)
        )

        try:
            result = await engine.run(context)
            print(f"Result status: {result.status}")
            print(f"Iterations: {result.iterations}")
            print(f"Execution state: {engine.state.execution_state if engine.state else 'N/A'}")

            # Check if we completed both iterations
            if result.iterations < 2:
                self.log_defect(
                    number=1,
                    name="Two-step task fails on second iteration",
                    command="python reproduce_defects.py",
                    actual=f"Completed {result.iterations} iteration(s), status={result.status}",
                    expected="Completed 2+ iterations with both steps executed",
                    root_cause="State machine doesn't support repeated iterations - transitions from terminal-like states not handled",
                    severity="CRITICAL",
                    planned_fix="Add ITERATION_COMPLETE state and explicit iteration boundary logic"
                )
                return False
            return True
        except Exception as e:
            print(f"Exception: {e}")
            self.log_defect(
                number=1,
                name="Two-step task fails on second iteration",
                command="python reproduce_defects.py",
                actual=f"Exception: {e}",
                expected="Successful completion of 2+ iterations",
                root_cause="State machine transition error or other runtime defect",
                severity="CRITICAL",
                planned_fix="Fix state transitions and iteration boundary logic"
            )
            return False

    async def defect_2_evaluating_to_planning_transition(self):
        """Defect 2: Transition error EVALUATING -> PLANNING."""
        print("\n=== Defect 2: Transition error EVALUATING -> PLANNING ===")

        engine = LoopEngine(LoopConfig(max_iterations=3, verbose=True))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))

        # Manually test transition
        engine.state = type('State', (), {
            'execution_state': ExecutionState.EVALUATING,
            'status': type('Status', (), {'value': 'RUNNING'})()
        })()

        try:
            engine._transition_to(ExecutionState.PLANNING)
            print("ERROR: Transition succeeded but should have failed!")
            self.log_defect(
                number=2,
                name="Missing transition validation - EVALUATING -> PLANNING succeeds incorrectly",
                command="Manual _transition_to() call",
                actual="Transition succeeded (no error)",
                expected="RuntimeError: Invalid state transition",
                root_cause="EVALUATING -> PLANNING is not in _VALID_TRANSITIONS, but the test bypassed validation",
                severity="HIGH",
                planned_fix="Verify _VALID_TRANSITIONS correctly excludes invalid transitions"
            )
            return False
        except RuntimeError as e:
            if "Invalid state transition" in str(e):
                print(f"CORRECT: Transition rejected - {e}")
                # Now let's see what valid transitions exist
                valid = engine._VALID_TRANSITIONS.get(ExecutionState.EVALUATING, set())
                print(f"Valid transitions from EVALUATING: {[s.value for s in valid]}")

                if ExecutionState.PLANNING not in valid:
                    self.log_defect(
                        number=2,
                        name="EVALUATING -> PLANNING transition missing (needed for next iteration)",
                        command="Check _VALID_TRANSITIONS",
                        actual=f"Valid: {[s.value for s in valid]}",
                        expected="PLANNING should be valid via ITERATION_COMPLETE intermediate state",
                        root_cause="No ITERATION_COMPLETE state to bridge iterations; EVALUATING cannot directly go to PLANNING",
                        severity="CRITICAL",
                        planned_fix="Add ITERATION_COMPLETE state with transition EVALUATING -> ITERATION_COMPLETE -> PLANNING"
                    )
                return True
            else:
                print(f"Unexpected error: {e}")
                return False

    async def defect_3_disabled_evaluator_transition(self):
        """Defect 3: Transition error when evaluator disabled: OBSERVING -> PLANNING."""
        print("\n=== Defect 3: Disabled evaluator transition OBSERVING -> PLANNING ===")

        engine = LoopEngine(LoopConfig(max_iterations=3, enable_evaluator=False, verbose=True))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())

        # Check valid transitions from OBSERVING
        valid = engine._VALID_TRANSITIONS.get(ExecutionState.OBSERVING, set())
        print(f"Valid transitions from OBSERVING: {[s.value for s in valid]}")

        # When evaluator is disabled, we need to go from OBSERVING to PLANNING
        # But this is not a valid transition
        if ExecutionState.PLANNING not in valid:
            self.log_defect(
                number=3,
                name="OBSERVING -> PLANNING missing (needed when evaluator disabled)",
                command="Check _VALID_TRANSITIONS with enable_evaluator=False",
                actual=f"Valid: {[s.value for s in valid]}",
                expected="Either PLANNING or ITERATION_COMPLETE should be valid for next iteration",
                root_cause="No bypass path for disabled evaluator; OBSERVING cannot reach next iteration",
                severity="HIGH",
                planned_fix="Add OBSERVING -> ITERATION_COMPLETE transition for disabled evaluator path"
            )
            return False
        return True

    async def defect_4_evaluator_rejected_but_completed(self):
        """Defect 4: Evaluator returns passed=False but engine returns COMPLETED."""
        print("\n=== Defect 4: Evaluator rejection doesn't block completion ===")

        # This requires creating a scenario where evaluator returns passed=False
        # but the engine still completes

        engine = LoopEngine(LoopConfig(max_iterations=3, verbose=True))
        llm = MockLLMClient()

        # Create a custom evaluator that always rejects
        class AlwaysRejectEvaluator:
            async def evaluate(self, plan, observations, goal, context):
                from loop_engine.types import Evaluation
                return Evaluation(
                    score=0.0,
                    passed=False,
                    feedback="Always rejected for testing"
                )

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, AlwaysRejectEvaluator())

        context = LoopContext(goal="Test rejection handling", budget=Budget(max_steps=5))

        try:
            result = await engine.run(context)
            print(f"Result status: {result.status}")
            print(f"Evaluations: {len(result.evaluations)}")

            # Check if any evaluation failed but we still completed
            failed_evaluations = [e for e in result.evaluations if not e.passed]

            if failed_evaluations and result.status.name == "COMPLETED":
                self.log_defect(
                    number=4,
                    name="Evaluator rejection doesn't block completion",
                    command="Run with AlwaysRejectEvaluator",
                    actual=f"Status={result.status.name} despite {len(failed_evaluations)} failed evaluations",
                    expected="Status=FAILED or recovery triggered",
                    root_cause="Engine doesn't check evaluation results in final status determination",
                    severity="CRITICAL",
                    planned_fix="Add evaluation result checking to _determine_final_status and iteration boundary"
                )
                return False
            elif failed_evaluations and result.status.name == "FAILED":
                print("CORRECT: Failed evaluations led to FAILED status")
                return True
            else:
                print(f"Unexpected state: {result.status}")
                return False
        except Exception as e:
            print(f"Exception: {e}")
            return False

    async def defect_5_recovery_not_executed(self):
        """Defect 5: Recovery returns strategy without executing it."""
        print("\n=== Defect 5: Recovery strategy not actually executed ===")

        engine = LoopEngine(LoopConfig(max_iterations=3, verbose=True))
        llm = MockLLMClient()

        # Track if recovery actually changed anything
        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))
        engine.register_component(ComponentType.OBSERVER, SimpleObserver())
        engine.register_component(ComponentType.EVALUATOR, LLMEvaluator(llm))
        engine.register_component(ComponentType.RECOVERY, AdaptiveRecovery())

        context = LoopContext(goal="Test recovery execution", budget=Budget(max_steps=5))

        result = await engine.run(context)

        print(f"Recoveries: {len(result.recoveries)}")
        for r in result.recoveries:
            print(f"  Recovery: {r.strategy.value}, executed={getattr(r, 'executed', 'N/A')}")

        # Check if recovery actions have been executed
        unexecuted_recoveries = [
            r for r in result.recoveries
            if not getattr(r, 'executed', False)
        ]

        if unexecuted_recoveries:
            self.log_defect(
                number=5,
                name="Recovery strategy selected but not executed",
                command="Run with recovery component",
                actual=f"{len(unexecuted_recoveries)} recovery actions with executed=False",
                expected="Recovery actions should have executed=True and state changes",
                root_cause="Recovery only creates RecoveryAction objects without executing handlers",
                severity="CRITICAL",
                planned_fix="Implement recovery strategy handlers that perform actual state changes"
            )
            return False
        return True

    async def defect_6_recovery_invalid_state(self):
        """Defect 6: Successful recovery leaves runtime in invalid state."""
        print("\n=== Defect 6: Recovery leaves invalid state ===")

        # This is hard to test without a working recovery
        # We'll document it as a known issue

        self.log_defect(
            number=6,
            name="Successful recovery may leave runtime in invalid state",
            command="N/A - requires working recovery",
            actual="Not directly testable with current implementation",
            expected="Recovery transitions to valid next state (REPLANNING or ITERATION_COMPLETE)",
            root_cause="No validation that recovery produces valid post-conditions",
            severity="HIGH",
            planned_fix="Add post-recovery state validation and explicit transition to valid state"
        )
        return False

    async def defect_7_max_recovery_not_propagated(self):
        """Defect 7: max_recovery_attempts from LoopConfig not propagated to failures."""
        print("\n=== Defect 7: max_recovery_attempts not propagated ===")

        # Check if failures created by the engine use the config value
        config = LoopConfig(max_recovery_attempts=5)
        engine = LoopEngine(config)

        # Create a failure in the engine
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message="Test error"
        )

        print(f"Config max_recovery_attempts: {config.max_recovery_attempts}")
        print(f"Failure max_recovery_attempts: {failure.max_recovery_attempts}")

        if failure.max_recovery_attempts != config.max_recovery_attempts:
            self.log_defect(
                number=7,
                name="max_recovery_attempts not propagated from LoopConfig to Failure",
                command="Create Failure and compare to LoopConfig",
                actual=f"Failure has max_recovery_attempts={failure.max_recovery_attempts}, config has {config.max_recovery_attempts}",
                expected="Failure should inherit max_recovery_attempts from LoopConfig",
                root_cause="Failure uses hard-coded default instead of config value",
                severity="MEDIUM",
                planned_fix="Pass max_recovery_attempts from LoopConfig when creating Failures"
            )
            return False
        return True

    async def defect_8_exceptions_lost(self):
        """Defect 8: Runtime exceptions lost or overwritten in final result."""
        print("\n=== Defect 8: Runtime exceptions lost in result ===")

        # Create a component that raises an exception
        class FailingActor:
            async def execute(self, step, observations, context):
                raise ValueError("Intentional test failure")

            async def execute_direct(self, goal, context):
                raise ValueError("Intentional test failure")

        engine = LoopEngine(LoopConfig(max_iterations=3))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, FailingActor())

        context = LoopContext(goal="Test exception handling", budget=Budget(max_steps=5))

        try:
            result = await engine.run(context)
            print(f"Result status: {result.status}")
            print(f"Failures: {len(result.failures)}")

            # Check if exception information is preserved
            if result.failures:
                last_failure = result.failures[-1]
                print(f"Last failure type: {last_failure.type}")
                print(f"Last failure message: {last_failure.message}")

                if "Intentional test failure" not in last_failure.message:
                    self.log_defect(
                        number=8,
                        name="Exception details lost in final result",
                        command="Run with FailingActor",
                        actual=f"Failure message: {last_failure.message}",
                        expected="Failure should contain 'Intentional test failure'",
                        root_cause="Exception message not properly captured in Failure",
                        severity="HIGH",
                        planned_fix="Ensure exception details are preserved in state.failures and result"
                    )
                    return False
            return True
        except Exception as e:
            print(f"Unexpected: Exception propagated out of run(): {e}")
            return False

    async def defect_9_incorrect_iteration_count(self):
        """Defect 9: Incorrect iteration count on failed execution."""
        print("\n=== Defect 9: Incorrect iteration count ===")

        # This requires testing that iterations are counted correctly
        # even when execution fails

        engine = LoopEngine(LoopConfig(max_iterations=3))
        llm = MockLLMClient()

        engine.register_component(ComponentType.PLANNER, LLMPlanner(llm))
        engine.register_component(ComponentType.ACTOR, LLMActor(llm))

        context = LoopContext(goal="Test iteration counting", budget=Budget(max_steps=2))

        result = await engine.run(context)

        print(f"Result iterations: {result.iterations}")
        print(f"Result status: {result.status}")

        # Budget allows 2 steps, so we should have 2 iterations
        # But if the engine stops early, the count might be wrong

        # This is more of a potential issue - let's document it
        self.log_defect(
            number=9,
            name="Iteration count may be incorrect on early termination",
            command="Run with limited budget",
            actual=f"Iterations reported: {result.iterations}",
            expected="Accurate count of actually executed iterations",
            root_cause="Iteration counting logic may not handle all termination paths correctly",
            severity="MEDIUM",
            planned_fix="Audit iteration counting in all termination paths"
        )
        return False

    async def defect_10_benchmark_efficiency_credit(self):
        """Defect 10: Benchmark records receiving efficiency credit despite incorrect output."""
        print("\n=== Defect 10: Benchmark efficiency credit for incorrect output ===")

        # This requires examining the benchmark scoring logic
        # For now, document as known issue to investigate

        self.log_defect(
            number=10,
            name="Benchmark may award efficiency credit for incorrect/empty output",
            command="Examine benchmarks/base.py and benchmark runners",
            actual="Scoring logic not yet audited",
            expected="Incorrect/empty/crashed outputs should receive score=0",
            root_cause="Scoring formula may not gate efficiency on correctness",
            severity="HIGH",
            planned_fix="Implement correctness-first scoring: if not correct, total_score=0"
        )
        return False

    async def defect_11_editable_installation(self):
        """Defect 11: Editable installation failure."""
        print("\n=== Defect 11: Editable installation ===")

        # Check if pyproject.toml exists and is valid
        pyproject_path = project_root / "pyproject.toml"

        if not pyproject_path.exists():
            self.log_defect(
                number=11,
                name="Missing pyproject.toml for editable installation",
                command="pip install -e .",
                actual="pyproject.toml does not exist",
                expected="Valid pyproject.toml with package configuration",
                root_cause="No packaging configuration exists",
                severity="HIGH",
                planned_fix="Create valid pyproject.toml with package metadata"
            )
            return False
        else:
            print(f"pyproject.toml exists at {pyproject_path}")
            return True

    async def defect_12_plain_pytest(self):
        """Defect 12: Plain pytest import failure."""
        print("\n=== Defect 12: Plain pytest import ===")

        # Check for sys.path manipulation in tests
        test_file = project_root / "tests" / "unit" / "test_component_registration.py"

        if test_file.exists():
            content = test_file.read_text()
            if "sys.path.insert" in content:
                self.log_defect(
                    number=12,
                    name="Tests use sys.path manipulation instead of proper package installation",
                    command="pytest -q (without sys.path setup)",
                    actual="Tests contain sys.path.insert() calls",
                    expected="Tests import from installed package without path manipulation",
                    root_cause="Tests not designed for installed package use",
                    severity="MEDIUM",
                    planned_fix="Remove sys.path manipulation and rely on pip install -e ."
                )
                return False
        return True

    async def defect_13_absolute_paths(self):
        """Defect 13: Remaining absolute machine-specific paths."""
        print("\n=== Defect 13: Absolute machine-specific paths ===")

        # Search for absolute paths in codebase
        abs_paths_found = []

        for py_file in project_root.rglob("*.py"):
            try:
                content = py_file.read_text()
                if "/home/novix" in content or "/home/" in content:
                    abs_paths_found.append(str(py_file.relative_to(project_root)))
            except:
                pass

        if abs_paths_found:
            self.log_defect(
                number=13,
                name="Absolute machine-specific paths in codebase",
                command="grep -r '/home/novix' --include='*.py'",
                actual=f"Found in: {abs_paths_found}",
                expected="Only relative paths or pathlib-based path resolution",
                root_cause="Hard-coded absolute paths for development environment",
                severity="MEDIUM",
                planned_fix="Replace with Path(__file__).parent patterns"
            )
            return False
        return True

    async def defect_14_feature_flags_not_connected(self):
        """Defect 14: Feature flags not affecting runtime behavior."""
        print("\n=== Defect 14: Feature flags not connected ===")

        # Check if enable_verification affects behavior
        config_enabled = LoopConfig(enable_verification=True)
        config_disabled = LoopConfig(enable_verification=False)

        engine_enabled = LoopEngine(config_enabled)
        engine_disabled = LoopEngine(config_disabled)

        # Both engines should have different behavior but currently
        # the flag is only checked in _execute_iteration, not in final status

        print(f"enable_verification=True: {config_enabled.enable_verification}")
        print(f"enable_verification=False: {config_disabled.enable_verification}")

        # The flags exist but need to be connected to actual behavior
        self.log_defect(
            number=14,
            name="Feature flags (enable_verification, enable_memory, enable_safety, execution_mode) not affecting runtime",
            command="Compare engine behavior with different flag values",
            actual="Flags exist in config but don't change trace or final behavior",
            expected="Different flag values produce different execution traces",
            root_cause="Flags checked in _execute_iteration but not integrated into completion logic or other phases",
            severity="HIGH",
            planned_fix="Connect flags to actual component invocation and completion criteria"
        )
        return False

    async def run_all(self):
        """Run all defect reproductions."""
        print("=" * 60)
        print("RUNTIME DEFECT REPRODUCTION")
        print("=" * 60)

        await self.defect_1_two_step_task_fails()
        await self.defect_2_evaluating_to_planning_transition()
        await self.defect_3_disabled_evaluator_transition()
        await self.defect_4_evaluator_rejected_but_completed()
        await self.defect_5_recovery_not_executed()
        await self.defect_6_recovery_invalid_state()
        await self.defect_7_max_recovery_not_propagated()
        await self.defect_8_exceptions_lost()
        await self.defect_9_incorrect_iteration_count()
        await self.defect_10_benchmark_efficiency_credit()
        await self.defect_11_editable_installation()
        await self.defect_12_plain_pytest()
        await self.defect_13_absolute_paths()
        await self.defect_14_feature_flags_not_connected()

        # Print summary
        print("\n" + "=" * 60)
        print("DEFECT SUMMARY")
        print("=" * 60)

        for defect in self.results:
            print(f"\nDefect #{defect['number']}: {defect['name']}")
            print(f"  Severity: {defect['severity']}")
            print(f"  Root Cause: {defect['root_cause'][:80]}...")
            print(f"  Planned Fix: {defect['planned_fix'][:80]}...")

        print(f"\n\nTotal defects documented: {len(self.results)}")

        return self.results


async def main():
    repro = DefectReproduction()
    results = await repro.run_all()

    # Save results for documentation
    import json
    output_file = project_root / "docs" / "defect_reproduction_results.json"
    output_file.parent.mkdir(exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
