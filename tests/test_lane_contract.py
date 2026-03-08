# ABOUTME: Tests for the lane_contract module — LaneFinding, LaneResult, validate_lane_output.
# ABOUTME: Covers dataclass defaults, full-field construction, valid/invalid JSON parsing.

from __future__ import annotations

import json

import pytest

from speedrift_lane_sdk.lane_contract import LaneFinding, LaneResult, validate_lane_output


class TestLaneFinding:
    """Tests for the LaneFinding dataclass."""

    def test_defaults(self):
        """LaneFinding with only message should use sensible defaults."""
        f = LaneFinding(message="something drifted")
        assert f.message == "something drifted"
        assert f.severity == "info"
        assert f.file == ""
        assert f.line == 0
        assert f.tags == []

    def test_all_fields_set(self):
        """LaneFinding with every field explicitly provided."""
        f = LaneFinding(
            message="unused import",
            severity="warning",
            file="src/app.py",
            line=42,
            tags=["style", "imports"],
        )
        assert f.message == "unused import"
        assert f.severity == "warning"
        assert f.file == "src/app.py"
        assert f.line == 42
        assert f.tags == ["style", "imports"]

    def test_tags_default_factory_isolation(self):
        """Each instance should get its own tags list (no shared mutable default)."""
        a = LaneFinding(message="a")
        b = LaneFinding(message="b")
        a.tags.append("mutated")
        assert b.tags == []


class TestLaneResult:
    """Tests for the LaneResult dataclass."""

    def test_basic_construction(self):
        """LaneResult holds lane name, findings list, exit_code, summary."""
        finding = LaneFinding(message="drift detected")
        result = LaneResult(
            lane="coredrift",
            findings=[finding],
            exit_code=3,
            summary="1 finding",
        )
        assert result.lane == "coredrift"
        assert len(result.findings) == 1
        assert result.findings[0].message == "drift detected"
        assert result.exit_code == 3
        assert result.summary == "1 finding"


class TestValidateLaneOutput:
    """Tests for the validate_lane_output parsing function."""

    def test_valid_json_with_findings(self):
        """Full valid JSON with findings should parse correctly."""
        raw = json.dumps({
            "lane": "specdrift",
            "findings": [
                {
                    "message": "spec mismatch",
                    "severity": "error",
                    "file": "api.yaml",
                    "line": 10,
                    "tags": ["api"],
                },
                {
                    "message": "minor note",
                },
            ],
            "exit_code": 3,
            "summary": "2 findings",
        })
        result = validate_lane_output(raw)
        assert result is not None
        assert result.lane == "specdrift"
        assert len(result.findings) == 2
        assert result.findings[0].severity == "error"
        assert result.findings[0].file == "api.yaml"
        assert result.findings[0].line == 10
        assert result.findings[0].tags == ["api"]
        # Second finding should get defaults
        assert result.findings[1].message == "minor note"
        assert result.findings[1].severity == "info"
        assert result.findings[1].file == ""
        assert result.findings[1].line == 0
        assert result.findings[1].tags == []
        assert result.exit_code == 3
        assert result.summary == "2 findings"

    def test_missing_lane_field(self):
        """JSON without 'lane' key should return None."""
        raw = json.dumps({"findings": [], "exit_code": 0})
        assert validate_lane_output(raw) is None

    def test_non_json_string(self):
        """Non-JSON string input should return None."""
        assert validate_lane_output("this is not json") is None

    def test_none_input(self):
        """None input should return None (TypeError handled)."""
        assert validate_lane_output(None) is None

    def test_empty_findings_list(self):
        """Valid JSON with empty findings list should produce a LaneResult."""
        raw = json.dumps({
            "lane": "coredrift",
            "findings": [],
            "exit_code": 0,
            "summary": "clean",
        })
        result = validate_lane_output(raw)
        assert result is not None
        assert result.lane == "coredrift"
        assert result.findings == []
        assert result.exit_code == 0
        assert result.summary == "clean"

    def test_missing_optional_fields(self):
        """JSON with only 'lane' should default exit_code=0, summary='', findings=[]."""
        raw = json.dumps({"lane": "yagnidrift"})
        result = validate_lane_output(raw)
        assert result is not None
        assert result.lane == "yagnidrift"
        assert result.findings == []
        assert result.exit_code == 0
        assert result.summary == ""
