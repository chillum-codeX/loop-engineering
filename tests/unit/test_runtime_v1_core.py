"""
Basic integration tests for Runtime V1
"""

import pytest
import tempfile
from pathlib import Path

from loop_engine.runtime_contracts import (
    RuntimeState,
    TaskRecord,
    TaskLedger,
    TaskStatus,
    TaskPriority,
    RuntimePhase,
)
from loop_engine.runtime_persistence import RuntimeStatePersistence, RuntimePersistenceConfig


class TestRuntimeState:
    """Test the unified RuntimeState."""

    def test_runtime_state_creation(self):
        """Test creating a RuntimeState."""
        state = RuntimeState()
        assert state.runtime_id is not None
        assert state.schema_version == "1.0.0"
        assert state.task_ledger is not None
        assert state.current_iteration == 0

    def test_get_current_task(self):
        """Test getting the current task."""
        state = RuntimeState()
        task = TaskRecord(goal="Test")
        state.task_ledger.add_task(task)
        state.current_task_id = task.task_id

        current = state.get_current_task()
        assert current == task

    def test_phase_transitions(self):
        """Test phase status transitions."""
        from loop_engine.runtime_contracts import DiscoveryStatus
        state = RuntimeState()

        state.set_phase(RuntimePhase.DISCOVERY)
        assert state.current_phase == RuntimePhase.DISCOVERY

        state.set_phase_status(RuntimePhase.DISCOVERY, DiscoveryStatus.LOADING_STATE)
        assert state.phase_states.discovery == DiscoveryStatus.LOADING_STATE


class TestTaskRecord:
    """Test TaskRecord functionality."""

    def test_task_lifecycle(self):
        """Test task status transitions."""
        task = TaskRecord(goal="Test task")

        assert task.status == TaskStatus.PENDING

        task.transition_to(TaskStatus.DISCOVERED)
        assert task.status == TaskStatus.DISCOVERED
        assert len(task.status_history) == 1

        task.transition_to(TaskStatus.IN_PROGRESS)
        assert task.status == TaskStatus.IN_PROGRESS

    def test_task_to_dict(self):
        """Test task serialization."""
        task = TaskRecord(
            goal="Test goal",
            skill_name="test-skill",
        )
        task.transition_to(TaskStatus.DISCOVERED)

        data = task.to_dict()
        assert data["goal"] == "Test goal"
        assert data["skill_name"] == "test-skill"
        assert data["status"] == "discovered"


class TestTaskLedger:
    """Test TaskLedger functionality."""

    def test_add_task(self):
        """Test adding tasks to ledger."""
        ledger = TaskLedger()
        task = TaskRecord(goal="Test")

        ledger.add_task(task)

        assert len(ledger.tasks) == 1
        assert task.discovered_at is not None

    def test_select_next_task_priority(self):
        """Test task selection by priority."""
        ledger = TaskLedger()

        low = TaskRecord(goal="Low", priority=TaskPriority.LOW)
        high = TaskRecord(goal="High", priority=TaskPriority.HIGH)

        ledger.add_task(low)
        ledger.add_task(high)

        next_task = ledger.select_next_task()
        assert next_task == high

    def test_complete_task(self):
        """Test completing a task."""
        ledger = TaskLedger()
        task = TaskRecord(goal="Test")
        ledger.add_task(task)

        ledger.complete_task(task.task_id, success=True)

        assert task.status == TaskStatus.COMMITTED
        assert len(ledger.completed_task_ids) == 1


class TestRuntimePersistence:
    """Test runtime persistence."""

    def test_json_backend(self):
        """Test using JSON backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimePersistenceConfig(
                state_dir=Path(tmpdir),
                backend="json",
            )
            persistence = RuntimeStatePersistence(config)

            state = RuntimeState(runtime_id="test")
            path = persistence.save(state, "trace-1")

            assert path is not None
            assert path.suffix == ".json"

            loaded = persistence.load("trace-1")
            assert loaded.runtime_id == "test"

    def test_save_and_load(self):
        """Test full save and load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimePersistenceConfig(
                state_dir=Path(tmpdir),
                backend="json",
                verify_on_save=True,
            )
            persistence = RuntimeStatePersistence(config)

            # Create state with data
            state = RuntimeState(runtime_id="test-123", trace_id="trace-456")
            state.current_iteration = 42

            task = TaskRecord(task_id="task-1", goal="Test task")
            state.task_ledger.add_task(task)
            state.current_task_id = "task-1"

            # Save
            persistence.save(state, "trace-456")

            # Load
            loaded = persistence.load("trace-456")
            assert loaded.runtime_id == "test-123"
            assert loaded.current_iteration == 42
            assert loaded.current_task_id == "task-1"
            assert "task-1" in loaded.task_ledger.tasks

    def test_load_latest(self):
        """Test loading the most recent state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimePersistenceConfig(state_dir=Path(tmpdir))
            persistence = RuntimeStatePersistence(config)

            # Save multiple states
            state1 = RuntimeState(runtime_id="runtime-1")
            state2 = RuntimeState(runtime_id="runtime-2")

            persistence.save(state1, "trace-1")
            import time
            time.sleep(0.01)
            persistence.save(state2, "trace-2")

            latest = persistence.load_latest()
            assert latest is not None
            assert latest.runtime_id == "runtime-2"

    def test_list_saved_states(self):
        """Test listing saved states."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimePersistenceConfig(state_dir=Path(tmpdir))
            persistence = RuntimeStatePersistence(config)

            state1 = RuntimeState(runtime_id="runtime-1")
            state2 = RuntimeState(runtime_id="runtime-2")

            persistence.save(state1, "trace-1")
            persistence.save(state2, "trace-2")

            states = persistence.list_saved_states()
            assert len(states) == 2

            trace_ids = {s["trace_id"] for s in states}
            assert trace_ids == {"trace-1", "trace-2"}

    def test_get_stats(self):
        """Test getting persistence statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimePersistenceConfig(state_dir=Path(tmpdir))
            persistence = RuntimeStatePersistence(config)

            state = RuntimeState(runtime_id="test")
            persistence.save(state, "trace-1")
            persistence.save(state, "trace-2")

            stats = persistence.get_stats()
            assert stats["save_count"] == 2
            assert stats["backend"] == "json"
