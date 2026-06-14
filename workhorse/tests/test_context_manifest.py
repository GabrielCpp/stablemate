"""Runtime rendering of library prompts against a farrier context manifest.

Workflows now run directly from the agent library; farrier emits a per-repo
``agents-context.json`` instead of copying/rendering prompts. These tests pin the
contract the runtime helpers (workhorse/templates.py) rely on:

  - the manifest's path maps / selected-skills set back the farrier helpers
  - ``isUsingInstruction`` is a real bool and ``touched_layers`` gates per story
  - a missing manifest is a hard error (no silent install-time fallback)
"""
from __future__ import annotations

import importlib

import pytest

from workhorse.templates import render_string

wm = importlib.import_module("workhorse.main")


MANIFEST = {
    "template": {"backend_layer_name": "Go gateway"},
    "repo": {"name": "demo", "prefix": "demo"},
    "instructions": {
        "go": ".claude/skills/demo-go/SKILL.md",
        "react-router": ".claude/skills/demo-react-router/SKILL.md",
    },
    "prompts": {"plan-story": ".claude/commands/demo-plan-story.md"},
    "used_skills": ["go", "react-router"],
    "skill_dir": ".claude/skills",
}


def _ctx(**extra):
    return {**wm._build_manifest_context(MANIFEST), **extra}


def test_build_manifest_context_shapes_reserved_keys():
    ctx = wm._build_manifest_context(MANIFEST)
    assert ctx["_instructions"]["go"] == ".claude/skills/demo-go/SKILL.md"
    assert ctx["_used_skills"] == ["go", "react-router"]
    assert ctx["_skill_dir"] == ".claude/skills"
    assert ctx["template"]["backend_layer_name"] == "Go gateway"


def test_instruction_ref_resolves_from_manifest():
    out = render_string("{{ instruction_ref('go') }}", _ctx())
    assert out == ".claude/skills/demo-go/SKILL.md"


def test_instruction_ref_unknown_returns_placeholder_not_crash():
    out = render_string("{{ instruction_ref('nope') }}", _ctx())
    assert "generated nope instruction file when installed" in out


def test_is_using_instruction_is_real_bool():
    assert render_string("{{ isUsingInstruction('go') }}", _ctx()) == "True"
    assert render_string("{{ isUsingInstruction('flutter') }}", _ctx()) == "False"


def test_template_value_resolves():
    assert render_string("{{ template.backend_layer_name }}", _ctx()) == "Go gateway"


def test_touched_layers_gates_per_story():
    tmpl = (
        "{%- set layers = (plan_result.touched_layers if plan_result is mapping else []) "
        "| default([], true) %}"
        "{% if ('go' in layers) or (not layers and isUsingInstruction('go')) %}GO{% endif %}"
        "{% if ('react-router' in layers) or (not layers and isUsingInstruction('react-router')) %}WEB{% endif %}"
    )
    web_only = render_string(tmpl, _ctx(plan_result={"touched_layers": ["react-router"]}))
    assert "WEB" in web_only and "GO" not in web_only

    backend_only = render_string(tmpl, _ctx(plan_result={"touched_layers": ["go"]}))
    assert "GO" in backend_only and "WEB" not in backend_only

    # No touched_layers → fall back to repo capability (used_skills).
    fallback = render_string(tmpl, _ctx(plan_result={"status": "done"}))
    assert "GO" in fallback and "WEB" in fallback


def test_codex_backend_rewrites_skill_paths(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "codex")
    ctx = wm._build_manifest_context(MANIFEST)
    assert ctx["_instructions"]["go"] == ".agents/skills/demo-go/SKILL.md"
    assert ctx["_instructions"]["react-router"] == ".agents/skills/demo-react-router/SKILL.md"
    assert ctx["_skill_dir"] == ".agents/skills"


def test_copilot_backend_rewrites_skill_paths(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "copilot")
    ctx = wm._build_manifest_context(MANIFEST)
    assert ctx["_instructions"]["go"] == ".github/skills/demo-go/SKILL.md"
    assert ctx["_skill_dir"] == ".github/skills"


def test_same_backend_no_rewrite(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "claude")
    ctx = wm._build_manifest_context(MANIFEST)
    assert ctx["_instructions"]["go"] == ".claude/skills/demo-go/SKILL.md"
    assert ctx["_skill_dir"] == ".claude/skills"


def test_old_manifest_no_skill_dir_no_rewrite(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "codex")
    old_manifest = {k: v for k, v in MANIFEST.items() if k != "skill_dir"}
    ctx = wm._build_manifest_context(old_manifest)
    assert ctx["_instructions"]["go"] == ".claude/skills/demo-go/SKILL.md"


def test_unknown_backend_falls_back_to_manifest_dir(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "future-cli")
    ctx = wm._build_manifest_context(MANIFEST)
    assert ctx["_instructions"]["go"] == ".claude/skills/demo-go/SKILL.md"
    assert ctx["_skill_dir"] == ".claude/skills"


def test_explicit_missing_context_file_is_hard_error():
    # An explicitly-passed --context-file that doesn't exist is a hard error.
    with pytest.raises(SystemExit):
        wm._load_context_manifest("/tmp/definitely-not-a-manifest-12345.json")


def test_absent_auto_detected_manifest_returns_empty(monkeypatch, tmp_path):
    # No --context-file and no repo manifest → empty (manifest-free workflows run).
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    assert wm._load_context_manifest(None) == {}
