"""The role registry and the body resolver behind every coder agent turn.

Naming a role instead of a file costs one check the engine used to do for free:
`pyflow.graph._missing_prompts` only sees *literal* prompt strings, so an
`self.agent(turn.prompt, …)` is invisible to it and a prompt deleted out from under a
flow would now surface as a render error mid-run instead of before the first node. The
first two tests here are that check, restored — every role has an envelope, and every
envelope is a role or a named piece of workflow mechanics.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared import roles

CODER = Path(roles.__file__).resolve().parent.parent
PROMPTS = CODER / "prompts"

#: The prompts that are the state machine talking to itself. Not roles, not overridable,
#: and listed here so adding one is a decision rather than an omission.
MECHANICS = {"resolve-operator", "settle-worktree", "fix-merge"}


def test_every_role_has_an_envelope_the_workflow_ships():
    missing = sorted(r for r in roles.ROLES if not (PROMPTS / f"{r}.md").is_file())
    assert not missing, f"roles with no `prompts/<role>.md`: {missing}"


def test_every_prompt_is_a_role_or_declared_mechanics():
    stems = {p.stem for p in PROMPTS.glob("*.md")}
    assert stems - set(roles.ROLES) - MECHANICS == set()
    # And the mechanics are real files, so the set above cannot rot into a fiction that
    # silently excuses a missing role.
    assert MECHANICS <= stems


def test_no_flow_still_names_a_role_by_filename():
    """A flow may name a mechanics prompt literally; a role it must resolve."""
    literal = re.compile(r'"prompts/([a-z-]+)\.md"')
    offenders = [
        f"{path.name}:{stem}"
        for path in CODER.rglob("*.py")
        for stem in literal.findall(path.read_text())
        if stem in roles.ROLES
    ]
    assert not offenders, f"literal prompt paths for overridable roles: {offenders}"


def test_every_role_a_flow_asks_for_is_registered():
    asked = {
        role
        for path in CODER.rglob("*.py")
        for role in re.findall(r'roles\.turn\(\s*"([a-z-]+)"', path.read_text())
    }
    assert asked, "no flow resolves a role — the scan is looking in the wrong place"
    assert asked <= set(roles.ROLES)


def _library(root: Path, role: str, text: str) -> Path:
    body = root / roles.LIBRARY_SUBDIR
    body.mkdir(parents=True, exist_ok=True)
    (body / f"{role}.md").write_text(text)
    return root


def test_with_no_layers_the_envelope_renders_alone(tmp_path):
    turn = roles.turn("dev-fix", tmp_path)

    assert turn == roles.Turn("prompts/dev-fix.md", {})


def test_the_overlay_layer_wins_over_the_base(tmp_path):
    overlay = _library(tmp_path / "overlay", "dev-fix", "overlay")
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn("dev-fix", tmp_path, (str(overlay), str(base)))

    assert turn.args["body_template"] == "body/dev-fix.md"
    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "overlay"


def test_a_layer_without_the_role_is_skipped_rather_than_resolved(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn("dev-fix", tmp_path, (str(empty), str(base)))

    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "base"


def test_the_repo_outranks_every_library_layer(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "go").mkdir()
    (repo / "go" / "fix.md").write_text("the repo's own")
    (repo / "agents.yml").write_text(yaml.safe_dump({"prompts": {"dev-fix": "go/fix.md"}}))
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn("dev-fix", repo, (str(base),))

    assert (Path(turn.args["_body_dir"]) / Path(turn.args["body_template"]).name).read_text() == (
        "the repo's own"
    )


def test_a_repo_override_pointing_nowhere_falls_through_to_the_library(tmp_path):
    """A typo in a hand-edited `agents.yml` leaves the story implemented, not parked."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "agents.yml").write_text(yaml.safe_dump({"prompts": {"dev-fix": "go/gone.md"}}))
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn("dev-fix", repo, (str(base),))

    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "base"


def test_a_malformed_agents_yml_means_no_override_not_a_dead_run(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "agents.yml").write_text("prompts: [not, a, mapping\n  - :")

    assert roles.turn("dev-fix", repo) == roles.Turn("prompts/dev-fix.md", {})


def test_the_nested_workflow_block_is_read_too(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "own.md").write_text("nested")
    (repo / "agents.yml").write_text(
        yaml.safe_dump({"workflow": {"prompts": {"dev-fix": "own.md"}}})
    )

    turn = roles.turn("dev-fix", repo)

    assert (Path(turn.args["_body_dir"]) / "own.md").read_text() == "nested"


def test_an_unregistered_role_is_caught_on_the_transition(tmp_path):
    with pytest.raises(WorkflowFailed, match="unknown prompt role"):
        roles.turn("dev-fx", tmp_path)


def test_a_moved_body_no_layer_supplies_stops_the_turn(tmp_path, monkeypatch):
    """The envelope alone is a contract with no procedure — it must never be a turn."""
    monkeypatch.setattr(roles, "LIBRARY_BODIES", frozenset({"dev-fix"}))

    with pytest.raises(WorkflowFailed, match="no prompt body for role 'dev-fix'"):
        roles.turn("dev-fix", tmp_path)

    base = _library(tmp_path / "base", "dev-fix", "base")
    assert roles.turn("dev-fix", tmp_path, (str(base),)).args["body_template"] == (
        "body/dev-fix.md"
    )
