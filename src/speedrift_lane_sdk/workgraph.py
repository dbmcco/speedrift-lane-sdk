# ABOUTME: Unified Workgraph helper supporting both lazy (subprocess) and eager (dict) patterns.
# ABOUTME: Provides find_workgraph_dir() for discovery and load_workgraph() for eager initialization.

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAPH_DIR_NAMES = (".workgraph", ".wg")


class WorkgraphDirectoryConflictError(RuntimeError):
    """Raised when a repository has two initialized Workgraph directories."""


def _is_initialized_graph(path: Path) -> bool:
    return (path / "graph.jsonl").is_file()


@dataclass
class Workgraph:
    """Workgraph interface supporting lazy and eager idempotency patterns.

    Lazy mode (tasks=None): idempotency via subprocess ``wg show``.
    Eager mode (tasks={...}): idempotency via in-memory dict lookup.
    """

    wg_dir: Path
    project_dir: Path
    tasks: dict[str, dict[str, Any]] | None = field(default=None)

    def show_task(self, task_id: str) -> dict[str, Any] | None:
        """Fetch task JSON via ``wg show --json``. Returns None if not found."""
        try:
            out = subprocess.check_output(
                ["wg", "--dir", str(self.wg_dir), "show", task_id, "--json"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return json.loads(out)
        except subprocess.CalledProcessError:
            return None

    def ensure_task(
        self,
        *,
        task_id: str,
        title: str,
        description: str = "",
        blocked_by: list[str] | None = None,
        tags: list[str] | None = None,
        verify: str | None = None,
        exec_mode: str | None = None,
        skill: list[str] | None = None,
    ) -> bool:
        """Idempotent task creation. Returns True if created, False if existed.

        Eager mode checks ``self.tasks`` dict; lazy mode calls ``show_task()``.

        Args:
            verify: Shell command wg runs to validate task completion (``--verify``).
            exec_mode: Agent execution weight: full (default), light, bare, shell.
            skill: Routing hints passed to agency for agent selection (``--skill``).
        """
        # --- idempotency check ---
        if self.tasks is not None:
            if task_id in self.tasks:
                return False
        else:
            if self.show_task(task_id) is not None:
                return False

        # --- create via wg add ---
        # --no-place bypasses draft mode so follow-up tasks are immediately active.
        cmd = ["wg", "--dir", str(self.wg_dir), "add", title, "--id", task_id, "--no-place"]
        if description:
            cmd += ["-d", description]
        if blocked_by:
            cmd += ["--blocked-by", *blocked_by]
        if tags:
            for t in tags:
                cmd += ["-t", t]
        if verify:
            cmd += ["--verify", verify]
        if exec_mode:
            cmd += ["--exec-mode", exec_mode]
        if skill:
            for s in skill:
                cmd += ["--skill", s]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL)

        # --- keep eager dict in sync ---
        if self.tasks is not None:
            self.tasks[task_id] = {"kind": "task", "id": task_id, "title": title}

        return True

    def wg_log(self, task_id: str, message: str) -> None:
        """Append a log entry via ``wg log``."""
        subprocess.check_call(
            ["wg", "--dir", str(self.wg_dir), "log", task_id, message],
            stdout=subprocess.DEVNULL,
        )


def find_workgraph_dir(explicit: Path | None = None) -> Path:
    """Locate the active Workgraph directory (``.wg`` or legacy ``.workgraph``).

    ``explicit`` may be either a project root or a graph directory itself
    (named ``.workgraph`` or ``.wg``). When None, walks up from cwd looking
    for an initialized graph. In a hybrid repository — legacy ``.workgraph/``
    residue next to the active ``.wg/`` — only an initialized directory
    (one containing ``graph.jsonl``) resolves; two initialized directories
    raise :class:`WorkgraphDirectoryConflictError`.
    """
    if explicit:
        p = explicit
        if p.name not in GRAPH_DIR_NAMES:
            legacy = p / ".workgraph"
            current = p / ".wg"
            if _is_initialized_graph(current) and _is_initialized_graph(legacy):
                raise WorkgraphDirectoryConflictError(
                    "Two initialized Workgraph directories found: "
                    f"{legacy} and {current}. Choose one graph before continuing."
                )
            if _is_initialized_graph(current):
                return current
            p = legacy
        if not _is_initialized_graph(p):
            raise FileNotFoundError(f"Workgraph not found at: {p}")
        return p

    cur = Path.cwd()
    for base in [cur, *cur.parents]:
        current = base / ".wg"
        legacy = base / ".workgraph"
        current_init = _is_initialized_graph(current)
        legacy_init = _is_initialized_graph(legacy)
        if current_init and legacy_init:
            raise WorkgraphDirectoryConflictError(
                "Two initialized Workgraph directories found: "
                f"{legacy} and {current}. Choose one graph before continuing."
            )
        if current_init:
            return current
        if legacy_init:
            return legacy
    raise FileNotFoundError("Could not find .workgraph/graph.jsonl; pass --dir.")


def load_tasks(wg_dir: Path) -> dict[str, dict[str, Any]]:
    """Read graph.jsonl and return a dict of task-id -> task-object."""
    tasks: dict[str, dict[str, Any]] = {}
    for line in (wg_dir / "graph.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("kind") != "task":
            continue
        tid = str(obj.get("id"))
        tasks[tid] = obj
    return tasks


def load_workgraph(wg_dir: Path) -> Workgraph:
    """Read graph.jsonl and return an eager Workgraph with populated tasks dict."""
    graph_path = wg_dir / "graph.jsonl"
    tasks: dict[str, dict[str, Any]] = {}
    for line in graph_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("kind") != "task":
            continue
        tid = str(obj.get("id"))
        tasks[tid] = obj

    return Workgraph(wg_dir=wg_dir, project_dir=wg_dir.parent, tasks=tasks)
