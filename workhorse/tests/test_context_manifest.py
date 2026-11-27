"""Runtime rendering of library prompts against the repo's agents.yml."""
from __future__ import annotations

import importlib

import pytest

from workhorse.templates import render_string

wm = importlib.import_module("workhorse.manifest")


AGENTS_YML = """\
repo:
  prefix: demo
template:
  backend_layer_name: Go gateway
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "agents.yml").write_text(AGENTS_YML, encoding="utf-8")
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    return tmp_path


def _ctx(**extra):
    return {**wm.load_context_manifest().as_context(), **extra}


def test_agents_yml_gives_template_vars_and_repo(repo):
    mc = wm.load_context_manifest()
    assert mc.present
    assert mc.values["template"] == {"backend_layer_name": "Go gateway"}
    assert mc.values["vars"] == mc.values["template"]
    assert mc.values["repo"]["prefix"] == "demo"
    assert mc.values["repo"]["root"] == "."
    assert mc.repo_root == str(repo.resolve())


def test_the_reserved_keys_round_trip_through_one_type(repo):
    """`as_context` writes the `_`-prefixed keys and `from_context` reads them back, so a rename is one edit and neither half can drift."""
    mc = wm.load_context_manifest()
    back = wm.ManifestContext.from_context(mc.as_context())
    assert back.present
    assert back.repo_root == mc.repo_root


def test_the_context_holds_only_the_agents_yml_sections(repo):
    assert set(_ctx()) == {"template", "repo", "vars", "_repo_root"}


def test_an_absent_manifest_adds_no_context_key():
    """The manifest-free case is a value, not a None, and it contributes nothing."""
    assert wm.ManifestContext().as_context() == {}
    assert not wm.ManifestContext.from_context({}).present


def test_template_value_resolves(repo):
    assert render_string("{{ template.backend_layer_name }}", _ctx()) == "Go gateway"


def test_a_turn_without_a_cwd_resolves_skills_from_the_manifest_repo(repo, monkeypatch):
    monkeypatch.setenv("HOME", str(repo / "home"))
    monkeypatch.setenv("AGENT_CLI", "claude")
    skill = repo / ".claude/skills/demo-go/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo-go\nmetadata:\n  name: go\n---\n", encoding="utf-8")
    assert render_string("{{ skill_command('go') }}", _ctx()) == "/demo-go"


def test_no_agents_yml_gives_an_empty_context(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    mc = wm.load_context_manifest()
    assert not mc.present and mc.as_context() == {}


def test_an_invalid_agents_yml_gives_an_empty_context(monkeypatch, tmp_path):
    (tmp_path / "agents.yml").write_text("- a\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    assert not wm.load_context_manifest().present
