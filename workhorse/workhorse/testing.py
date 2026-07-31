"""Test utilities for workflow authors.

A workflow is a Python state machine, so testing one needs no harness: a test
constructs the :class:`~workhorse.pyflow.workflow.Workflow`, substitutes the
dependencies it wants to control on the run's ``RunEnv``, and drives it with
:func:`workhorse.pyflow.driver.drive`. What that leaves over — and what lives
here — are the two things a callable flow still cannot do for itself: stand up a
real throwaway git repo to act on, and assert on the files it wrote.

Example::

    from workhorse.artifacts import ArtifactWriter
    from workhorse.config_run import RunConfig
    from workhorse.pyflow.driver import drive
    from workhorse.pyflow.engine import RunEnv
    from workhorse.testing import assert_json_file, make_git_repo

    def test_select_story(tmp_path):
        repo = make_git_repo(tmp_path / "acme")
        writer = ArtifactWriter("acme", tmp_path / "runs", run_id="t")
        result = drive(
            MyWorkflow(subject="login"),
            RunEnv(
                writer=writer,
                workflow_dir=Path(my_workflow.__file__).parent,
                session_id_path=writer.run_dir / ".session_id",
                config=RunConfig(),  # no CLI selected: the null backend, not None
                # The seams: rebind a node, script a turn, or leave either out to
                # get the real one. `nodes=` takes `registry.nodes` or a copy from
                # `registry.override(...)`.
                nodes=my_workflow.workflow.nodes,
                agent_runner=StubRunner(scripted_turn),
            ),
        )
        assert_json_file(repo, "docs/state.json", {"status": "done"})

See ``docs/features/workhorse/flows/workhorse-author-test.md`` for the walkthrough,
and ``workflows/tests/test_hello_world.py`` for this example as running code.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

__all__ = [
    "make_git_repo",
    "assert_file",
    "assert_file_contains",
    "assert_json_file",
]


# ── Real throwaway git repo ────────────────────────────────────────────────────

def make_git_repo(path: Path, *, name: str = "test") -> Path:
    """Initialise a minimal real git repo at ``path`` with one commit.

    Git operations are tested against a REAL (cheap) repo rather than a mocked
    ``git`` — the ``test_multi_repo_git`` pattern, generalised. Returns ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True
    )
    return path


# ── Assertion helpers ─────────────────────────────────────────────────────────

def assert_file(sandbox: Path, rel: str) -> None:
    """Assert that ``sandbox / rel`` exists."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"


def assert_file_contains(sandbox: Path, rel: str, text: str) -> None:
    """Assert that ``sandbox / rel`` exists and contains ``text``."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"
    content = path.read_text(encoding="utf-8")
    assert text in content, (
        f"Expected {rel!r} to contain {text!r}\n"
        f"Actual content:\n{content}"
    )


def assert_json_file(sandbox: Path, rel: str, subset: dict | list) -> None:
    """Assert that ``sandbox / rel`` is valid JSON matching ``subset``.

    For dicts: every key/value pair in ``subset`` must be present with equal values.
    For lists: the parsed JSON must equal ``subset`` exactly.
    """
    path = sandbox / rel
    assert path.exists(), f"Expected JSON file {rel!r} to exist in sandbox, but it does not"
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AssertionError(f"File {rel!r} is not valid JSON: {e}") from e
    if isinstance(subset, list):
        assert actual == subset, (
            f"Expected {rel!r} to equal {subset!r}\nActual: {actual!r}"
        )
    else:
        for key, expected_val in subset.items():
            assert key in actual, (
                f"Expected key {key!r} in {rel!r}\nActual keys: {list(actual)}"
            )
            assert actual[key] == expected_val, (
                f"Expected {rel!r}[{key!r}] == {expected_val!r}\nActual: {actual[key]!r}"
            )
