"""Benchmark evaluators must accept oracles and reject empty controls."""

from experiments.deterministic_runner import run_suite


def test_all_benchmark_evaluators_pass_deterministic_controls():
    result = run_suite()

    assert result["network_calls"] == 0
    assert result["claims_model_performance"] is False
    assert result["all_oracles_passed"] is True
    assert result["all_negative_controls_rejected"] is True
