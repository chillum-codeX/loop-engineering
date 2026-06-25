"""
Worktree Isolation Module

Based on Anthropic's Loop Engineering paper (Section IV):
- "Handoff moves the task into the hands of the agent"
- "Each finding worth doing gets its own isolated git worktree"
- "Multiple agents change code in separate directories without stepping on each other"
- "Worktrees turn parallelism from 'runs but messy' into 'runs and clean'"

Also from Stripe's Minions (Section VII.B):
- "Each environment is swapped out at will"
- "A thousand-plus agents run at once without stepping on each other"
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import uuid


@dataclass
class Worktree:
    """
    Represents an isolated git worktree.

    Each agent gets its own worktree to prevent conflicts during
    parallel execution.
    """
    task_id: str
    path: Path
    branch: str
    base_dir: Path
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "path": str(self.path),
            "branch": self.branch,
            "base_dir": str(self.base_dir),
            "created_at": self.created_at,
        }


@dataclass
class MergeResult:
    """Result of merging worktrees."""
    success: bool
    merged_worktrees: List[str]
    conflicts: List[str]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "merged_worktrees": self.merged_worktrees,
            "conflicts": self.conflicts,
            "message": self.message,
        }


class WorktreeManager:
    """
    Manage isolated working directories for parallel agents.

    Uses git worktrees to create isolated environments where multiple
    agents can work simultaneously without conflicts.
    """

    def __init__(
        self,
        base_repo: Path,
        worktrees_dir: Optional[Path] = None,
        main_branch: str = "main",
    ):
        """
        Initialize worktree manager.

        Args:
            base_repo: Path to the base git repository
            worktrees_dir: Directory to create worktrees in (default: base_repo/.worktrees)
            main_branch: Main branch to base worktrees on
        """
        self.base_repo = Path(base_repo).resolve()
        self.worktrees_dir = worktrees_dir or self.base_repo / ".worktrees"
        self.main_branch = main_branch
        self._worktrees: Dict[str, Worktree] = {}

        # Ensure worktrees directory exists
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

    def create_worktree(
        self,
        task_id: Optional[str] = None,
        branch_prefix: str = "agent",
    ) -> Worktree:
        """
        Create isolated git worktree for a task.

        Args:
            task_id: Unique task identifier (generated if not provided)
            branch_prefix: Prefix for the git branch name

        Returns:
            Worktree object representing the isolated directory
        """
        if task_id is None:
            task_id = str(uuid.uuid4())[:8]

        # Check if already exists
        if task_id in self._worktrees:
            return self._worktrees[task_id]

        branch = f"{branch_prefix}/{task_id}"
        worktree_path = self.worktrees_dir / task_id

        try:
            # Create new branch from main
            subprocess.run(
                ["git", "checkout", "-b", branch],
                cwd=self.base_repo,
                check=True,
                capture_output=True,
            )

            # Create worktree
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch],
                cwd=self.base_repo,
                check=True,
                capture_output=True,
            )

            worktree = Worktree(
                task_id=task_id,
                path=worktree_path,
                branch=branch,
                base_dir=self.base_repo,
            )

            self._worktrees[task_id] = worktree
            return worktree

        except subprocess.CalledProcessError as e:
            # Cleanup on failure
            self._cleanup_failed_creation(branch, worktree_path)
            raise RuntimeError(f"Failed to create worktree: {e.stderr.decode()}")

    def _cleanup_failed_creation(self, branch: str, path: Path) -> None:
        """Cleanup after failed worktree creation."""
        try:
            # Remove branch if created
            subprocess.run(
                ["git", "branch", "-D", branch],
                cwd=self.base_repo,
                capture_output=True,
            )
        except:
            pass

        # Remove directory if created
        if path.exists():
            shutil.rmtree(path)

    def cleanup_worktree(self, task_id: str, keep_branch: bool = False) -> bool:
        """
        Remove worktree after completion.

        Args:
            task_id: Task identifier
            keep_branch: If True, keep the git branch (for manual review)

        Returns:
            True if cleanup succeeded
        """
        if task_id not in self._worktrees:
            return False

        worktree = self._worktrees[task_id]

        try:
            # Remove worktree
            subprocess.run(
                ["git", "worktree", "remove", str(worktree.path)],
                cwd=self.base_repo,
                check=True,
                capture_output=True,
            )

            # Remove branch unless keeping
            if not keep_branch:
                subprocess.run(
                    ["git", "branch", "-D", worktree.branch],
                    cwd=self.base_repo,
                    check=True,
                    capture_output=True,
                )

            # Clean up directory if still exists
            if worktree.path.exists():
                shutil.rmtree(worktree.path)

            del self._worktrees[task_id]
            return True

        except subprocess.CalledProcessError:
            return False

    def merge_worktree(self, task_id: str, squash: bool = False) -> MergeResult:
        """
        Merge a worktree back to main branch.

        Args:
            task_id: Task identifier
            squash: If True, squash commits into one

        Returns:
            MergeResult with success status and any conflicts
        """
        if task_id not in self._worktrees:
            return MergeResult(
                success=False,
                merged_worktrees=[],
                conflicts=[],
                message=f"Worktree {task_id} not found",
            )

        worktree = self._worktrees[task_id]

        try:
            # Checkout main
            subprocess.run(
                ["git", "checkout", self.main_branch],
                cwd=self.base_repo,
                check=True,
                capture_output=True,
            )

            # Merge
            merge_cmd = ["git", "merge"]
            if squash:
                merge_cmd.append("--squash")
            merge_cmd.append(worktree.branch)

            result = subprocess.run(
                merge_cmd,
                cwd=self.base_repo,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Clean up after successful merge
                self.cleanup_worktree(task_id, keep_branch=False)

                return MergeResult(
                    success=True,
                    merged_worktrees=[task_id],
                    conflicts=[],
                    message=f"Successfully merged {task_id}",
                )
            else:
                # Check for conflicts
                if "conflict" in result.stderr.lower():
                    return MergeResult(
                        success=False,
                        merged_worktrees=[],
                        conflicts=self._get_conflict_files(),
                        message=f"Merge conflicts in {task_id}: {result.stderr}",
                    )
                else:
                    return MergeResult(
                        success=False,
                        merged_worktrees=[],
                        conflicts=[],
                        message=f"Merge failed: {result.stderr}",
                    )

        except subprocess.CalledProcessError as e:
            return MergeResult(
                success=False,
                merged_worktrees=[],
                conflicts=[],
                message=f"Merge error: {e}",
            )

    def merge_results(self, task_ids: Optional[List[str]] = None) -> MergeResult:
        """
        Merge results from multiple worktrees.

        Args:
            task_ids: List of task IDs to merge (None = all)

        Returns:
            MergeResult with combined status
        """
        if task_ids is None:
            task_ids = list(self._worktrees.keys())

        merged = []
        conflicts = []
        messages = []

        for task_id in task_ids:
            result = self.merge_worktree(task_id)
            if result.success:
                merged.append(task_id)
            else:
                conflicts.extend(result.conflicts)
            messages.append(result.message)

        return MergeResult(
            success=len(conflicts) == 0,
            merged_worktrees=merged,
            conflicts=conflicts,
            message="; ".join(messages),
        )

    def get_worktree(self, task_id: str) -> Optional[Worktree]:
        """Get worktree by task ID."""
        return self._worktrees.get(task_id)

    def list_worktrees(self) -> List[Worktree]:
        """List all active worktrees."""
        return list(self._worktrees.values())

    def is_clean(self, task_id: str) -> bool:
        """Check if worktree has uncommitted changes."""
        if task_id not in self._worktrees:
            return False

        worktree = self._worktrees[task_id]

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree.path,
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and not result.stdout.strip()
        except:
            return False

    def commit_changes(
        self,
        task_id: str,
        message: str,
        author: Optional[str] = None,
    ) -> bool:
        """
        Commit changes in a worktree.

        Args:
            task_id: Task identifier
            message: Commit message
            author: Optional author (Name <email>)

        Returns:
            True if commit succeeded
        """
        if task_id not in self._worktrees:
            return False

        worktree = self._worktrees[task_id]

        try:
            # Add all changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=worktree.path,
                check=True,
                capture_output=True,
            )

            # Commit
            cmd = ["git", "commit", "-m", message]
            if author:
                cmd.extend(["--author", author])

            subprocess.run(
                cmd,
                cwd=worktree.path,
                check=True,
                capture_output=True,
            )

            return True

        except subprocess.CalledProcessError:
            return False

    def _get_conflict_files(self) -> List[str]:
        """Get list of files with conflicts."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=self.base_repo,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return [f.strip() for f in result.stdout.split('\n') if f.strip()]
            return []
        except:
            return []

    def cleanup_all(self, keep_branches: bool = False) -> None:
        """Clean up all worktrees."""
        for task_id in list(self._worktrees.keys()):
            self.cleanup_worktree(task_id, keep_branch=keep_branches)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup all worktrees."""
        self.cleanup_all()
        return False
