# Testing — substitute, don't patch

Reached from [../SKILL.md](../SKILL.md) when you write or change a test of a workflow node.

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
non-mutating copy:

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
monkeypatch.setattr(workhorse_workflows.acme.qa.nodes, "Ostler", lambda root: FakeOstler(...))
monkeypatch.setattr(workhorse_workflows.kit.git, "commit_all", fake_commit)   # defining module, not `kit`
```

**Never skip a suite on a missing tool.** `pytest.mark.skipif(shutil.which("ostler") is
None, …)` gates on a CLI shim while the code needs the *import*, and a suite that skips
itself reports green having exercised none of the workflow's logic. The dependency is
declared in the distribution; let the tests fail loudly with the `ModuleNotFoundError`.
