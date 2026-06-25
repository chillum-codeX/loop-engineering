"""
State Persistence Module

Based on Anthropic's Loop Engineering paper (Section VI.B):
- The Amnesiac Loop anti-pattern: loop discovers work, does it, then forgets
- The fix: state file on disk - the agent forgets, the repo does not
- Memory persists across rounds and days

State file format (markdown for human readability):
```markdown
# Loop State: {trace_id}

## Current Plan
| Step | Status | Output |
|------|--------|--------|
...

## Failures
| ID | Type | Status | Attempts |
|----|------|--------|----------|
...

## Completed Work
...
```
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from .types import (
    ExecutionState,
    Failure,
    FailureStatus,
    LoopStatus,
    Plan,
    RecoveryAction,
    Step,
    StepStatus,
)

if TYPE_CHECKING:
    from .core import LoopState


@dataclass
class PersistenceConfig:
    """Configuration for state persistence."""
    state_dir: Path = field(default_factory=lambda: Path(".loop_state"))
    format: str = "markdown"  # "markdown" or "json"
    auto_save: bool = True
    save_interval: int = 1  # Save every N iterations
    max_history: int = 10  # Keep last N state files


class LoopStatePersistence:
    """
    Persist loop state to disk for cross-run memory.

    Following the paper: "the agent forgets, the repo does not"
    """

    def __init__(self, config: Optional[PersistenceConfig] = None):
        self.config = config or PersistenceConfig()
        self.config.state_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: "LoopState", trace_id: Optional[str] = None) -> Path:
        """
        Save state to disk.

        Args:
            state: Current loop state
            trace_id: Optional trace identifier (defaults to timestamp)

        Returns:
            Path to saved state file
        """
        if trace_id is None:
            trace_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        filepath = self.config.state_dir / f"loop_state_{trace_id}.md"

        if self.config.format == "markdown":
            content = self._to_markdown(state, trace_id)
        else:
            content = self._to_json(state, trace_id)

        filepath.write_text(content)

        # Cleanup old states
        self._cleanup_old_states()

        return filepath

    def load(self, trace_id: str) -> Optional["LoopState"]:
        """Load state from disk."""
        filepath = self.config.state_dir / f"loop_state_{trace_id}.md"

        if not filepath.exists():
            # Try JSON fallback
            filepath = self.config.state_dir / f"loop_state_{trace_id}.json"
            if not filepath.exists():
                return None

        content = filepath.read_text()

        if filepath.suffix == ".json":
            return self._from_json(content)
        else:
            return self._from_markdown(content)

    def load_latest(self) -> Optional["LoopState"]:
        """Load the most recent state file."""
        state_files = sorted(
            self.config.state_dir.glob("loop_state_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not state_files:
            # Try JSON
            state_files = sorted(
                self.config.state_dir.glob("loop_state_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

        if not state_files:
            return None

        content = state_files[0].read_text()
        if state_files[0].suffix == ".json":
            return self._from_json(content)
        else:
            return self._from_markdown(content)

    def merge_with_current(self, saved: "LoopState", current: "LoopState") -> "LoopState":
        """
        Merge persisted state with current execution.

        Strategy:
        1. Keep current plan if it exists, otherwise use saved
        2. Merge failure lists (deduplicate by ID)
        3. Merge recovery actions (deduplicate by ID)
        4. Use higher iteration count
        5. Preserve current execution state
        """
        # Start with current state
        merged = current

        # Use saved plan if current has none
        if not merged.current_plan and saved.current_plan:
            merged.current_plan = saved.current_plan

        # Merge failures (deduplicate)
        existing_ids = {f.failure_id for f in merged.failures}
        for failure in saved.failures:
            if failure.failure_id not in existing_ids:
                merged.failures.append(failure)

        # Merge recoveries (deduplicate)
        existing_ids = {r.action_id for r in merged.recoveries}
        for recovery in saved.recoveries:
            if recovery.action_id not in existing_ids:
                merged.recoveries.append(recovery)

        # Use max iteration
        merged.current_iteration = max(
            merged.current_iteration,
            saved.current_iteration
        )

        return merged

    def list_saved_states(self) -> List[Dict[str, Any]]:
        """List all saved states with metadata."""
        states = []

        for filepath in self.config.state_dir.glob("loop_state_*.md"):
            stat = filepath.stat()
            states.append({
                "trace_id": filepath.stem.replace("loop_state_", ""),
                "filepath": str(filepath),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "size_bytes": stat.st_size,
                "format": "markdown",
            })

        return sorted(states, key=lambda x: x["modified"], reverse=True)

    def _to_markdown(self, state: "LoopState", trace_id: str) -> str:
        """Convert state to markdown format."""
        lines = [
            f"# Loop State: {trace_id}",
            "",
            f"**Saved:** {datetime.now().isoformat()}",
            f"**Status:** {state.status.name}",
            f"**Execution State:** {state.execution_state.value}",
            f"**Iteration:** {state.current_iteration}",
            "",
            "## Summary",
            "",
            f"- **Observations:** {len(state.observations)}",
            f"- **Evaluations:** {len(state.evaluations)}",
            f"- **Failures:** {len(state.failures)}",
            f"- **Recoveries:** {len(state.recoveries)}",
            "",
        ]

        # Current Plan
        if state.current_plan:
            lines.extend([
                "## Current Plan",
                "",
                f"**Goal:** {state.current_plan.goal}",
                f"**Version:** {state.current_plan.version}",
                "",
                "| Step | Status | Description |",
                "|------|--------|-------------|",
            ])
            for step in state.current_plan.steps:
                status_emoji = self._status_emoji(step.status)
                desc = step.description[:40] + "..." if len(step.description) > 40 else step.description
                lines.append(f"| {step.id} | {status_emoji} {step.status.value} | {desc} |")
            lines.append("")

        # Failures
        if state.failures:
            lines.extend([
                "## Failures",
                "",
                "| ID | Type | Status | Attempts | Message |",
                "|----|------|--------|----------|---------|",
            ])
            for failure in state.failures:
                msg = failure.message[:30] + "..." if len(failure.message) > 30 else failure.message
                lines.append(
                    f"| {failure.failure_id} | {failure.type.value} | "
                    f"{failure.status.value} | {failure.recovery_attempts} | {msg} |"
                )
            lines.append("")

        # Recoveries
        if state.recoveries:
            lines.extend([
                "## Recovery Actions",
                "",
                "| ID | Strategy | Success | Failure ID |",
                "|----|----------|---------|------------|",
            ])
            for recovery in state.recoveries:
                success = "✅" if recovery.success else "❌" if recovery.success is False else "⏳"
                lines.append(
                    f"| {recovery.action_id} | {recovery.strategy.value} | "
                    f"{success} | {recovery.failure_id or '-'} |"
                )
            lines.append("")

        # Component Call Counters
        lines.extend([
            "## Component Calls",
            "",
            "| Component | Calls |",
            "|-----------|-------|",
        ])
        counters = state.counters.to_dict()
        for component, count in counters.items():
            if count > 0:
                lines.append(f"| {component} | {count} |")
        lines.append("")

        # Completed Work Summary
        if state.current_plan:
            completed = sum(1 for s in state.current_plan.steps if s.is_completed())
            total = len(state.current_plan.steps)
            progress = (completed / total * 100) if total > 0 else 0
            lines.extend([
                "## Progress",
                "",
                f"**Completed:** {completed}/{total} steps ({progress:.1f}%)",
                "",
            ])

        # Metadata
        if state.metadata:
            lines.extend([
                "## Metadata",
                "",
                "```json",
                json.dumps(state.metadata, indent=2, default=str),
                "```",
                "",
            ])

        return "\n".join(lines)

    def _from_markdown(self, content: str) -> "LoopState":
        """Parse state from markdown format."""
        from .core import LoopState
        state = LoopState()

        # Extract basic info
        status_match = re.search(r'\*\*Status:\*\* (\w+)', content)
        if status_match:
            try:
                state.status = LoopStatus[status_match.group(1).upper()]
            except KeyError:
                pass

        exec_match = re.search(r'\*\*Execution State:\*\* (\w+)', content)
        if exec_match:
            try:
                state.execution_state = ExecutionState(exec_match.group(1).lower())
            except ValueError:
                pass

        iter_match = re.search(r'\*\*Iteration:\*\* (\d+)', content)
        if iter_match:
            state.current_iteration = int(iter_match.group(1))

        # Note: Full plan reconstruction from markdown is complex
        # This is a simplified version - for full reconstruction use JSON

        return state

    def _to_json(self, state: "LoopState", trace_id: str) -> str:
        """Convert state to JSON format (more complete)."""
        data = {
            "trace_id": trace_id,
            "saved_at": datetime.now().isoformat(),
            "state": {
                "status": state.status.name,
                "execution_state": state.execution_state.value,
                "current_iteration": state.current_iteration,
                "current_plan": self._plan_to_dict(state.current_plan) if state.current_plan else None,
                "observations": len(state.observations),
                "evaluations": len(state.evaluations),
                "failures": [self._failure_to_dict(f) for f in state.failures],
                "recoveries": [self._recovery_to_dict(r) for r in state.recoveries],
                "counters": state.counters.to_dict(),
                "metadata": state.metadata,
            }
        }
        return json.dumps(data, indent=2, default=str)

    def _from_json(self, content: str) -> "LoopState":
        """Parse state from JSON format."""
        from .core import LoopState
        data = json.loads(content)
        state_data = data.get("state", {})

        state = LoopState()

        if "status" in state_data:
            try:
                state.status = LoopStatus[state_data["status"].upper()]
            except KeyError:
                pass

        if "execution_state" in state_data:
            try:
                state.execution_state = ExecutionState(state_data["execution_state"])
            except ValueError:
                pass

        state.current_iteration = state_data.get("current_iteration", 0)
        state.metadata = state_data.get("metadata", {})

        # Restore counters
        counters = state_data.get("counters", {})
        for key, value in counters.items():
            if hasattr(state.counters, key):
                setattr(state.counters, key, value)

        # Note: Full plan/failure/recovery reconstruction would require
        # more complete serialization - this is a simplified version

        return state

    def _plan_to_dict(self, plan: Plan) -> Dict[str, Any]:
        """Convert plan to dictionary."""
        return {
            "id": plan.id,
            "goal": plan.goal,
            "version": plan.version,
            "steps": [
                {
                    "id": step.id,
                    "description": step.description,
                    "status": step.status.value,
                    "evaluation_passed": step.evaluation_passed,
                    "verification_passed": step.verification_passed,
                }
                for step in plan.steps
            ],
        }

    def _failure_to_dict(self, failure: Failure) -> Dict[str, Any]:
        """Convert failure to dictionary."""
        return {
            "failure_id": failure.failure_id,
            "type": failure.type.value,
            "message": failure.message,
            "step_id": failure.step_id,
            "status": failure.status.value,
            "recoverable": failure.recoverable,
            "recovery_attempts": failure.recovery_attempts,
            "max_recovery_attempts": failure.max_recovery_attempts,
        }

    def _recovery_to_dict(self, recovery: RecoveryAction) -> Dict[str, Any]:
        """Convert recovery to dictionary."""
        return {
            "action_id": recovery.action_id,
            "strategy": recovery.strategy.value,
            "failure_id": recovery.failure_id,
            "executed": recovery.executed,
            "success": recovery.success,
        }

    def _cleanup_old_states(self) -> None:
        """Remove old state files keeping only max_history."""
        state_files = sorted(
            self.config.state_dir.glob("loop_state_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for old_file in state_files[self.config.max_history:]:
            old_file.unlink()

    @staticmethod
    def _status_emoji(status: StepStatus) -> str:
        """Get emoji for step status."""
        emoji_map = {
            StepStatus.PENDING: "⏳",
            StepStatus.READY: "📝",
            StepStatus.IN_PROGRESS: "🔄",
            StepStatus.EXECUTED: "✓",
            StepStatus.EVALUATED: "👁",
            StepStatus.EVALUATION_FAILED: "❌",
            StepStatus.VERIFICATION_FAILED: "🚫",
            StepStatus.VERIFIED_COMPLETED: "✅",
            StepStatus.RECOVERY_PENDING: "🔄",
            StepStatus.RETRY_PENDING: "🔄",
            StepStatus.SKIPPED: "⏭",
            StepStatus.FAILED: "💥",
            StepStatus.CANCELLED: "🚫",
        }
        return emoji_map.get(status, "❓")
