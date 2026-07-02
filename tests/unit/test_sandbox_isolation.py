"""Adversarial tests for isolated code execution."""

import asyncio

import pytest

from loop_engine.safety.safety_monitor import Sandbox, SecurityError


@pytest.mark.asyncio
async def test_isolated_worker_returns_json_result():
    sandbox = Sandbox(max_cpu_time=2)

    result = await sandbox.execute("result = sum(values)", {"values": [1, 2, 3]})

    assert result == 6
    assert sandbox.get_execution_log()[-1]["success"] is True


@pytest.mark.asyncio
async def test_file_access_and_imports_are_rejected():
    sandbox = Sandbox(max_cpu_time=2)

    with pytest.raises(SecurityError):
        await sandbox.execute("result = open('secret.txt').read()")
    with pytest.raises(SecurityError, match="Import is not allowed"):
        await sandbox.execute("import os\nresult = os.getcwd()")


@pytest.mark.asyncio
async def test_dunder_introspection_is_rejected():
    sandbox = Sandbox(max_cpu_time=2)

    with pytest.raises(SecurityError, match="Dunder"):
        await sandbox.execute("result = ().__class__.__mro__")


@pytest.mark.asyncio
async def test_infinite_loop_is_killed():
    sandbox = Sandbox(max_cpu_time=0.2)

    with pytest.raises(SecurityError, match="timed out"):
        await sandbox.execute("while True:\n    pass")

    await asyncio.sleep(0.05)
    assert sandbox.get_execution_log()[-1]["error"] == "timeout"
