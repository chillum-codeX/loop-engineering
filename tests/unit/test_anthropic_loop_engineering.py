"""
Tests for Anthropic Loop Engineering paper implementations.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from loop_engine.separation import (
    GeneratorConfig,
    EvaluatorConfig,
    SkepticalEvaluatorConfig,
    GeneratorEvaluatorSeparationValidator,
    EvaluatorPresets,
)
from loop_engine.skills import (
    SkillDefinition,
    SkillParser,
    SkillLoader,
    SkillValidator,
    EXAMPLE_TRIAGE_SKILL,
)
from loop_engine.budget_caps import (
    BudgetCaps,
    Usage,
    BudgetTracker,
    BudgetPresets,
)
from loop_engine.gates import (
    LintGate,
    SyntaxGate,
    SecurityGate,
    GateRunner,
    StandardGates,
    GateContext,
)
from loop_engine.checkpoint import (
    HumanCheckpoint,
    CheckpointConfig,
    HumanDecision,
    CheckpointPresets,
)


class TestGeneratorEvaluatorSeparation:
    """Test Generator/Evaluator separation (Section V of paper)."""

    def test_generator_has_higher_temperature(self):
        """Generator should have higher temperature for creativity."""
        gen = GeneratorConfig()
        eval_conf = EvaluatorConfig()

        assert gen.temperature > eval_conf.temperature
        assert gen.temperature == 0.7
        assert eval_conf.temperature == 0.0

    def test_evaluator_has_skeptical_prompt(self):
        """Evaluator should have skeptical system prompt."""
        eval_conf = EvaluatorConfig()

        prompt_lower = eval_conf.system_prompt.lower()
        assert "skeptical" in prompt_lower or "assume" in prompt_lower
        assert eval_conf.assume_broken is True

    def test_different_models_recommended(self):
        """Generator and evaluator should use different models ideally."""
        gen = GeneratorConfig()
        eval_conf = EvaluatorConfig()

        # They CAN be same model but SHOULD be different
        # Just verify they're configured
        assert gen.model is not None
        assert eval_conf.model is not None

    def test_separation_validator_detects_same_prompt(self):
        """Validator should detect identical prompts (Ego Loop anti-pattern)."""
        gen = GeneratorConfig(system_prompt="Same prompt")
        eval_conf = EvaluatorConfig(system_prompt="Same prompt")

        result = GeneratorEvaluatorSeparationValidator.validate_separation(gen, eval_conf)

        assert not result.is_valid
        assert any("identical" in issue.lower() for issue in result.issues)

    def test_separation_validator_allows_different_prompts(self):
        """Validator should pass for properly separated configs."""
        gen = GeneratorConfig()
        eval_conf = EvaluatorConfig()

        result = GeneratorEvaluatorSeparationValidator.validate_separation(gen, eval_conf)

        # Should be valid (no critical issues)
        assert result.is_valid

    def test_evaluator_presets(self):
        """Test evaluator preset configurations."""
        code_review = EvaluatorPresets.code_review()
        assert code_review.temperature == 0.0

        security = EvaluatorPresets.security_review()
        assert "security" in security.system_prompt.lower()


class TestSkillSystem:
    """Test SKILL.md system (Section IV of paper)."""

    def test_skill_parser_extracts_name(self):
        """Parser should extract skill name."""
        skill = SkillParser.parse_content(EXAMPLE_TRIAGE_SKILL)

        assert skill.name == "morning-triage"

    def test_skill_parser_extracts_sections(self):
        """Parser should extract all skill sections."""
        skill = SkillParser.parse_content(EXAMPLE_TRIAGE_SKILL)

        assert "morning" in skill.when.lower()
        assert len(skill.read) > 0
        assert "skip" in skill.judge.lower()
        assert "./state/triage.md" in skill.output.lower()
        assert len(skill.stop) > 0

    def test_skill_validation_requires_name(self):
        """Skill must have a name."""
        skill = SkillDefinition(name="")

        result = SkillValidator.validate(skill)

        assert not result.is_valid
        assert any("name" in issue.lower() for issue in result.issues)

    def test_skill_validation_warns_missing_judge(self):
        """Validator should warn about missing judgment criteria."""
        skill = SkillDefinition(
            name="test-skill",
            when="always",
            read=["file.txt"],
            judge="",  # Missing
        )

        result = SkillValidator.validate(skill)

        assert any("judge" in warning.lower() for warning in result.warnings)

    def test_skill_to_dict_roundtrip(self):
        """Skill should convert to/from dict."""
        original = SkillDefinition(
            name="test-skill",
            when="on trigger",
            read=["input.txt"],
            judge="is it good?",
            output="result.md",
            stop=["don't break"],
        )

        data = original.to_dict()
        restored = SkillDefinition.from_dict(data)

        assert restored.name == original.name
        assert restored.when == original.when
        assert restored.read == original.read


class TestBudgetCaps:
    """Test Budget Caps system (Section VIII of paper)."""

    def test_budget_caps_enforce_token_limit(self):
        """Caps should enforce token limits."""
        caps = BudgetCaps(per_run_tokens=1000)
        usage = Usage(tokens_used=1500)

        result = caps.check(usage)

        assert not result.passed
        assert any(v.cap_type.name == "TOKENS" for v in result.exceeded)

    def test_budget_caps_enforce_cost_limit(self):
        """Caps should enforce cost limits."""
        caps = BudgetCaps(per_run_cost=10.0)
        usage = Usage(cost_used=15.0)

        result = caps.check(usage)

        assert not result.passed
        assert any(v.cap_type.name == "COST" for v in result.exceeded)

    def test_budget_caps_enforce_retry_limit(self):
        """Caps should enforce retry limits."""
        caps = BudgetCaps(max_retries=3)
        usage = Usage(retries_used=5)

        result = caps.check(usage)

        assert not result.passed
        assert any(v.cap_type.name == "RETRIES" for v in result.exceeded)

    def test_budget_caps_pass_when_within_limits(self):
        """Caps should pass when within limits."""
        caps = BudgetCaps(per_run_tokens=1000, per_run_cost=10.0)
        usage = Usage(tokens_used=500, cost_used=5.0)

        result = caps.check(usage)

        assert result.passed
        assert len(result.exceeded) == 0

    def test_budget_tracker_records_usage(self):
        """Tracker should record usage history."""
        caps = BudgetCaps(per_run_tokens=1000)
        tracker = BudgetTracker(caps)

        tracker.start()
        tracker.record_tokens(100)
        tracker.record_tokens(200)

        assert tracker.usage.tokens_used == 300
        assert len(tracker.get_history()) == 2

    def test_budget_presets(self):
        """Test budget preset configurations."""
        conservative = BudgetPresets.conservative()
        assert conservative.per_run_tokens < 100000

        generous = BudgetPresets.generous()
        assert generous.per_run_tokens > conservative.per_run_tokens


class TestDeterministicGates:
    """Test Deterministic Gates (Stripe Minions pattern from Section VII.B)."""

    def test_syntax_gate_detects_invalid_python(self):
        """Syntax gate should detect invalid Python code."""
        gate = SyntaxGate()
        context = GateContext(content="def broken(:")

        result = gate.check(context)

        assert not result.passed
        assert "syntax" in result.message.lower()

    def test_syntax_gate_passes_valid_python(self):
        """Syntax gate should pass valid Python code."""
        gate = SyntaxGate()
        context = GateContext(content="def valid():\n    pass")

        result = gate.check(context)

        assert result.passed

    def test_security_gate_detects_eval(self):
        """Security gate should detect dangerous eval()."""
        gate = SecurityGate()
        context = GateContext(content="result = eval(user_input)")

        result = gate.check(context)

        assert not result.passed

    def test_security_gate_passes_safe_code(self):
        """Security gate should pass safe code."""
        gate = SecurityGate()
        context = GateContext(content="result = 1 + 1")

        result = gate.check(context)

        assert result.passed

    def test_gate_runner_stops_on_failure(self):
        """Runner should fail if any gate fails."""
        runner = GateRunner()
        runner.add_gate(SyntaxGate())

        context = GateContext(content="invalid python {{")
        result = runner.run_all(context)

        assert not result.passed

    def test_standard_gates_python_code(self):
        """Standard Python gates should include syntax and security."""
        runner = StandardGates.python_code()

        assert len(runner.gates) >= 2


class TestHumanCheckpoints:
    """Test Human Checkpoints (Section VII.C)."""

    def test_checkpoint_should_pause_on_major_failure(self):
        """Checkpoint should trigger on major failure."""
        from loop_engine.types import Failure, FailureType, FailureStatus
        from loop_engine.core import LoopState

        config = CheckpointConfig(trigger_on_major_failure=True)
        checkpoint = HumanCheckpoint(config)

        state = LoopState()
        failure = Failure(
            type=FailureType.EXECUTION_ERROR,
            message="Test failure",
        )
        failure.mark_terminal()
        state.failures.append(failure)

        trigger = checkpoint.should_pause(state)

        assert trigger is not None

    def test_checkpoint_respects_disabled_config(self):
        """Checkpoint should not trigger when disabled."""
        from loop_engine.types import Failure, FailureType
        from loop_engine.core import LoopState

        config = CheckpointConfig(enabled=False)
        checkpoint = HumanCheckpoint(config)

        state = LoopState()
        state.failures.append(Failure(type=FailureType.EXECUTION_ERROR))

        trigger = checkpoint.should_pause(state)

        assert trigger is None

    def test_review_request_includes_state_summary(self):
        """Review request should include state summary."""
        from loop_engine.core import LoopState

        checkpoint = HumanCheckpoint()
        state = LoopState()
        state.current_iteration = 5

        request = checkpoint.present_for_review(
            state,
            trigger=None,
            proposed_action="Continue"
        )

        assert request.state_summary["iteration"] == 5
        assert request.proposed_action == "Continue"

    def test_checkpoint_presets(self):
        """Test checkpoint preset configurations."""
        manual = CheckpointPresets.manual_only()
        assert manual.trigger_on_failure is False

        conservative = CheckpointPresets.conservative()
        assert conservative.trigger_on_failure is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
