"""Runtime rendering of library prompts against a farrier context manifest."""
from __future__ import annotations

import importlib

import pytest

from workhorse.templates import render_string

wm = importlib.import_module("workhorse.manifest")


MANIFEST = {
    "template": {"backend_layer_name": "Go gateway"},
    "repo": {"name": "demo", "prefix": "demo"},
    "instructions": {"go": ".claude/skills/demo-go/SKILL.md"},
    "skill_dir": ".claude/skills",
}


def _ctx(**extra):
    return {**wm.build_manifest_context(MANIFEST).as_context(), **extra}


def test_build_manifest_context_names_what_it_read(tmp_path):
    mc = wm.build_manifest_context(MANIFEST, repo_root=str(tmp_path))
    assert mc.present
    assert mc.values["template"]["backend_layer_name"] == "Go gateway"
    assert mc.repo_root == str(tmp_path.resolve())


def test_the_reserved_keys_round_trip_through_one_type():
    """`as_context` writes the `_`-prefixed keys and `from_context` reads them back, so a rename is one edit and neither half can drift."""
    mc = wm.build_manifest_context(MANIFEST)
    back = wm.ManifestContext.from_context(mc.as_context())
    assert back.present
    assert back.repo_root == mc.repo_root


def test_the_skill_maps_of_an_older_manifest_stay_out_of_the_context():
    assert set(_ctx()) == {"template", "repo", "_repo_root"}


def test_an_absent_manifest_adds_no_context_key():
    """The manifest-free case is a value, not a None, and it contributes nothing."""
    assert wm.ManifestContext().as_context() == {}
    assert not wm.ManifestContext.from_context({}).present


def test_a_wrong_typed_field_degrades_instead_of_raising():
    """farrier's file is another tool's output: an unknown key is ignored and a wrong-typed one falls back to its default."""
    mc = wm.build_manifest_context({**MANIFEST, "vars": "x", "future_key": {"a": 1}})
    assert "vars" not in mc.values
    assert mc.values["repo"]["name"] == "demo"


def test_template_value_resolves():
    assert render_string("{{ template.backend_layer_name }}", _ctx()) == "Go gateway"


def test_a_turn_without_a_cwd_resolves_skills_from_the_manifest_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_CLI", "claude")
    skill = tmp_path / ".claude/skills/demo-go/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: demo-go\nmetadata:\n  name: go\n---\n", encoding="utf-8")
    ctx = wm.build_manifest_context(MANIFEST, repo_root=str(tmp_path)).as_context()
    assert render_string("{{ skill_command('go') }}", ctx) == "/demo-go"


def test_explicit_missing_context_file_is_hard_error():
    with pytest.raises(SystemExit):
        wm.load_context_manifest("/tmp/definitely-not-a-manifest-12345.json")


def test_absent_auto_detected_manifest_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    mc = wm.load_context_manifest(None)
    assert not mc.present and mc.as_context() == {}
