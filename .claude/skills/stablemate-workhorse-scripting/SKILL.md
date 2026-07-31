---
name: stablemate-workhorse-scripting
description: "Writing workhorse workflow nodes — the @blueprint.node contract, typed returns, WorkflowFailed routing, the kit git/GitHub/workspace helpers, the in-process ostler facade, and substitution-based testing. Applies to a workflow distribution's Python."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/stablemate-workhorse-scripting/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-workhorse-scripting/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Workhorse workflow nodes

A workflow is a **Python package**, not a YAML document. Its states are methods on a
`Workflow` subclass; its side-effecting work lives in **node functions** registered on a
`Blueprint`. There is no `workflow.yaml`, no `script:` node, no `outputs:` list, and no
stdout protocol — a node **returns a typed value**.

The engine API is documented in `workhorse/docs/AUTHORING.md`; this skill is about the
code you write against it.

---

## Separation of concerns — workhorse is generic, keep workflow logic in the workflow

Workhorse (`workhorse/**`, including `scriptutil.py`, `templates.py`, the pyflow driver,
and the Jinja globals it registers) is a **generic engine shared by every workflow**. It
must never learn the shape of one workflow's data.

**Do not add workflow-specific logic to workhorse.** Concretely, do not put in workhorse:
- a schema of a particular `plan-context.json` / plan_result (e.g. `services[].type`,
  `touched_layers`, layer→platform maps) — that is the coder workflow's vocabulary;
- a Jinja global that derives a workflow-specific value (e.g. `touched_layers()`); or
- branching on a specific env var name, repo name, or story convention.

**Where each thing lives:**
- **Deriving a value from the workflow's own data** → do it in the **workflow**: either in
  a `@blueprint.node` function that reads the JSON and returns the derived field, or
  directly in the prompt's Jinja over the args the state passes
  (`{% for svc in plan_result.services %}` / `| map(attribute='type') | unique`).
- **A genuinely reusable primitive** → add it to workhorse **parameterised**, with no
  knowledge of any workflow's field names. `resolve_workspace(env_key)` is the model: the
  workflow passes `"CODER_WORKSPACE"`; workhorse just reads the env var it's told to. Good
  additions are things like "read a dotted path from a JSON file", "dedup a list preserving
  order" — verbs, not nouns from a specific schema.

Litmus test before touching `workhorse/**`: *would a totally different workflow want this
unchanged?* If it only makes sense for the coder workflow, it belongs in the workflow.

---

## Where a node lives

```
workflows/src/workhorse_workflows/<name>/
├── workflow.py          # the Workflow subclass + `Registry(...)` + `main = registry.main(Entry)`
├── schemas.py           # the pydantic models states and nodes exchange
├── prompts/*.md         # Jinja prompt templates, addressed by path from self.agent(...)
└── nodes/
    ├── _blueprint.py    # `blueprint = Blueprint("<name>")` — here, not in __init__, so
    │                    #   submodules import it without a cycle
    ├── __init__.py      # re-exports `blueprint` and every node function
    └── setup.py, …      # the node functions themselves
```

The distribution advertises itself through the `workhorse.workflows` entry-point group;
`workhorse run <name>` resolves the name to the registry. Nothing is found by file path.

## The node contract

```python
from __future__ import annotations

import logging

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.acme.nodes._blueprint import blueprint
from workhorse_workflows.acme.schemas import Validation


@blueprint.node
def validate_plan(logger: logging.Logger, spec_dir: str) -> Validation:
    logger.info("validating %s", spec_dir)
    errors = [...]
    return Validation(status="invalid" if errors else "valid", errors=errors)
```

- **`logger` is the first parameter, injected by the engine.** Never construct one, never
  call `logging.basicConfig` — the driver owns handlers, level (`WORKHORSE_LOG_LEVEL`) and
  the OTel export, and a node's records ride the driver's root logger with the run's
  `run_id` and node attribute already stamped.
- **Every other parameter is supplied by the caller**: `self.call(validate_plan, spec_dir)`.
  Arguments are ordinary Python values — no Jinja, no `sys.argv`, no argparse.
- **The return annotation is required and is the node's real output contract.** The
  decorator resolves it (`eval_str=True`, so `from __future__ import annotations` is fine)
  and keeps it: it is what `self.output(node)` revives an `output.json` back into, and what
  `--dry-run` blanks. A pydantic `BaseModel` is the intended shape; dataclasses, dicts and
  scalars are projected too, but only a model round-trips as a typed value.
- **Nothing is printed to communicate.** The engine records `jsonable(return_value)` to the
  node's `output.json` itself. `print()` in a node is a diagnostic at best; use `logger`.
- **`raise WorkflowFailed(reason)`** ends the run with that reason. There are no exit codes
  and no `SystemExit`; `raise SystemExit` inside a node kills the driver's own process and
  loses the checkpoint.

### Porting a `main(logger)` script

The old `script:` nodes were already `def main(logger)`. That contract was chosen so they
port with the envelope stripped and nothing else:

1. rename `main` to something that says what it does, and decorate it `@blueprint.node`;
2. delete the `argparse` / `sys.argv[1:]` preamble — those become named parameters;
3. delete the final `print(json.dumps({...}))` — return the model instead;
4. add the return annotation;
5. replace `raise SystemExit(1)` with `raise WorkflowFailed("…")`.

The body in between does not change.

### Decorator options

```python
@blueprint.node(aliases=["old_name"], retries=2, stub=lambda logger, **kw: Report(ok=True))
def check_stack(logger: logging.Logger, manifest: dict) -> Report: ...
```

- `aliases=[…]` — the names this node used to have. `self.output(node)` resolves by node
  name against the run directory, so renaming a node without an alias orphans a mid-week
  run's recorded outputs exactly as renaming a state breaks its checkpoint.
- `retries=N` — re-calls on exception before the failure propagates. `0` (the default)
  means call once.
- `stub=…` — what `--dry-run` calls instead, same signature. Declaring one turns a dry run
  from "every branch takes an arbitrary path" into a real smoke test of the happy path;
  without one the node yields a blank instance of its return model.
- There is deliberately **no `timeout=`**. A node runs in the engine's own process and
  there is no portable way to interrupt it, so the knob would be accepted and ignored. The
  run-wide `WORKHORSE_MAX_RUNTIME_S` budget is what bounds a slow node.

### A node shares the driver's fate

`self.call(node, …)` is an in-process function call — that is what makes a node's spans and
log records land in the run's telemetry at all. The cost is one-directional: a node that
calls `os._exit`, segfaults a C extension or exhausts memory takes the run down with it,
losing the checkpoint write a raised exception would have gone through. Raise; do not exit.

A process a node **backgrounds** is owned by nothing and is reaped when the node ends. A
process that must outlive its node has to be started detached and owned explicitly —
`workhorse.stack`'s `ensure_stack` / `teardown_stack` is the parameterised primitive for it.

## Idempotency, not just determinism

A resume re-enters a state **from the top**, so every node the state already called is
called again. A node must therefore be safe to run twice: create-or-reuse a branch rather
than create, `mkdir(exist_ok=True)`, skip a commit with nothing staged, look for an open PR
before opening one. "It only worked because it ran once" is the defect this contract names.

## Logging and activity

```python
logger.info("Starting with spec_dir=%s", spec_dir)
logger.warning("Skipping %s: no agents.yml", repo_name)
logger.info("gate %s: implementing", gate_id, extra={"activity": True})
```

`extra={"activity": True}` flags a record as *what the run is doing now* — the rendered
message **is** the activity, so it is never written twice. Workflow-level dimensions
(`work_id`, epic, service…) go in the `Workflow.labels()` override instead, not in log text.

## Failure routing — commit the evidence, fail red, never publish

A gate that fails must leave the broken work somewhere obvious and stop the run. It must
never fall through to a publishing step (open a PR, merge, deploy, mark an epic done).
In a state machine the shape is:

- have the failing branch call its **own** commit node with an unmistakable message
  (`"author: INCOMPLETE — unwritten stories, do not merge"`), then `raise WorkflowFailed(…)`
  — the partial work stays on the branch, findable, and the run exits non-zero;
- keep the publishing call reachable **only** from the passing branch. In Python the old
  `default:`-swallows-everything hazard becomes an `else:`: an `else` that falls through to
  the happy path turns every unanticipated verdict into a green run. Route the unknown
  verdict to the failure arm, or `raise WorkflowFailed` naming the value you did not expect;
- name the offenders in the node's own returned model (an `errors` field) and, when the doc
  graph owns the fact, as a `doctor` finding too, so the failure is visible from outside.

Deleting the partial artifact is the wrong instinct: work that vanishes on failure is
indistinguishable from work never attempted.

## Dependencies — declare them in the distribution, import at the top, never degrade

There is no `requires:` block. A workflow distribution declares what its nodes need in its
own `[project.dependencies]` (`workflows/pyproject.toml` for `workhorse-workflows`), and
resolving a workflow *name* imports its package — so an unimportable dependency fails at
import, before any node runs, which is where it belongs.

Two rules follow, and they are the whole point:

- **Import at module scope.** No `import` inside a `def`. A declared dependency is
  importable by the time the workflow resolves, so the import cannot usefully fail there.
- **No degradation branch.** Never write `try: import X / except ImportError:` followed by
  emitting a verdict anyway. A node that answers "is this story authored?" with "I couldn't
  load the graph, so — yes" is worse than one that crashes; that shape is what lets a run
  produce empty artifacts and report success.

Catch narrowly around the *work*, not around the import: `except (OSError, ValueError,
RuntimeError, KeyError)` around a graph load that can legitimately fail, with the failure
returned as a **negative** verdict plus its reason. A verdict that could not be computed is
never a pass.

The one accepted `try/except ImportError` is a genuinely optional dependency (PyYAML) —
still at module scope, binding the name to `None`, with every user returning early on
`yaml is None` so a later `yaml.YAMLError` reference cannot raise `NameError`.

## JSONC parsing

VSCode workspace files are JSON with Comments (trailing commas, `//` comments). Parse them
with `load_jsonc()` from `workhorse.scriptutil` — never `json.loads()` directly. Anything a
node *writes* is strict JSON; only input may be JSONC.

## What the engine still offers directly — `workhorse.scriptutil`

The generic, workflow-agnostic half: `load_json`, `load_jsonc`, `find_repo_root`,
`find_docs_root`, `fresh_import`, `run_tool`, `die`. `run_tool` remains the seam for a
genuine external CLI — one that is not git, GitHub or ostler.

## Domain helpers — `workhorse_workflows.kit`

Git, GitHub and workspace resolution live in the **workflow** distribution, not the engine.

```python
from workhorse_workflows import kit
```

- `kit.git` — `open_repo`, `active_branch`, `current_branch`, `default_branch`,
  `branch_exists`, `local_branch_exists`, `checkout`, `clone`, `fetch_reset`,
  `commit_all`, `commit_paths`, `commits_ahead`, `merge_base`, `diff_text`, `show_file`,
  `list_tracked_files`, `restore_paths`, `rename_branch`, `push_to_origin`, `origin_url`,
  `remote_urls`, `set_identity`, `short_sha`, `allow_all_directories`.
- `kit.github` — `resolve_github_token`, `resolve_repo`, `github_client`, `find_open_pr`,
  `push_branch`, `repo_full_name_from_url`, `sync_to_origin`.
- `kit.workspace` — `resolve_workspace`, `get_repo_config`, `get_affected_repos`,
  `build_dispatch_list`, `checkout_workspace`.

**Never shell out to `git` or `gh`.** The helpers wrap GitPython and PyGithub behind seams,
so a node never touches the CLIs while git still runs for **real** under test (against a
throwaway repo from `make_git_repo`) and GitHub is faked by patching `github_client`. Every
git helper is fail-soft: a bad repo or failed command returns `None`/`False`/`-1` rather
than raising into a run.

```python
# Branch: create or check out, idempotently — a resume re-enters this node.
if kit.git.local_branch_exists(repo_path, branch):
    kit.git.checkout(repo_path, branch)
else:
    kit.git.checkout(repo_path, branch, create=True)

kit.git.commit_all(repo_path, f"{epic}: {slug}" if epic else slug)   # False = nothing to commit
kit.git.commit_paths(repo_path, "prune completed epic from queue", "docs/epics/index.md")
```

`push_branch` handles the transient credential helper (the token rides `GH_TOKEN`, never a
URL / git config / log) **and** verifies the remote head advanced to the local head — an
unverified push is what lets a fix loop spin against a stale ref:

```python
if not kit.github.push_branch(repo_path, token, branch):   # verify=True by default
    ...  # push attempted but did not land / did not verify
```

For GitHub, go through the seams and reach for raw PyGithub objects past them when you need
structured responses (`gh_repo.get_workflow_runs(head_sha=…)`, `pr.merge(merge_method=…)`):

```python
token = kit.github.resolve_github_token(root)     # agents.yml workflow.githubTokenEnv → GH_TOKEN → GITHUB_TOKEN
gh_repo, slug = kit.github.resolve_repo(root, token)
if gh_repo is not None:
    pr = kit.github.find_open_pr(gh_repo, branch) or gh_repo.create_pull(
        title=title, body=body, head=branch, base=base,
    )
```

`kit` re-exports these through a module `__getattr__`, so `kit.git.commit_all` and
`from workhorse_workflows.kit.git import commit_all` are the same function. **Patch the
defining submodule** (`workhorse_workflows.kit.git`), not the `kit` facade, or the
forwarding hands the test the real one.

**Working directory.** A node inherits the driver's cwd. Use `AGENT_REPO_DIR` when you need
the run's repo root rather than assuming it:

```python
env_root = os.environ.get("AGENT_REPO_DIR")
root = Path(env_root).resolve() if env_root else Path.cwd().resolve()
```

## OKF graph (ostler) — the in-process `ostler` API, never subprocess

Don't shell out to the `ostler` CLI — no `subprocess.run(["ostler", …])`, no
`scriptutil.run_tool(["ostler", …])`, no local `ostler_json`/`ostler_run` helper scraping
`--json` out of stdout with `raw_decode`. `ostler` is a dependency of the workflow
distribution, so command the doc graph **as a library** through the `Ostler` facade — it
returns plain Python objects (`dict`/`list`/`str` and `Result`), and an in-process test
fakes it by patching the class:

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

The graph is a **snapshot** read at load time: reads reuse one cached snapshot (the win over
a subprocess-per-call); mutations (`create_*` / `add_seed` / `set_status` / `backlog_*` /
`todo_*` / `settle_review`) apply against a fresh load and invalidate the cache, so the next
read sees them (`reload()` forces a refresh). A read never returns `None` — on a genuinely
unloadable graph the call raises `(OSError, ValueError, RuntimeError)`; catch that to take a
fallback (e.g. a JSON sidecar). Don't paper over an empty result as "unavailable": `[]` means
an empty queue, a raise means unreadable.

QA / artifact / edit subsystems live on the same facade, **lazy-imported** so the read path
never loads the QA/vet machinery: `okf.qa_context(...)`, `okf.qa_validate(plan, spec=…)`,
`okf.qa_run(plan, spec=…)`, `okf.qa_context_validate(spec=…)`, `okf.artifact_vet(kind, spec)`,
`okf.settle_review(slug, write=True)`. The coder QA nodes route through the thin `qa_cli`
helpers (`qa_run`/`qa_context`/`qa_validate`/`qa_context_validate`) that wrap these and
normalize to `(returncode, payload, stderr)`. Full verb→method reference: the
`stablemate-ostler` skill.

## Testing — substitute, don't patch

The node index and the agent backend are **fields of the run**, so a test supplies its own
instead of assigning over module attributes it then has to remember to restore.

**Unit test a node** — it is a plain function; call it:

```python
import logging

def test_validate_plan_rejects(tmp_path):
    result = validate_plan(logging.getLogger("test"), str(tmp_path))
    assert result.status == "invalid"
```

**Drive the whole state machine** — build a `RunEnv` with a scripted agent and a node index
with the outside-world nodes overridden. `Registry.override(**by_name)` returns a
non-mutating copy; `Registry.stub_agents({stem: reply})` declares dry-run replies:

```python
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

registry = acme.workflow.override(clone_repo=lambda logger: RepoSetup(repo_dir=str(repo)))
env = RunEnv(nodes=registry.nodes, agent=_Agent(script), writer=writer, ...)
drive(env, acme.Build, params={...})
```

Everything not substituted runs for real — git against a throwaway repo from
`make_git_repo`, the workflow's own parsing, its `setup()` residue, its commits. That is
the point: what is under test is the machine's arithmetic (caps, counters, routing), and a
cap is best asserted by *changing the constant*, which is only possible when there is one
copy of it.

`workhorse.testing` offers `make_git_repo`, `assert_file`, `assert_file_contains`,
`assert_json_file`. There is no `WorkflowRun`, no `assert_step_output`, no
`assert_prompt_contains`, no `assert_command_called` — a state machine is asserted on its
return values and its recorded artifacts, not on a step table.

**Patch the name the code actually bound.** Because nodes import at module scope, a module
that did `from ostler import Ostler` resolved that name at import —
`monkeypatch.setitem(sys.modules, "ostler", fake)` is too late and the test silently
exercises the real tool while appearing to fake it. Patch the attribute on the module that
bound it (or the class's methods, which is the same object):

```python
monkeypatch.setattr(workhorse_workflows.acme.nodes.qa, "Ostler", lambda root: FakeOstler(...))
monkeypatch.setattr(workhorse_workflows.kit.git, "commit_all", fake_commit)   # defining module, not `kit`
```

**Never skip a suite on a missing tool.** `pytest.mark.skipif(shutil.which("ostler") is
None, …)` gates on a CLI shim while the code needs the *import*, and a suite that skips
itself reports green having exercised none of the workflow's logic. The dependency is
declared in the distribution; let the tests fail loudly with the `ModuleNotFoundError`.
