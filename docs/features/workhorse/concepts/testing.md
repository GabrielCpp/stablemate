---
type: concept
slug: testing
title: workhorse.testing — what a callable flow cannot do for itself
---
# workhorse.testing — what a callable flow cannot do for itself

A small library workflow authors import from their workflow's `tests/*.py` pytest files — the
suite [`workhorse test`](../workhorse.md#test) runs. It is **not a harness**, and that is the
whole point of it: a workflow is a Python state machine, so testing one needs no harness at
all. A test constructs the [`Workflow`](../workflow-format.md#workflow-subclass), hands
[`drive`](pyflow-driver.md) a `RunEnv` whose dependencies are substituted, and asserts on what
came back. The walkthrough is
[Author and run a workflow's test suite](../flows/workhorse-author-test.md).

What that leaves over — and all this module is — are the two jobs a callable flow still cannot
do for itself: **stand up a real throwaway git repo to act on**, and **assert on the files it
wrote**. Four functions, no classes, no state.

```python
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.testing import assert_json_file, make_git_repo


def test_select_story(tmp_path):
    repo = make_git_repo(tmp_path / "acme")
    result = drive(Build(subject="login"), env_for(repo))
    assert_json_file(repo, "docs/state.json", {"status": "done"})
```

- code: `workhorse/workhorse/testing.py`

## Why a real repo rather than a mocked `git`

Git operations are tested against a **real (cheap) repo**, not a mocked `git` binary. A
workflow that branches, commits and reads `git status` is exercising git's actual behaviour;
a mock encodes what its author believed that behaviour to be, and the two diverge exactly
where a bug lives. `git init` into a `tmp_path` costs milliseconds, so the honest version is
also the affordable one.

This replaces what the retired YAML front-end's harness did instead: write PATH shim
executables ahead of a subprocess run so the real `workhorse` binary invoked a fake `git`.
Those shims, and the whole subprocess model around them, are gone.

### `make_git_repo(path, *, name="test") -> Path`
Initialises a minimal real git repo at `path` and returns `path`.

- Creates `path` (`parents=True, exist_ok=True`), then runs `git init -q -b main` — the
  default branch is **`main`**, set explicitly so the result does not depend on the host's
  `init.defaultBranch`.
- Sets a repo-local `user.email` / `user.name`, so committing works on a machine with no
  global git identity — a bare CI container, typically.
- Writes `README.md` containing `# <name>` **only if it does not already exist**, so a test
  may lay down its own fixture tree first and then call this to put it under version control.
- `git add -A` and one `git commit -qm init`, giving a repo with a real HEAD. A repo with no
  commits is not the same object: `git rev-parse HEAD`, `git branch` and `git diff HEAD` all
  behave differently on one.

Every subprocess runs with `check=True, capture_output=True`, so a git failure surfaces as
`CalledProcessError` at the setup line rather than as a confusing assertion later.

- code: `workhorse/workhorse/testing.py::make_git_repo`

## Assertion helpers

Module-level `assert`-based helpers, each raising `AssertionError` with a diagnostic message
naming the path and, where it helps, the actual content — standard pytest-collected
assertions, not custom exceptions. All three take the sandbox directory first and a path
**relative** to it, so a test never spells out `tmp_path` twice.

### `assert_file(sandbox, rel)`
`sandbox / rel` exists.

- code: `workhorse/workhorse/testing.py::assert_file`

### `assert_file_contains(sandbox, rel, text)`
`sandbox / rel` exists and its UTF-8 text contains `text` as a substring. The failure message
includes the file's full actual content, which is what makes it usable on a rendered prompt
or a generated document.

- code: `workhorse/workhorse/testing.py::assert_file_contains`

### `assert_json_file(sandbox, rel, subset)`
`sandbox / rel` exists and parses as JSON (a parse failure is re-raised as an `AssertionError`
naming the file, not a bare `JSONDecodeError`), then matched against `subset`:

- **`subset` is a `dict`** — every key in it must be present in the parsed file with an equal
  value. Extra keys in the file are **ignored**, so a test asserts on the fields it cares
  about and does not break when a node starts recording one more.
- **`subset` is a `list`** — the parsed JSON must equal it **exactly**. Order and length are
  part of the claim, because for a list they usually are.

- code: `workhorse/workhorse/testing.py::assert_json_file`

## What is not here, and where it went

The module used to carry a whole-workflow subprocess harness — `WorkflowRun`, `mock_agent`,
`mock_agent_sequence`, `mock_command`, `RunResult`, and the two shim-script templates that
made them work. All of it is deleted. It existed because a YAML workflow had no in-process
callable to test: the only way to exercise one was to run the real CLI and intercept the
world around it. A Python workflow is a class, so the seams moved inside:

| Was | Is |
|---|---|
| `mock_agent(node_id, response)` | `RunEnv(agent_runner=…)` for a scripted turn, or [`Registry.stub_agents({stem: reply})`](../workflow-format.md#registry) for a declared one |
| `mock_agent_sequence(node_id, [...])` | an `agent_runner` that is a closure over a list — ordinary Python |
| `mock_command("git", …)` | `make_git_repo` (real git), or [`Registry.override(**by_name)`](../workflow-format.md#registry) to rebind the node that shells out |
| `WorkflowRun.run(params=…, flow=…)` | `drive(MyWorkflow(**params), env)`, or the flow class directly |
| `RunResult.context()` / `.step_outputs(id)` | the value `drive` returned, and `self.output(node)` / the run dir's `output.json` |
| `RunResult.prompt(id)` | the run dir's `<node>/prompt.md`, written by the real writer |
| `assert_step_output` / `assert_prompt_contains` / `assert_command_called` | a plain `assert` on the above — there is no indirection left to wrap |

Nothing was lost that a test still needs, because the substitutions are now **run
dependencies rather than environment tricks**: no `PATH` manipulation, no `subprocess`, no
recorded-call JSON to parse back.

## Consumers

- Every workflow's `tests/*.py`, run via [`workhorse test <workflow_dir>`](../workhorse.md#test).
- `workflows/tests/**` in this workspace — the shipped workflows' own suites, and the
  worked reference for the pattern above.
