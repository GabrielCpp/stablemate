"""The role registry and the body resolver behind every coder agent turn."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.schemas.dev import FixResult

CODER = Path(roles.__file__).resolve().parent.parent

PROMPT_DIRS = sorted(CODER.glob("*/prompts"))

MECHANICS = {"resolve-operator", "settle-worktree", "fix-merge"}


def _stems(directory: Path) -> set[str]:
    """The envelopes in a prompt directory — the `_`-prefixed partials are not envelopes."""
    return {p.stem for p in directory.glob("*.md") if not p.stem.startswith("_")}


def _flow(name: str, repo_dir: Path, library_dirs: tuple[str, ...] = ()) -> object:
    """A stand-in for a flow, defined where a real one lives so `flow_dir` reads `name`."""
    fake = type("Flow", (), {"repo_dir": repo_dir, "library_dirs": library_dirs})
    fake.__module__ = f"{roles.PACKAGE}.{name}.flow"
    return fake()


def test_the_sweep_found_prompt_directories():
    """The guard against a glob that silently matches nothing after another move."""
    assert len(PROMPT_DIRS) >= 7, [d.parent.name for d in PROMPT_DIRS]


def test_every_role_has_an_envelope_the_workflow_ships():
    shipped: set[str] = set()
    for directory in PROMPT_DIRS:
        shipped |= _stems(directory)
    missing = sorted(set(roles.ROLES) - shipped)
    assert not missing, f"roles with no `<flow>/prompts/<role>.md`: {missing}"


@pytest.mark.parametrize("directory", PROMPT_DIRS, ids=[d.parent.name for d in PROMPT_DIRS])
def test_every_prompt_is_a_role_or_declared_mechanics(directory: Path):
    stems = _stems(directory)
    assert stems, f"{directory.parent.name}/prompts/ ships nothing"
    assert stems - set(roles.ROLES) - MECHANICS == set()


def test_the_operator_resolver_ships_exactly_once():
    """Four lanes gate; one prompt answers."""
    copies = sorted(
        f"{d.parent.name}/prompts" for d in PROMPT_DIRS if "resolve-operator" in _stems(d)
    )

    assert copies == ["shared/prompts"], copies


def test_the_declared_mechanics_are_real_files():
    """So the set above cannot rot into a fiction that silently excuses a missing role."""
    shipped: set[str] = set()
    for directory in PROMPT_DIRS:
        shipped |= _stems(directory)
    assert MECHANICS <= shipped


def test_no_flow_still_names_a_role_by_filename():
    """A flow may name a mechanics prompt literally; a role it must resolve."""
    literal = re.compile(r'"[a-z_]+/prompts/([a-z-]+)\.md"')
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
        for role in re.findall(r'roles\.turn\(\s*self,\s*"([a-z-]+)"', path.read_text())
    }
    assert asked, "no flow resolves a role — the scan is looking in the wrong place"
    assert asked <= set(roles.ROLES)


def _library(root: Path, role: str, text: str) -> Path:
    body = root / roles.LIBRARY_SUBDIR
    body.mkdir(parents=True, exist_ok=True)
    (body / f"{role}.md").write_text(text)
    return root


def test_with_no_layers_the_envelope_renders_alone(tmp_path):
    turn = roles.turn(_flow("dev", tmp_path), "dev-fix", returns=FixResult)

    assert turn.prompt == "dev/prompts/dev-fix.md"
    assert "body_template" not in turn.args


def test_the_envelope_is_the_calling_flows_own_copy(tmp_path):
    """The same role, two flows, two files — which is the whole point of taking `flow`."""
    assert roles.turn(_flow("dev", tmp_path), "plan-story", returns=FixResult).prompt == (
        "dev/prompts/plan-story.md"
    )
    assert roles.turn(_flow("fix", tmp_path), "plan-story", returns=FixResult).prompt == (
        "fix/prompts/plan-story.md"
    )


def test_a_flow_defined_outside_the_package_is_caught_rather_than_mispathed(tmp_path):
    stray = type("Stray", (), {"repo_dir": tmp_path, "library_dirs": ()})
    stray.__module__ = "somewhere.else"

    with pytest.raises(WorkflowFailed, match="outside"):
        roles.turn(stray(), "dev-fix", returns=FixResult)


def test_the_overlay_layer_wins_over_the_base(tmp_path):
    overlay = _library(tmp_path / "overlay", "dev-fix", "overlay")
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn(_flow("dev", tmp_path, (str(overlay), str(base))), "dev-fix", returns=FixResult)

    assert turn.args["body_template"] == "body/dev-fix.md"
    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "overlay"


def test_a_layer_without_the_role_is_skipped_rather_than_resolved(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn(_flow("dev", tmp_path, (str(empty), str(base))), "dev-fix", returns=FixResult)

    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "base"


def test_one_repo_override_serves_every_flows_copy(tmp_path):
    """`prompts:` is keyed by role, so a repo replaces a body once, not once per flow."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "go").mkdir()
    (repo / "go" / "plan.md").write_text("the repo's own")
    (repo / "agents.yml").write_text(
        yaml.safe_dump({"prompts": {"plan-story": "go/plan.md"}})
    )

    for name in ("dev", "fix", "main"):
        turn = roles.turn(_flow(name, repo), "plan-story", returns=FixResult)
        assert turn.prompt == f"{name}/prompts/plan-story.md"
        body = Path(turn.args["_body_dir"]) / Path(turn.args["body_template"]).name
        assert body.read_text() == "the repo's own"


def test_the_repo_outranks_every_library_layer(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "go").mkdir()
    (repo / "go" / "fix.md").write_text("the repo's own")
    (repo / "agents.yml").write_text(yaml.safe_dump({"prompts": {"dev-fix": "go/fix.md"}}))
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn(_flow("dev", repo, (str(base),)), "dev-fix", returns=FixResult)

    assert (Path(turn.args["_body_dir"]) / Path(turn.args["body_template"]).name).read_text() == (
        "the repo's own"
    )


def test_a_repo_override_pointing_nowhere_falls_through_to_the_library(tmp_path):
    """A typo in a hand-edited `agents.yml` leaves the story implemented, not parked."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "agents.yml").write_text(yaml.safe_dump({"prompts": {"dev-fix": "go/gone.md"}}))
    base = _library(tmp_path / "base", "dev-fix", "base")

    turn = roles.turn(_flow("dev", repo, (str(base),)), "dev-fix", returns=FixResult)

    assert (Path(turn.args["_body_dir"]) / "dev-fix.md").read_text() == "base"


def test_a_malformed_agents_yml_means_no_override_not_a_dead_run(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "agents.yml").write_text("prompts: [not, a, mapping\n  - :")

    turn = roles.turn(_flow("dev", repo), "dev-fix", returns=FixResult)

    assert turn.prompt == "dev/prompts/dev-fix.md"
    assert "body_template" not in turn.args


def test_the_nested_workflow_block_is_read_too(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "own.md").write_text("nested")
    (repo / "agents.yml").write_text(
        yaml.safe_dump({"workflow": {"prompts": {"dev-fix": "own.md"}}})
    )

    turn = roles.turn(_flow("dev", repo), "dev-fix", returns=FixResult)

    assert (Path(turn.args["_body_dir"]) / "own.md").read_text() == "nested"


def test_an_unregistered_role_is_caught_on_the_transition(tmp_path):
    with pytest.raises(WorkflowFailed, match="unknown prompt role"):
        roles.turn(_flow("dev", tmp_path), "dev-fx", returns=FixResult)


def test_no_library_anywhere_is_not_an_error(tmp_path):
    """The workflow is installed standalone and must run with nothing else on the machine."""
    turn = roles.turn(_flow("dev", tmp_path, ()), "dev-fix", returns=FixResult)

    assert turn.prompt == "dev/prompts/dev-fix.md"
    assert "body_template" not in turn.args
