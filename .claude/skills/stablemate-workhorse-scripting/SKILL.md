---
name: stablemate-workhorse-scripting
description: "Workhorse workflow scripting — JSON output protocol, shared lib import, workspace resolution, WorkflowRun test API. Applies to scripts/**/*.py."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/stablemate-workhorse-scripting/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-workhorse-scripting/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
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

## Flows — factor a phase for reuse and standalone runs

A **flow** is a named sub-graph declared under a top-level `flows:` map, each a self-contained
mini-workflow with its own `vars` (its parameter contract), `start`, and `nodes`. Two ways to run it:

- **Inline** — a `type: flow` node in the parent graph calls it like a function: `args:` are
  Jinja-rendered against the parent context and are the *only* values that cross the boundary;
  `outputs:` lift declared keys back out; `next:` continues the parent.
- **Standalone** — `workhorse run <workflow> <flow> --params '{"service":"groom"}'`. The flow's
  `vars` are the param contract, so it runs on its own with no parent.


```yaml
# parent graph invokes it:
- id: run_walkthrough_web
  type: flow
  name: walkthrough-web      # must match a key under `flows:`
  args: { service: "{{ service }}", docs_path: "{{ docs_path }}" }
  next: done
flows:
  walkthrough-web:
    name: walkthrough-web
    start: detect_webapp     # resolves its OWN paths — no pre-resolved input needed
    vars:
      service: null          # null default = REQUIRED (missing param -> launch error)
      docs_path: ""          # "" = optional (empty when the caller omits it)
    nodes: [ ... ]
```


**Vars contract:** `null` = required, `""` = optional, any other value = default (see
`workhorse/docs/WORKFLOW.md` §2.6 for the authoritative schema).

**When to factor a phase into a flow:** when it should be **independently runnable** — a re-QA
entrypoint, or a verification pass over an already-built artifact — or reused from more than one
place. Make the flow **self-contained**: its `start` node should resolve its own paths/roots from
the params (e.g. a `prepare`/`detect` script that runs `find_docs_root(docs_path)`), so a
standalone run needs no state the parent would otherwise have supplied. Isolation implications for
the scripts you write: a flow node's scripts see only `{manifest, flow.vars, rendered_args}` — the
parent's context does **not** leak in, so pass every value a flow script needs through `args:`, and
emit back through the flow node's `outputs:` anything the parent must observe.

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

## Git operations — `workhorse.scriptutil`, never `git` subprocess

Don't shell out to `git`. Use the `workhorse.scriptutil` helpers — they wrap
GitPython behind the same lazy-import seam as `open_repo`, so a script never
touches the `git` CLI while git still runs for **real** under test (against a
throwaway repo built with `make_git_repo`). Every helper is fail-soft: a bad repo
or failed command returns `None`/`False`/`-1` rather than raising into a run.

```python
from workhorse.scriptutil import (
    branch_exists, local_branch_exists, current_branch, checkout,
    commits_ahead, commit_all, commit_paths, push_branch, origin_url,
)

# Branch: create or check out story/<slug>, idempotently
if local_branch_exists(repo_path, branch):
    checkout(repo_path, branch)
else:
    checkout(repo_path, branch, create=True)

# Commit everything (False when there was nothing to commit)
commit_all(repo_path, f"{epic}: {slug}" if epic else slug)
# ...or only specific paths
commit_paths(repo_path, "prune completed epic from queue", "docs/epics/index.md")
```

For an authenticated push, `push_branch` handles the transient credential helper
(the token rides `GH_TOKEN`, never a URL / git config / log) **and** verifies the
remote head advanced to the local head — an unverified push is what lets a fix
loop spin against a stale ref:

```python
if not push_branch(repo_path, token, branch):   # verify=True by default
    ...  # push attempted but did not land / did not verify
```

Need the raw `Repo`? `scriptutil.open_repo(path)` is the seam (lazy `import git`,
so a git-free script never pays the import-time `git version` probe).

## GitHub API — `workhorse.scriptutil`, never `gh` subprocess

Don't shell out to `gh`. Go through the `github_client` seam so an in-process test
fakes GitHub by monkeypatching it — no CLI, no network:

```python
from workhorse.scriptutil import resolve_github_token, resolve_repo, find_open_pr

# agents.yml workflow.githubTokenEnv → GH_TOKEN → GITHUB_TOKEN (replaces gh-token.py)
token = resolve_github_token(root)
# PyGithub repo for the origin at `root` (None if not github.com / unreachable)
gh_repo, slug = resolve_repo(root, token)
if gh_repo is not None:
    pr = find_open_pr(gh_repo, branch) or gh_repo.create_pull(
        title=title, body=body, head=branch, base=base,
    )
    pr.create_issue_comment("**Related PRs:**\n- another-service: https://...")
```

`resolve_repo` / `find_open_pr` / `github_client` (and `resolve_github_token`) are
the seams the coder PR/CI scripts share. Reach for raw PyGithub objects past them —
`gh_repo.get_workflow_runs(head_sha=…)`, `pr.merge(merge_method=…)`,
`gh_repo.allow_squash_merge` — when you need structured responses.

## OKF graph (ostler) — the in-process `ostler` API, never subprocess

Don't shell out to the `ostler` CLI — no `subprocess.run(["ostler", …])`, no
`scriptutil.run_tool(["ostler", …])`, no local `ostler_json`/`ostler_run` helper
scraping `--json` out of stdout with `raw_decode`. `ostler` is a dependency of the
library (base-library → tools), so command the doc graph **as a library** through the
`Ostler` facade — it returns plain Python objects (`dict`/`list`/`str` and `Result`),
and an in-process test fakes it by patching the class:

```python
from ostler import Ostler

okf = Ostler(root)                         # root discovered upward, like `ostler -C DIR`
queue   = okf.todo()                       # ["epic-a", …]            (ostler todo list)
stories = okf.list("story", epic="epic-a") # [{"slug","status",…}]    (ostler list --type story)
spec    = okf.spec_path("01-foo")          # "docs/specs/01-foo"      (ostler path spec)
report  = okf.doctor(epic="epic-a")        # dict, == doctor --json's report

res = okf.create_story("epic-a", "02-baz", "Baz", covers=["seed-1"])  # Result(.ok, .entity_id, .message)
okf.add_seed("epic-a", "seed-2", status="researched", meta={"sourceBullet": "…"})
okf.set_status("01-foo", "QA passed")
```

The graph is a **snapshot** read at load time: reads reuse one cached snapshot (the
win over a subprocess-per-call); mutations (`create_*` / `add_seed` / `set_status` /
`backlog_*` / `todo_*` / `settle_review`) apply against a fresh load and invalidate
the cache, so the next read sees them (`reload()` forces a refresh). A read never
returns `None` — on a genuinely unloadable graph the call raises `(OSError,
ValueError, RuntimeError)`; catch that to take a fallback (e.g. a JSON sidecar)
exactly where the old code branched on a non-zero CLI exit. Don't paper over an
empty result as "unavailable": `[]` means an empty queue, a raise means unreadable.

QA / artifact / edit subsystems live on the same facade, **lazy-imported** so the
read path never loads the QA/vet machinery: `okf.qa_context(...)`,
`okf.qa_validate(plan, spec=…)`, `okf.qa_run(plan, spec=…)`,
`okf.qa_context_validate(spec=…)`, `okf.artifact_vet(kind, spec)`,
`okf.settle_review(slug, write=True)`. The coder QA nodes route through the thin
`qa_cli` helpers (`qa_run`/`qa_context`/`qa_validate`/`qa_context_validate`) that wrap
these and normalize to `(returncode, payload, stderr)`. Full verb→method reference:
the `stablemate-ostler` skill.

## Testing workflow scripts

The whole-workflow harness runs the engine **in-process** — no `workhorse` CLI
subprocess and no PATH shims. Agent nodes are mocked, Python script nodes run via
`runpy`, **git runs for real** against a throwaway repo, and **GitHub is faked** by
monkeypatching the `scriptutil.github_client` seam.

**Unit test (call a script directly)** — for a standalone script:

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

**Integration test (WorkflowRun)** — for scripts wired into workflow nodes. Seed
the sandbox as a real git repo with `make_git_repo`; for a GitHub-touching node,
monkeypatch `scriptutil.github_client` to return a fake — there is no `git`/`gh`
mock:

```python
from workhorse import scriptutil
from workhorse.testing import WorkflowRun, make_git_repo, assert_step_output

def test_validate_gate_rejects(tmp_path, monkeypatch):
    make_git_repo(tmp_path)                         # real git; add an `origin` for gh paths
    monkeypatch.setattr(scriptutil, "github_client", lambda token=None: FakeGithub(...))
    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run(flow="dev", params={...})
    assert_step_output(result, "validate_plan", "validation_result", {"status": "invalid"})
```

Key `WorkflowRun` methods:

| Method | Purpose |
|--------|---------|
| `mock_agent(node_id, response)` | Return fixed JSON from an agent node |
| `mock_agent_sequence(node_id, responses)` | Multiple responses for rework loops |
| `run(params, flow)` | Execute the workflow **in-process**, return `RunResult` |
| `result.step_outputs(node_id)` | Parsed `output.json` for a node |
| `result.prompt(node_id)` | Rendered prompt sent to agent |
| `result.context()` | Final workflow context dict |
| `result.calls(cli)` | Recorded agent-backend invocations |

External tools are **not** mocked through `WorkflowRun`: `git` runs for real (seed
with `make_git_repo`), `gh`/GitHub is faked by patching `scriptutil.github_client`,
and `ostler` runs **in-process as a library** — fake it by patching `Ostler`'s
methods (queue/path methods *raising* so a script takes its JSON-sidecar fallback;
QA nodes via the `qa_cli` seam), not `scriptutil.run_tool`. `scriptutil.run_tool`
remains the seam for any *other* genuine external CLI.
