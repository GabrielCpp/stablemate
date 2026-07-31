"""The quick start runs. That is the whole subject of this file.

`hello_world/workflow.py` is the workflow the README and `docs/AUTHORING.md` tell a
first-time reader to run before they trust anything else here, and a quick start that
does not run is worse than no quick start at all — it is the one claim a stranger
checks in the first two minutes. So it is checked here rather than by whoever next
edits it.

Three things have to hold, and they fail independently:

* the name resolves — `workhorse run hello-world` finds it only through the
  `workhorse.workflows` entry point, which lives in `pyproject.toml` and which nothing
  else in this repo would notice the absence of;
* the documented `--dry-run` walks the machine green with **no agent CLI installed**,
  which is the property that makes it runnable on a bare checkout;
* the real path — a genuine agent turn, validated into `Greeting` — reaches `Done`.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.packaged import find_packaged_workflow
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv
from workhorse.pyflow.run import RunInvocation, run_pyflow

from workhorse_workflows.hello_world import workflow as hello_world


def test_the_name_workhorse_run_resolves_is_registered() -> None:
    """`workhorse run hello-world` is a documented command, so the entry point is part
    of the example — not packaging trivia. Nothing else imports this package, so a
    dropped registration is otherwise silent until a reader hits it."""
    found = find_packaged_workflow("hello-world")
    assert found is not None, "hello-world is not registered in workhorse.workflows"
    assert found.value == "workhorse_workflows.hello_world.workflow:workflow"


def test_the_documented_dry_run_walks_the_machine_green() -> None:
    """`workhorse run hello-world --dry-run`, minus the CLI parsing.

    This is the command the quick start opens with, and the reason it can be the
    opener: `measure` answers from its declared `stub=` and the agent turn from
    `stub_agents`, so nothing spawns and no agent CLI need exist. A green exit code
    here also covers the static preflight — every state reachable, every prompt file
    present — which is what would catch `prompts/greet.md` going missing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        code = run_pyflow(
            RunInvocation(
                registry=hello_world.workflow, runs_dir=Path(tmp), dry_run=True
            )
        )
    assert code == 0


def test_a_real_turn_reaches_done_with_the_agents_own_greeting() -> None:
    """The live path: `measure` runs for real and the turn's reply is validated into
    `Greeting` before `greet` ever sees it. The agent is *supplied* on `RunEnv` rather
    than patched into a module, which is the seam the example is meant to teach."""
    seen: list[dict[str, Any]] = []

    def agent(node: Any, ctx: Any, *_args: Any, **_kwargs: Any) -> Any:
        seen.append(ctx.as_dict())
        return "(scripted)", {"greeting": "Hello, globex."}

    with tempfile.TemporaryDirectory() as tmp:
        writer = ArtifactWriter("hello-world", Path(tmp), run_id="t")
        result = drive(
            hello_world.HelloWorld(name="globex"),
            RunEnv(
                writer=writer,
                workflow_dir=Path(hello_world.__file__).parent,
                session_id_path=writer.run_dir / ".session_id",
                config=RunConfig(backend_factory=lambda cli=None: None),
                agent_runner=StubRunner(agent),
                nodes=hello_world.workflow.nodes,
            ),
        )

    assert isinstance(result, hello_world.Greeting)
    assert result.greeting == "Hello, globex."
    # The turn's render args are what the prompt's `{{ name }}`/`{{ letters }}` read,
    # and `letters` only reaches them by travelling through the transition.
    assert seen == [{"name": "globex", "letters": 6}]


if __name__ == "__main__":  # standalone, like every other test in this tree
    test_the_name_workhorse_run_resolves_is_registered()
    test_the_documented_dry_run_walks_the_machine_green()
    test_a_real_turn_reaches_done_with_the_agents_own_greeting()
    print("ok")
