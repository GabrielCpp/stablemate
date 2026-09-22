"""Tests for a prompt written in the state's own source (`self.agent(..., label=...)`)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fakes import FakeBackend, FakeClock  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import (  # noqa: E402
    Continue,
    Done,
    Registry,
    Workflow,
    WorkflowDefinitionError,
)
from workhorse.pyflow.driver import drive  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.runner import ladder  # noqa: E402
from workhorse.templates import render_text  # noqa: E402

Transition = Any

BODY = "# Fix the findings\n\nFix {{ subject }}, each in a sub agent.\n"


class Payload(BaseModel):
    kind: str = "?"
    count: int = 0


def _answer(prompt: str, node_id: str, sid: Any, model: Any = None, **kwargs: Any) -> str:
    seen.append((node_id, prompt))
    return json.dumps({"kind": "fixed", "count": 2})


seen: list[tuple[str, str]] = []


def _env(tmp: str, **kwargs: Any) -> RunEnv:
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        **kwargs,
    )


def _asks(text: str = BODY, label: str = "fix-findings") -> Workflow:
    class Asks(Workflow):
        def start(self) -> Transition:
            reply = self.agent(
                text,
                label=label,
                returns=Payload,
                args={"subject": "the login page"},
            )
            return Done((reply.kind, reply.count))

    return Asks()


def test_an_inline_body_includes_a_partial_the_package_ships(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "rules.md").write_text("Cite a file for {{ subject }}.\n")

    out = render_text(
        "fix-findings",
        '# Fix\n{% include "prompts/rules.md" %}\n',
        {"subject": "login"},
        tmp_path,
    )

    assert "Cite a file for login." in out


def test_a_template_global_resolves_in_an_inline_body(tmp_path):
    out = render_text(
        "fix-findings", '{{ workhorse_var("subject") }}!', {"subject": "login"}, tmp_path
    )

    assert out == "login!"


def test_a_flavor_file_shadows_an_inline_body(tmp_path):
    """Converting a prompt file to inline must not silently drop a repo's override."""
    workflow_dir = tmp_path / "lib" / "workflows" / "author"
    workflow_dir.mkdir(parents=True)
    repo = tmp_path / "repo"
    flavors = repo / ".agents" / "flavors" / "author"
    flavors.mkdir(parents=True)
    (flavors / "fix-findings.md").write_text("REPO RULE for {{ subject }}\n")

    out = render_text(
        "fix-findings",
        BODY,
        {"subject": "login", "_repo_root": str(repo)},
        workflow_dir,
    )

    assert out == "REPO RULE for login\n"


def test_the_label_names_the_node_the_turn_and_the_artifact():
    seen.clear()
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(
            tmp,
            agent_runner=ladder.AgentRunner(
                backend=FakeBackend(turn=_answer), clock=FakeClock()
            ),
        )

        assert drive(_asks(), env) == ("fixed", 2)

        assert seen[0][0] == "fix-findings", seen
        assert "Fix the login page, each in a sub agent." in seen[0][1], seen
        artifact = env.run_dir / "fix-findings" / "prompt.md"
        assert artifact.is_file(), sorted(p.name for p in env.run_dir.iterdir())
        assert "Fix the login page" in artifact.read_text()


def test_the_event_line_carries_the_label_and_not_the_body():
    """`NodeEvent` allows extra keys, so an unguarded prompt would put the whole body on every turn's event line."""
    seen.clear()
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(
            tmp,
            agent_runner=ladder.AgentRunner(
                backend=FakeBackend(turn=_answer), clock=FakeClock()
            ),
        )
        drive(_asks(), env)

        events = (env.run_dir / ArtifactWriter.EVENTS_FILE).read_text()

        assert "inline:fix-findings" in events
        assert "sub agent" not in events


def test_a_dry_run_answers_an_inline_turn_by_its_label():
    with tempfile.TemporaryDirectory() as tmp:
        stubs = Registry("acme").stub_agents(
            {"fix-findings": {"kind": "approved", "count": 3}}
        )
        env = _env(tmp, dry_run=True, agent_stubs=stubs.agent_stubs)

        assert drive(_asks(), env) == ("approved", 3)


def test_a_label_that_is_not_a_node_id_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            drive(_asks(label="Fix Findings"), _env(tmp, dry_run=True))
        except WorkflowDefinitionError as exc:
            assert "Fix Findings" in str(exc)
        else:
            raise AssertionError("a label naming no directory must be refused")


def test_an_inline_body_that_calls_a_manifest_reference_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        body = '# Fix\nRead {{ skill_file("code-review") }}.\n'
        try:
            drive(_asks(text=body), _env(tmp, dry_run=True))
        except WorkflowDefinitionError as exc:
            assert "skill_file" in str(exc)
            assert "prompt file" in str(exc)
        else:
            raise AssertionError("a reference no sweep can see must be refused")


def test_an_inline_body_that_is_not_jinja_is_refused_where_it_is_written():
    """A prompt file's syntax error surfaces at the turn; an inline one surfaces at the call."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            drive(_asks(text="# Fix\n{% for x in %}\n"), _env(tmp, dry_run=True))
        except WorkflowDefinitionError as exc:
            assert "not valid Jinja" in str(exc)
        else:
            raise AssertionError("an unparseable body must be refused")


def test_a_bare_string_is_still_a_prompt_path():
    """Every call site that predates `label` means exactly what it meant."""
    seen.clear()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "prompts").mkdir()
        (Path(tmp) / "prompts" / "review.md").write_text("Review {{ subject }}.\n")
        env = _env(
            tmp,
            agent_runner=ladder.AgentRunner(
                backend=FakeBackend(turn=_answer), clock=FakeClock()
            ),
        )

        class Asks(Workflow):
            def start(self) -> Transition:
                return Continue(None, self.end)

            def end(self) -> Transition:
                reply = self.agent(
                    "prompts/review.md", returns=Payload, args={"subject": "login"}
                )
                return Done(reply.kind)

        assert drive(Asks(), env) == "fixed"
        assert seen[0] == ("review", "Review login.\n"), seen


if __name__ == "__main__":
    import tempfile as _tf

    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                with _tf.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"ok {name}")
