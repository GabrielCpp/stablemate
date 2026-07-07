---
name: stablemate-workhorse-scripting
description: "Workhorse workflow scripting — JSON output protocol, shared lib import, workspace resolution, WorkflowRun test API. Applies to scripts/**/*.py."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/workhorse-scripting/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
---

# Workhorse Scripting

Patterns for Python scripts executed as `script:` nodes in a workhorse `workflow.yaml`.

---

## Separation of concerns — workhorse is generic, keep workflow logic in the workflow

Workhorse (`workhorse/**`, including `scriptutil.py`, `templates.py`, the graph engine,
and the Jinja globals it registers) is a **generic engine shared by every workflow**. It
must never learn the shape of one workflow's data.

**Do not add workflow-specific logic to workhorse.** Concretely, do not put in workhorse:
- a schema of a particular `plan-context.json` / plan_result (e.g. `services[].type`,
  `touched_layers`, layer→platform maps) — that is the coder workflow's vocabulary;
- a Jinja global that derives a workflow-specific value (e.g. `touched_layers()`); or
- branching on a specific env var name, repo name, or story convention.

**Where each thing lives:**
- **Deriving a value from the workflow's own data** → do it in the **workflow**: either in
  a workflow `script:` node (`agents/workflows/<wf>/scripts/*.py`) that reads the JSON and
  emits the derived field to context, or directly in the prompt's Jinja over the context
  data (`{% for svc in plan_result.services %}` / `| map(attribute='type') | unique`).
  Workhorse already exposes the raw context — the derivation is the workflow's job.
- **A genuinely reusable primitive** → add it to workhorse **parameterised**, with no
  knowledge of any workflow's field names. `resolve_workspace(env_key)` is the model: the
  workflow passes `"CODER_WORKSPACE"`; workhorse just reads the env var it's told to. Good
  additions are things like "read a dotted path from a JSON file", "dedup a list preserving
  order" — verbs, not nouns from a specific schema.

Litmus test before touching `workhorse/**`: *would a totally different workflow want this
unchanged?* If it only makes sense for the coder workflow, it belongs in the workflow.

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

## JSONC parsing

VSCode workspace files use JSON with Comments (trailing commas, `//` comments). Parse them with `load_jsonc()` from scriptutil — never standard `json.loads()` directly.

Output is always strict JSON — only input (workspace files) may be JSONC.

## Workspace resolution

Scripts resolve multi-repo context via `workhorse.scriptutil`:

```python
from workhorse.scriptutil import resolve_workspace, load_json, load_jsonc

# Pass the workflow's env key so the correct workspace file is found.
repos = resolve_workspace("CODER_WORKSPACE")
# {repo_name: {"path": "/abs/path", "qa_mode": "cli", "verification": "...", ...}}
```

The `workspace_env_key` parameter is the name of the env var that points to a VSCode `.code-workspace` file. Each workflow defines its own convention (e.g. `CODER_WORKSPACE` for the coder workflow). When unset or file missing, CWD is used as the single-folder fallback.

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

For push operations, use the transient credential-helper pattern via `subprocess` (gitpython doesn't support it cleanly):


```python
push_url = f"https://github.com/{owner}/{repo_slug}.git"
cred_helper = f'!f() {{ echo username=x-access-token; echo "password={token}"; }}; f'
subprocess.run(
    ["git", "-c", f"credential.helper={cred_helper}", "push", push_url, f"{branch}:{branch}"],
    cwd=str(repo_path), timeout=120,
)
```


## GitHub API — PyGithub

For typed GitHub API access (PR creation, PR search, issue comments) use PyGithub.
Resolve the token first via `gh-token.py`, then pass it to `Github()`:

```python
from github import Github, GithubException

gh = Github(token)
gh_repo = gh.get_repo("SafelyYou-Inc/olympus")

# Check for existing PR or create one
owner = gh_repo.owner.login
existing = list(gh_repo.get_pulls(head=f"{owner}:{branch}", state="open"))
if existing:
    pr = existing[0]
else:
    pr = gh_repo.create_pull(title=title, body=body, head=branch, base=base)

# Cross-reference comment
pr.create_issue_comment("**Related PRs:**\n- delphi: https://...")
```

Use `gh` CLI via subprocess for one-off token lookup. Use PyGithub when you need
structured responses (PR URL, PR number, paginated list of PRs).

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
