---
name: stablemate-workhorse-scripting
description: "Workhorse workflow scripting — JSON output protocol, shared lib import, workspace resolution, WorkflowRun test API. Applies to scripts/**/*.py."
metadata:
  generated_by: farrier
  source: library/skills/python/workhorse-scripting/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
---

# Workhorse Scripting

Patterns for Python scripts executed as `script:` nodes in a workhorse `workflow.yaml`.

---

## Output protocol

Script **stdout must be valid JSON** containing all keys declared in the node's `outputs:` list. Workhorse extracts them after the process exits — stdout is not streamed.

```python
import json

def main() -> None:
    ...
    # Always the last stdout line
    print(json.dumps({
        "status": "valid",
        "errors": [],
    }))
```

Stderr is for logging only. Workhorse surfaces it in the error message when exit code != 0.

## Logging — stdlib, no module-level globals

```python
import logging
import sys

logger = logging.getLogger(__name__)

def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(name)s %(levelname)s: %(message)s",
    )
    logger.info("Starting with spec_dir=%s", spec_dir)
    logger.warning("Skipping %s: no agents.yml", repo_name)
```

`__name__` is the script module name — automatic, stateless, no `set_script_name()` needed.

## Shared lib pattern

Scripts in the same workflow share a `lib/` directory via `sys.path.insert`:

```python
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))

from workspace import resolve_workspace, load_json, load_jsonc
```

Public exports from `lib/` use **no underscore prefix** — underscore means private to the module. `load_jsonc` not `_load_jsonc`.

## JSONC parsing

VSCode workspace files use JSON with Comments (trailing commas, `//` comments). Parse them with `load_jsonc()` from the shared lib — never standard `json.loads()` directly.

Output is always strict JSON — only input (workspace files) may be JSONC.

## Workspace resolution

Scripts resolve multi-repo context via `resolve_workspace()`:

```python
from workspace import resolve_workspace

repos = resolve_workspace()
# {repo_name: {"path": "/abs/path", "qa_mode": "cli", "verification": "...", ...}}
```

Resolution order:
1. Read the `CODER_WORKSPACE` env var → its value is the VSCode workspace file path
2. If unset or file missing → CWD is the single-folder workspace (mono-repo fallback)

The planner selects which repos are relevant — scripts iterate only repos listed in `plan-context.json`, not all workspace folders.

## Working directory

Workhorse sets `cwd` per node. Scripts **must respect the effective CWD** — do not assume the workflow directory or repo root. Use `AGENT_REPO_DIR` env var when you need the workflow's repo root:

```python
env_root = os.environ.get("AGENT_REPO_DIR")
root = Path(env_root).resolve() if env_root else Path.cwd().resolve()
```

## Arguments

Workhorse renders args via Jinja2 before passing them as `sys.argv[1:]`:

```yaml
# workflow.yaml
args:
  - "{{ spec_dir }}"
  - "{{ current_layer_index }}"
```

```python
spec_dir_rel = sys.argv[1] if len(sys.argv) > 1 else ""
current_index = int(sys.argv[2]) if len(sys.argv) > 2 else -1
```

## Exit codes

| Code | Meaning in workhorse |
|------|---------------------|
| 0 | Success — outputs extracted from stdout |
| 1 | `ScriptExitError` raised, stderr shown in error |
| 2 | Special: "operator input required" (`await_operator` pattern) |

Use `raise SystemExit(code)` — never `sys.exit()` in library code.

## Git operations — GitPython, not subprocess

```python
from git import Repo, InvalidGitRepositoryError

repo = Repo(str(repo_path))

# Branch
if f"story/{slug}" not in [h.name for h in repo.heads]:
    repo.git.checkout("-b", f"story/{slug}")
else:
    repo.git.checkout(f"story/{slug}")

# Commit
if repo.is_dirty(untracked_files=True):
    repo.git.add("-A")
    repo.index.commit(f"{epic}: {slug}" if epic else slug)

# Push
repo.remote("origin").push()
```

For `gh` CLI operations (no Python library exists): `subprocess.run(["gh", "pr", "create", ...])` is the acceptable exception.

## Testing workflow scripts

**Unit test (direct subprocess)** — for scripts that run standalone:

```python
import json, os, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

def test_my_script(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "my-script.py"), "specs"],
        capture_output=True, text=True, cwd=str(tmp_path),
        env={**os.environ, "AGENT_REPO_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "valid"
```

**Integration test (WorkflowRun)** — for scripts wired into workflow nodes:

```python
from workhorse.testing import WorkflowRun, assert_step_output

def test_validate_gate_rejects(story_sandbox):
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_command("git", {"rev-parse": (0, "main")})
    result = wf.run(flow="dev", params={...})
    assert_step_output(result, "validate_plan", "validation_result", {"status": "invalid"})
```

Key `WorkflowRun` methods:

| Method | Purpose |
|--------|---------|
| `mock_agent(node_id, response)` | Return fixed JSON from an agent node |
| `mock_agent_sequence(node_id, responses)` | Multiple responses for rework loops |
| `mock_command(name, response)` | Install PATH shim (git, gh, etc.) |
| `run(params, flow)` | Execute workflow as subprocess, return `RunResult` |
| `result.step_outputs(node_id)` | Parsed `output.json` for a node |
| `result.prompt(node_id)` | Rendered prompt sent to agent |
| `result.context()` | Final workflow context dict |
| `result.calls(command)` | Recorded shim invocations |
