"""
Real State Persistence Module for Loop Runtime V1
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from .runtime_contracts import (
    BudgetReservation,
    BudgetReservationStatus,
    DiscoveryStatus,
    EventType,
    GateOutcomeData,
    HandoffStatus,
    PersistenceStatus,
    PhaseState,
    RuntimeEvent,
    RuntimePhase,
    RuntimeState,
    SchedulingStatus,
    TaskLedger,
    TaskPriority,
    TaskRecord,
    TaskStatus,
    VerificationOutcome,
    VerificationVerdict,
)
from .types import Failure, FailureStatus, FailureType, RecoveryAction, RecoveryStrategy


def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _deserialize_datetime(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _serialize_path(p: Optional[Path]) -> Optional[str]:
    return str(p) if p else None


def _deserialize_path(s: Optional[str]) -> Optional[Path]:
    return Path(s) if s else None


class StateSerializer:
    """Handles serialization/deserialization of runtime state objects."""

    @staticmethod
    def serialize_task_record(task: TaskRecord) -> Dict[str, Any]:
        return {
            "task_id": task.task_id,
            "skill_name": task.skill_name,
            "goal": task.goal,
            "context": task.context,
            "priority": task.priority.value,
            "status": task.status.value,
            "status_history": task.status_history,
            "discovered_at": _serialize_datetime(task.discovered_at),
            "reserved_at": _serialize_datetime(task.reserved_at),
            "started_at": _serialize_datetime(task.started_at),
            "completed_at": _serialize_datetime(task.completed_at),
            "budget_reservation_id": task.budget_reservation_id,
            "worktree_path": _serialize_path(task.worktree_path),
        }

    @staticmethod
    def deserialize_task_record(data: Dict[str, Any]) -> TaskRecord:
        task = TaskRecord(
            task_id=data.get("task_id", str(uuid.uuid4())[:8]),
            skill_name=data.get("skill_name"),
            goal=data.get("goal", ""),
            context=data.get("context", {}),
            priority=TaskPriority(data.get("priority", 2)),
            status=TaskStatus(data.get("status", "pending")),
            status_history=data.get("status_history", []),
            discovered_at=_deserialize_datetime(data.get("discovered_at")),
            reserved_at=_deserialize_datetime(data.get("reserved_at")),
            started_at=_deserialize_datetime(data.get("started_at")),
            completed_at=_deserialize_datetime(data.get("completed_at")),
            budget_reservation_id=data.get("budget_reservation_id"),
            worktree_path=_deserialize_path(data.get("worktree_path")),
        )
        return task

    @staticmethod
    def serialize_task_ledger(ledger: TaskLedger) -> Dict[str, Any]:
        return {
            "tasks": {
                task_id: StateSerializer.serialize_task_record(task)
                for task_id, task in ledger.tasks.items()
            },
            "completed_task_ids": ledger.completed_task_ids,
            "failed_task_ids": ledger.failed_task_ids,
        }

    @staticmethod
    def deserialize_task_ledger(data: Dict[str, Any]) -> TaskLedger:
        ledger = TaskLedger()
        for task_id, task_data in data.get("tasks", {}).items():
            task = StateSerializer.deserialize_task_record(task_data)
            ledger.tasks[task_id] = task
        ledger.completed_task_ids = data.get("completed_task_ids", [])
        ledger.failed_task_ids = data.get("failed_task_ids", [])
        return ledger

    @staticmethod
    def serialize_runtime_state(state: RuntimeState) -> Dict[str, Any]:
        from .types import LoopStatus
        return {
            "schema_version": state.schema_version,
            "runtime_id": state.runtime_id,
            "trace_id": state.trace_id,
            "status": state.status.name if hasattr(state.status, 'name') else str(state.status),
            "current_phase": state.current_phase.value if state.current_phase else None,
            "task_ledger": StateSerializer.serialize_task_ledger(state.task_ledger),
            "current_task_id": state.current_task_id,
            "current_iteration": state.current_iteration,
            "max_iterations": state.max_iterations,
            "created_at": _serialize_datetime(state.created_at),
            "started_at": _serialize_datetime(state.started_at),
            "last_updated": _serialize_datetime(state.last_updated),
            "metadata": state.metadata,
        }

    @staticmethod
    def deserialize_runtime_state(data: Dict[str, Any]) -> RuntimeState:
        from .types import LoopStatus
        state = RuntimeState(
            runtime_id=data.get("runtime_id", str(uuid.uuid4())[:8]),
            trace_id=data.get("trace_id"),
            schema_version=data.get("schema_version", "1.0.0"),
        )

        status_name = data.get("status", "PENDING")
        try:
            state.status = LoopStatus[status_name]
        except (KeyError, TypeError):
            pass

        current_phase = data.get("current_phase")
        if current_phase:
            state.current_phase = RuntimePhase(current_phase)

        ledger_data = data.get("task_ledger", {})
        state.task_ledger = StateSerializer.deserialize_task_ledger(ledger_data)

        state.current_task_id = data.get("current_task_id")
        state.current_iteration = data.get("current_iteration", 0)
        state.max_iterations = data.get("max_iterations", 100)
        state.created_at = _deserialize_datetime(data.get("created_at")) or datetime.now()
        state.started_at = _deserialize_datetime(data.get("started_at"))
        state.last_updated = _deserialize_datetime(data.get("last_updated")) or datetime.now()
        state.metadata = data.get("metadata", {})

        return state


class PersistenceBackend(ABC):
    """Abstract base class for persistence backends."""

    @abstractmethod
    def save(self, state: RuntimeState, trace_id: str) -> Path:
        pass

    @abstractmethod
    def load(self, trace_id: str) -> Optional[RuntimeState]:
        pass

    @abstractmethod
    def load_latest(self) -> Optional[RuntimeState]:
        pass

    @abstractmethod
    def list_saved_states(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete(self, trace_id: str) -> None:
        pass


class JSONPersistenceBackend(PersistenceBackend):
    """JSON-based persistence backend."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._serializer = StateSerializer()

    def save(self, state: RuntimeState, trace_id: str) -> Path:
        filepath = self.state_dir / f"runtime_state_{trace_id}.json"
        data = self._serializer.serialize_runtime_state(state)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return filepath

    def load(self, trace_id: str) -> Optional[RuntimeState]:
        filepath = self.state_dir / f"runtime_state_{trace_id}.json"
        if not filepath.exists():
            return None
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return self._serializer.deserialize_runtime_state(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def load_latest(self) -> Optional[RuntimeState]:
        state_files = sorted(
            self.state_dir.glob("runtime_state_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        if not state_files:
            return None
        try:
            with open(state_files[0], 'r') as f:
                data = json.load(f)
            return self._serializer.deserialize_runtime_state(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_saved_states(self) -> List[Dict[str, Any]]:
        states = []
        for filepath in self.state_dir.glob("runtime_state_*.json"):
            stat = filepath.stat()
            states.append({
                "trace_id": filepath.stem.replace("runtime_state_", ""),
                "filepath": str(filepath),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": stat.st_size,
                "format": "json",
            })
        return sorted(states, key=lambda x: x["modified"], reverse=True)

    def delete(self, trace_id: str) -> None:
        filepath = self.state_dir / f"runtime_state_{trace_id}.json"
        filepath.unlink(missing_ok=True)


class SQLitePersistenceBackend(PersistenceBackend):
    """SQLite-backed state persistence with one atomic record per trace."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.state_dir / "runtime_state.db"
        self._serializer = StateSerializer()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_states (
                    trace_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def save(self, state: RuntimeState, trace_id: str) -> Path:
        payload = json.dumps(
            self._serializer.serialize_runtime_state(state),
            default=str,
        )
        updated_at = datetime.now().isoformat()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO runtime_states(trace_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(trace_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (trace_id, payload, updated_at),
            )
            connection.commit()
        return self.database_path

    def load(self, trace_id: str) -> Optional[RuntimeState]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM runtime_states WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return self._serializer.deserialize_runtime_state(json.loads(row[0]))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def load_latest(self) -> Optional[RuntimeState]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM runtime_states ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        try:
            return self._serializer.deserialize_runtime_state(json.loads(row[0]))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            return None

    def list_saved_states(self) -> List[Dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT trace_id, updated_at, length(payload)
                FROM runtime_states
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            {
                "trace_id": trace_id,
                "filepath": str(self.database_path),
                "modified": updated_at,
                "size_bytes": payload_size,
                "format": "sqlite",
            }
            for trace_id, updated_at, payload_size in rows
        ]

    def delete(self, trace_id: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                "DELETE FROM runtime_states WHERE trace_id = ?",
                (trace_id,),
            )
            connection.commit()


@dataclass
class RuntimePersistenceConfig:
    """Configuration for runtime state persistence."""
    state_dir: Path = field(default_factory=lambda: Path(".loop_state"))
    backend: str = "json"
    auto_save: bool = True
    save_interval_seconds: int = 30
    max_history: int = 10
    verify_on_save: bool = True


class RuntimeStatePersistence:
    """Real state persistence for Loop Runtime V1."""

    def __init__(self, config: Optional[RuntimePersistenceConfig] = None):
        self.config = config or RuntimePersistenceConfig()
        self.config.state_dir.mkdir(parents=True, exist_ok=True)

        backend = self.config.backend.lower()
        if backend == "json":
            self._backend: PersistenceBackend = JSONPersistenceBackend(
                self.config.state_dir
            )
        elif backend == "sqlite":
            self._backend = SQLitePersistenceBackend(self.config.state_dir)
        else:
            raise ValueError(
                f"Unsupported persistence backend: {self.config.backend!r}. "
                "Choose 'json' or 'sqlite'."
            )
        self.config.backend = backend

        self._last_save_time: Optional[datetime] = None
        self._save_count: int = 0

    def save(self, state: RuntimeState, trace_id: Optional[str] = None) -> Optional[Path]:
        if trace_id is None:
            trace_id = state.trace_id or state.runtime_id

        try:
            state.last_updated = datetime.now()
            path = self._backend.save(state, trace_id)

            if self.config.verify_on_save:
                reloaded = self._backend.load(trace_id)
                if reloaded is None:
                    return None

            self._last_save_time = datetime.now()
            self._save_count += 1

            self._cleanup_old_states()

            return path
        except Exception:
            return None

    def load(self, trace_id: str) -> Optional[RuntimeState]:
        try:
            return self._backend.load(trace_id)
        except Exception:
            return None

    def load_latest(self) -> Optional[RuntimeState]:
        try:
            return self._backend.load_latest()
        except Exception:
            return None

    def list_saved_states(self) -> List[Dict[str, Any]]:
        return self._backend.list_saved_states()

    def should_auto_save(self, state: RuntimeState) -> bool:
        if not self.config.auto_save:
            return False
        if self._last_save_time is None:
            return True
        elapsed = (datetime.now() - self._last_save_time).total_seconds()
        return elapsed >= self.config.save_interval_seconds

    def get_stats(self) -> Dict[str, Any]:
        return {
            "save_count": self._save_count,
            "last_save_time": _serialize_datetime(self._last_save_time),
            "backend": self.config.backend,
            "state_dir": str(self.config.state_dir),
        }

    def _cleanup_old_states(self) -> None:
        states = self._backend.list_saved_states()
        for old_state in states[self.config.max_history:]:
            self._backend.delete(old_state["trace_id"])


__all__ = [
    "RuntimePersistenceConfig",
    "RuntimeStatePersistence",
    "StateSerializer",
    "JSONPersistenceBackend",
    "SQLitePersistenceBackend",
]
