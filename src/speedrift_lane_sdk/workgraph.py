# ABOUTME: Unified Workgraph helper supporting both lazy (subprocess) and eager (dict) patterns.
# ABOUTME: Provides find_workgraph_dir() for discovery and load_workgraph() for eager initialization.

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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
    ) -> bool:
        """Idempotent task creation. Returns True if created, False if existed.

        Eager mode checks ``self.tasks`` dict; lazy mode calls ``show_task()``.
        """
        # --- idempotency check ---
        if self.tasks is not None:
            if task_id in self.tasks:
                return False
        else:
            if self.show_task(task_id) is not None:
                return False

        # --- create via wg add ---
        cmd = ["wg", "--dir", str(self.wg_dir), "add", title, "--id", task_id]
        if description:
            cmd += ["-d", description]
        if blocked_by:
            cmd += ["--blocked-by", *blocked_by]
        if tags:
            for t in tags:
                cmd += ["-t", t]
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
    """Locate the .workgraph directory.

    ``explicit`` may be either a project root or the .workgraph directory itself.
    When None, walks up from cwd looking for .workgraph/graph.jsonl.
    """
    if explicit:
        p = explicit
        if p.name != ".workgraph":
            p = p / ".workgraph"
        if not (p / "graph.jsonl").exists():
            raise FileNotFoundError(f"Workgraph not found at: {p}")
        return p

    cur = Path.cwd()
    for p in [cur, *cur.parents]:
        candidate = p / ".workgraph" / "graph.jsonl"
        if candidate.exists():
            return candidate.parent
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
