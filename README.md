# speedrift-lane-sdk

Shared workgraph helpers and lane contract types for Speedrift drift lanes.

## Ecosystem Map

This project is part of the Speedrift suite for Workgraph-first drift control.

- Spine: [Workgraph](https://graphwork.github.io/)
- Orchestrator: [driftdriver](https://github.com/dbmcco/driftdriver)
- Baseline lane: [coredrift](https://github.com/dbmcco/coredrift)
- Optional lanes: [specdrift](https://github.com/dbmcco/specdrift), [datadrift](https://github.com/dbmcco/datadrift), [depsdrift](https://github.com/dbmcco/depsdrift), [uxdrift](https://github.com/dbmcco/uxdrift), [therapydrift](https://github.com/dbmcco/therapydrift), [fixdrift](https://github.com/dbmcco/fixdrift), [yagnidrift](https://github.com/dbmcco/yagnidrift), [redrift](https://github.com/dbmcco/redrift)

## Installation

```bash
pip install git+https://github.com/dbmcco/speedrift-lane-sdk.git
```

## Quick Start

### Lane Output

```python
from speedrift_lane_sdk import LaneFinding, LaneResult, validate_lane_output, ExitCode
import json

# Build structured lane output
findings = [
    LaneFinding(message="Missing test coverage", severity="warning", file="src/app.py", line=42, tags=["coverage"]),
    LaneFinding(message="Scope creep detected", severity="error", file="task.md", tags=["scope"]),
]

result = LaneResult(
    lane="yourlane",
    findings=findings,
    exit_code=ExitCode.FINDINGS if findings else ExitCode.OK,
    summary=f"{len(findings)} finding(s)",
)

# Serialize to JSON for driftdriver consumption
print(json.dumps(result.__dict__, default=lambda o: o.__dict__))
```

### Validate Lane Output

```python
from speedrift_lane_sdk import validate_lane_output

raw = '{"lane": "yourlane", "findings": [], "exit_code": 0, "summary": "Clean"}'
result = validate_lane_output(raw)
if result is None:
    print("Malformed lane output")
else:
    print(f"{result.lane}: {result.summary}")
```

### Workgraph Helpers

```python
from speedrift_lane_sdk import Workgraph, find_workgraph_dir, load_workgraph

# Discover .workgraph directory (walks up from cwd)
wg_dir = find_workgraph_dir()

# Load tasks eagerly (in-memory dict for fast idempotency checks)
wg = load_workgraph(wg_dir)

# Idempotent task creation
created = wg.ensure_task(task_id="drift-fix-123", title="Fix scope drift", tags=["drift"])

# Log to a task
wg.wg_log("drift-fix-123", "Created by yourlane")
```

## API Reference

### `speedrift_lane_sdk.lane_contract`

- **`LaneFinding`** — dataclass: `message`, `severity`, `file`, `line`, `tags`
- **`LaneResult`** — dataclass: `lane`, `findings`, `exit_code`, `summary`
- **`validate_lane_output(raw: str) -> LaneResult | None`** — parse raw JSON into a `LaneResult`, returns `None` on malformed input

### `speedrift_lane_sdk.workgraph`

- **`Workgraph`** — dataclass with lazy (subprocess) and eager (dict) idempotency patterns
  - `show_task(task_id) -> dict | None` — fetch task via `wg show --json`
  - `ensure_task(*, task_id, title, description, blocked_by, tags) -> bool` — idempotent create, returns `True` if created
  - `wg_log(task_id, message)` — append log entry via `wg log`
- **`find_workgraph_dir(explicit=None) -> Path`** — locate `.workgraph` directory (explicit path or walk up from cwd)
- **`load_tasks(wg_dir) -> dict`** — read `graph.jsonl` into a task-id dict
- **`load_workgraph(wg_dir) -> Workgraph`** — eager-load tasks and return a `Workgraph` instance

### `speedrift_lane_sdk.constants`

- **`ExitCode`** — `OK = 0`, `USAGE = 2`, `FINDINGS = 3`

## Development

```bash
uv sync
uv run pytest
```

## Agent Guidance

AI agents building or extending Speedrift drift lanes should use this SDK for consistent lane output.

### Lane Output Contract

Every drift lane must produce JSON matching the `LaneResult` schema:

```json
{
  "lane": "yourlane",
  "findings": [
    {"message": "description", "severity": "warning", "file": "path.py", "line": 42, "tags": ["tag1"]}
  ],
  "exit_code": 0,
  "summary": "Human-readable summary"
}
```

Severity levels: `info`, `warning`, `error`, `critical`.
Actionable severities (used by driftdriver attractor loop): `warning`, `error`, `critical`.

### Exit Codes

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `ExitCode.OK` | Clean — no findings |
| 2 | `ExitCode.USAGE` | CLI usage error |
| 3 | `ExitCode.FINDINGS` | Findings exist (advisory, never blocks) |

### Workgraph Integration

Use the `Workgraph` helper for idempotent task creation and logging:

```python
from speedrift_lane_sdk import Workgraph, find_workgraph_dir, load_workgraph

wg_dir = find_workgraph_dir()
wg = load_workgraph(wg_dir)
wg.ensure_task(task_id="drift-fix-123", title="Fix scope drift", tags=["drift"])
wg.wg_log("drift-fix-123", "Created by yourlane")
```

### Key Rules

- Drift is advisory — never hard-block the calling task
- Follow-up tasks should be idempotent (use deterministic IDs)
- All output must be parseable by `validate_lane_output()`
- Exit code 3 means "findings exist" not "failure"
