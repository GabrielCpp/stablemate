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

wm = importlib.import_module("workhorse.manifest")


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
    return {**wm.build_manifest_context(MANIFEST).as_context(), **extra}


def test_build_manifest_context_names_what_it_read():
    mc = wm.build_manifest_context(MANIFEST)
    assert mc.present
    assert mc.instructions["go"] == ".claude/skills/demo-go/SKILL.md"
    assert mc.used_skills == ("go", "react-router")
    assert mc.skill_dir == ".claude/skills"
    assert mc.values["template"]["backend_layer_name"] == "Go gateway"


def test_the_reserved_keys_round_trip_through_one_type():
    """`as_context` writes the `_`-prefixed keys and `from_context` reads them back —
    the two halves are one type, so a rename is one edit and neither half can drift."""
    mc = wm.build_manifest_context(MANIFEST)
    back = wm.ManifestContext.from_context(mc.as_context())
    assert back.present
    assert back.instructions == mc.instructions
    assert back.prompts == mc.prompts
    assert back.used_skills == mc.used_skills
    assert back.skill_dir == mc.skill_dir
    assert back.repo_root == mc.repo_root


def test_an_absent_manifest_adds_no_context_key():
    """The manifest-free case is a value, not a None — and it contributes nothing, so
    a run without one renders exactly the arguments its state passed."""
    assert wm.ManifestContext().as_context() == {}
    assert not wm.ManifestContext.from_context({}).present


def test_a_wrong_typed_field_degrades_instead_of_raising():
    """farrier's file is another tool's output: an unknown key is ignored and a
    wrong-typed one falls back to its default. A manifest workhorse cannot fully read
    must not end a week-long run."""
    mc = wm.build_manifest_context(
        {**MANIFEST, "used_skills": "go", "skill_dir": 7, "future_key": {"a": 1}},
        backend="claude",
    )
    assert mc.used_skills == ()
    assert mc.skill_dir == ".claude/skills"  # the backend's, since the file's was junk
    assert mc.instructions["go"] == ".claude/skills/demo-go/SKILL.md"


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


def test_codex_backend_rewrites_skill_paths():
    mc = wm.build_manifest_context(MANIFEST, backend="codex")
    assert mc.instructions["go"] == ".agents/skills/demo-go/SKILL.md"
    assert mc.instructions["react-router"] == ".agents/skills/demo-react-router/SKILL.md"
    assert mc.skill_dir == ".agents/skills"


def test_copilot_backend_rewrites_skill_paths():
    mc = wm.build_manifest_context(MANIFEST, backend="copilot")
    assert mc.instructions["go"] == ".github/skills/demo-go/SKILL.md"
    assert mc.skill_dir == ".github/skills"


def test_same_backend_no_rewrite():
    mc = wm.build_manifest_context(MANIFEST, backend="claude")
    assert mc.instructions["go"] == ".claude/skills/demo-go/SKILL.md"
    assert mc.skill_dir == ".claude/skills"


def test_old_manifest_no_skill_dir_no_rewrite():
    old_manifest = {k: v for k, v in MANIFEST.items() if k != "skill_dir"}
    mc = wm.build_manifest_context(old_manifest, backend="codex")
    assert mc.instructions["go"] == ".claude/skills/demo-go/SKILL.md"


def test_unknown_backend_falls_back_to_manifest_dir():
    mc = wm.build_manifest_context(MANIFEST, backend="future-cli")
    assert mc.instructions["go"] == ".claude/skills/demo-go/SKILL.md"
    assert mc.skill_dir == ".claude/skills"


def test_explicit_missing_context_file_is_hard_error():
    # An explicitly-passed --context-file that doesn't exist is a hard error.
    with pytest.raises(SystemExit):
        wm.load_context_manifest("/tmp/definitely-not-a-manifest-12345.json")


def test_absent_auto_detected_manifest_returns_empty(monkeypatch, tmp_path):
    # No --context-file and no repo manifest → absent (manifest-free workflows run).
    monkeypatch.setenv("AGENT_REPO_DIR", str(tmp_path))
    mc = wm.load_context_manifest(None)
    assert not mc.present and mc.as_context() == {}


# ── namespaced skills ─────────────────────────────────────────────────────────
# A prompt asks for a capability ("story-docs"); a pack is free to namespace the skill that
# provides it ("process/process-story-docs", installed as "process-story-docs"). Exact-only
# lookup made those miss each other, and the miss was silent — the placeholder rendered into
# the prompt as prose, handing the agent "generated story-docs instruction file when
# installed" where a path belonged. Live consequence: the author workflow's epic-split gate
# failed and escalated to its auto-resolver.

NAMESPACED = {
    **MANIFEST,
    "instructions": {
        "go": ".claude/skills/demo-go/SKILL.md",
        # Farrier indexes one skill under several aliases — bare and repo-prefixed.
        "process-story-docs": ".claude/skills/demo-process-story-docs/SKILL.md",
        "demo-process-story-docs": ".claude/skills/demo-process-story-docs/SKILL.md",
        "process/process-story-docs": ".claude/skills/demo-process-story-docs/SKILL.md",
    },
}


def _ns_ctx():
    return wm.build_manifest_context(NAMESPACED).as_context()


def test_instruction_ref_resolves_through_a_pack_namespace():
    out = render_string("{{ instruction_ref('story-docs') }}", _ns_ctx())
    assert out == ".claude/skills/demo-process-story-docs/SKILL.md"


def test_aliases_of_one_skill_are_not_treated_as_ambiguous():
    """Uniqueness is judged on the resolved path, not the key. Counting keys would make every
    namespaced skill look ambiguous with itself (bare vs repo-prefixed alias) and resolve to
    nothing — which is how this first appeared to be unfixable."""
    ctx = _ns_ctx()
    assert len([k for k in NAMESPACED["instructions"] if k.endswith("-story-docs")]) > 1
    assert render_string("{{ instruction_ref('story-docs') }}", ctx).endswith("SKILL.md")


def test_genuinely_ambiguous_suffix_does_not_guess():
    """Two different skills both ending in the requested name is a real ambiguity. Silently
    picking one is a worse failure than not resolving, so it falls back to the placeholder."""
    ambiguous = {
        **MANIFEST,
        "instructions": {
            "alpha-story-docs": ".claude/skills/demo-alpha-story-docs/SKILL.md",
            "beta-story-docs": ".claude/skills/demo-beta-story-docs/SKILL.md",
        },
    }
    out = render_string("{{ instruction_ref('story-docs') }}",
                        wm.build_manifest_context(ambiguous).as_context())
    assert "generated story-docs instruction file when installed" in out


def test_exact_match_still_wins_over_a_suffix_match():
    exact = {
        **MANIFEST,
        "instructions": {
            "story-docs": ".claude/skills/demo-story-docs/SKILL.md",
            "process-story-docs": ".claude/skills/demo-process-story-docs/SKILL.md",
        },
    }
    out = render_string("{{ instruction_ref('story-docs') }}",
                        wm.build_manifest_context(exact).as_context())
    assert out == ".claude/skills/demo-story-docs/SKILL.md"


if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
