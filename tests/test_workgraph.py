# ABOUTME: Tests for the workgraph module — Workgraph, find_workgraph_dir, load_workgraph.
# ABOUTME: Covers lazy/eager patterns, subprocess mocking, filesystem discovery, and graph.jsonl parsing.

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from speedrift_lane_sdk.workgraph import Workgraph, find_workgraph_dir, load_workgraph


# ---------------------------------------------------------------------------
# find_workgraph_dir
# ---------------------------------------------------------------------------


class TestFindWorkgraphDir:
    """Tests for locating the .workgraph directory."""

    def test_explicit_project_root(self, tmp_path: Path):
        """Passing a project root that contains .workgraph/ should return the .workgraph dir."""
        wg = tmp_path / ".workgraph"
        wg.mkdir()
        (wg / "graph.jsonl").write_text("")
        assert find_workgraph_dir(tmp_path) == wg

    def test_explicit_workgraph_path(self, tmp_path: Path):
        """Passing the .workgraph directory itself should return it directly."""
        wg = tmp_path / ".workgraph"
        wg.mkdir()
        (wg / "graph.jsonl").write_text("")
        assert find_workgraph_dir(wg) == wg

    def test_nonexistent_path_raises(self, tmp_path: Path):
        """Passing a path with no .workgraph/graph.jsonl should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            find_workgraph_dir(tmp_path / "nope")


# ---------------------------------------------------------------------------
# load_workgraph
# ---------------------------------------------------------------------------


class TestLoadWorkgraph:
    """Tests for reading graph.jsonl into an eager Workgraph."""

    def test_reads_tasks(self, tmp_path: Path):
        """Tasks in graph.jsonl should populate the tasks dict keyed by id."""
        wg_dir = tmp_path / ".workgraph"
        wg_dir.mkdir()
        lines = [
            json.dumps({"kind": "task", "id": "t1", "title": "First"}),
            json.dumps({"kind": "task", "id": "t2", "title": "Second"}),
        ]
        (wg_dir / "graph.jsonl").write_text("\n".join(lines))

        wg = load_workgraph(wg_dir)
        assert wg.tasks is not None
        assert "t1" in wg.tasks
        assert "t2" in wg.tasks
        assert wg.tasks["t1"]["title"] == "First"
        assert wg.project_dir == tmp_path

    def test_skips_non_task_entries(self, tmp_path: Path):
        """Edges and meta entries should be ignored."""
        wg_dir = tmp_path / ".workgraph"
        wg_dir.mkdir()
        lines = [
            json.dumps({"kind": "task", "id": "t1", "title": "Only task"}),
            json.dumps({"kind": "edge", "from": "t1", "to": "t2"}),
            json.dumps({"kind": "meta", "version": 1}),
        ]
        (wg_dir / "graph.jsonl").write_text("\n".join(lines))

        wg = load_workgraph(wg_dir)
        assert wg.tasks is not None
        assert len(wg.tasks) == 1
        assert "t1" in wg.tasks

    def test_empty_graph(self, tmp_path: Path):
        """An empty graph.jsonl should produce an eager Workgraph with empty tasks dict."""
        wg_dir = tmp_path / ".workgraph"
        wg_dir.mkdir()
        (wg_dir / "graph.jsonl").write_text("")

        wg = load_workgraph(wg_dir)
        assert wg.tasks is not None
        assert len(wg.tasks) == 0


# ---------------------------------------------------------------------------
# Lazy-mode Workgraph (tasks=None)
# ---------------------------------------------------------------------------


class TestLazyShowTask:
    """Tests for show_task in lazy mode (subprocess-backed)."""

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_output")
    def test_success(self, mock_check_output):
        """show_task returns parsed JSON on success."""
        mock_check_output.return_value = json.dumps({"id": "t1", "title": "Hello"})
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        result = wg.show_task("t1")
        assert result == {"id": "t1", "title": "Hello"}
        mock_check_output.assert_called_once_with(
            ["wg", "--dir", "/fake/.workgraph", "show", "t1", "--json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_output")
    def test_not_found_returns_none(self, mock_check_output):
        """show_task returns None when subprocess raises CalledProcessError."""
        mock_check_output.side_effect = subprocess.CalledProcessError(1, "wg")
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        result = wg.show_task("missing")
        assert result is None


class TestLazyEnsureTask:
    """Tests for ensure_task in lazy mode."""

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_call")
    @patch("speedrift_lane_sdk.workgraph.subprocess.check_output")
    def test_creates_when_not_found(self, mock_check_output, mock_check_call):
        """ensure_task should create the task when show_task returns None."""
        mock_check_output.side_effect = subprocess.CalledProcessError(1, "wg")
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        created = wg.ensure_task(task_id="new-1", title="New task", description="desc")
        assert created is True
        mock_check_call.assert_called_once()
        cmd = mock_check_call.call_args[0][0]
        assert "add" in cmd
        assert "new-1" in cmd
        assert "New task" in cmd

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_output")
    def test_skips_when_found(self, mock_check_output):
        """ensure_task should skip creation when show_task finds existing task."""
        mock_check_output.return_value = json.dumps({"id": "existing", "title": "X"})
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        created = wg.ensure_task(task_id="existing", title="X")
        assert created is False


# ---------------------------------------------------------------------------
# Eager-mode Workgraph (tasks={...})
# ---------------------------------------------------------------------------


class TestEagerEnsureTask:
    """Tests for ensure_task in eager mode (dict-backed)."""

    def test_skips_existing(self):
        """ensure_task returns False when task_id already in tasks dict."""
        tasks = {"t1": {"kind": "task", "id": "t1", "title": "Exists"}}
        wg = Workgraph(
            wg_dir=Path("/fake/.workgraph"),
            project_dir=Path("/fake"),
            tasks=tasks,
        )

        created = wg.ensure_task(task_id="t1", title="Exists")
        assert created is False

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_call")
    def test_creates_and_updates_dict(self, mock_check_call):
        """ensure_task creates via subprocess and updates internal tasks dict."""
        tasks: dict = {}
        wg = Workgraph(
            wg_dir=Path("/fake/.workgraph"),
            project_dir=Path("/fake"),
            tasks=tasks,
        )

        created = wg.ensure_task(task_id="new-1", title="New thing")
        assert created is True
        assert "new-1" in wg.tasks
        assert wg.tasks["new-1"]["title"] == "New thing"
        mock_check_call.assert_called_once()


# ---------------------------------------------------------------------------
# ensure_task flags (blocked_by, tags)
# ---------------------------------------------------------------------------


class TestEnsureTaskFlags:
    """Tests for ensure_task command construction with optional flags."""

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_call")
    @patch("speedrift_lane_sdk.workgraph.subprocess.check_output")
    def test_blocked_by_and_tags_in_command(self, mock_check_output, mock_check_call):
        """ensure_task should include --blocked-by and -t flags when provided."""
        mock_check_output.side_effect = subprocess.CalledProcessError(1, "wg")
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        wg.ensure_task(
            task_id="t-flags",
            title="Flagged task",
            description="with deps",
            blocked_by=["dep-1", "dep-2"],
            tags=["drift", "core"],
        )

        cmd = mock_check_call.call_args[0][0]
        assert "--blocked-by" in cmd
        bb_idx = cmd.index("--blocked-by")
        assert cmd[bb_idx + 1] == "dep-1"
        assert cmd[bb_idx + 2] == "dep-2"
        assert "-t" in cmd
        t_indices = [i for i, x in enumerate(cmd) if x == "-t"]
        assert len(t_indices) == 2
        assert cmd[t_indices[0] + 1] == "drift"
        assert cmd[t_indices[1] + 1] == "core"


# ---------------------------------------------------------------------------
# wg_log
# ---------------------------------------------------------------------------


class TestWgLog:
    """Tests for wg_log subprocess call."""

    @patch("speedrift_lane_sdk.workgraph.subprocess.check_call")
    def test_calls_correct_subprocess(self, mock_check_call):
        """wg_log should invoke 'wg log' with the correct arguments."""
        wg = Workgraph(wg_dir=Path("/fake/.workgraph"), project_dir=Path("/fake"))

        wg.wg_log("t1", "drift check passed")
        mock_check_call.assert_called_once_with(
            ["wg", "--dir", "/fake/.workgraph", "log", "t1", "drift check passed"],
            stdout=subprocess.DEVNULL,
        )
