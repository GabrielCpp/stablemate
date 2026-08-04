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


TAGGED = {
    **MANIFEST,
    "instructions": {
        **MANIFEST["instructions"],
        "go-errors": ".claude/skills/demo-go-errors/SKILL.md",
        "demo-go-errors": ".claude/skills/demo-go-errors/SKILL.md",
    },
    "instruction_tags": {
        "go": ["backend", "standards", "runbook"],
        "react-router": ["web", "standards", "runbook"],
        "go-errors": ["backend", "tests"],
        "demo-go-errors": ["backend", "tests"],
    },
}


def _tagged_ctx():
    return wm.build_manifest_context(TAGGED).as_context()


def test_instruction_tags_round_trip_through_one_type():
    """The tag map rides the same reserved-key round trip as the path maps, so a prompt
    rendered from a resumed run queries exactly what the original run queried."""
    mc = wm.build_manifest_context(TAGGED)
    assert mc.instruction_tags["go"] == ["backend", "standards", "runbook"]
    back = wm.ManifestContext.from_context(mc.as_context())
    assert back.instruction_tags == mc.instruction_tags


def test_an_older_manifest_without_tags_matches_nothing():
    """farrier's file is another tool's output and may predate tags entirely. A tag
    query on it has to render empty — the sentence around it then disappears — rather
    than raise or, worse, fall back to naming every installed skill."""
    mc = wm.build_manifest_context(MANIFEST)
    assert mc.instruction_tags == {}
    assert render_string("{{ find_by_tags('web') }}", _ctx()) == ""


def test_a_wrong_typed_tag_map_degrades_instead_of_raising():
    mc = wm.build_manifest_context({**MANIFEST, "instruction_tags": ["web"]})
    assert mc.instruction_tags == {}


def test_find_by_tags_narrows_as_tags_are_added():
    """AND, not OR: `backend` is the layer, `tests` is the capability, and asking for
    both is how a prompt says "however this repo tests its backend" without knowing
    that this repo spells it `go-errors`."""
    ctx = _tagged_ctx()
    assert render_string("{{ find_by_tags('backend') }}", ctx) == (
        "`.claude/skills/demo-go-errors/SKILL.md`, `.claude/skills/demo-go/SKILL.md`"
    )
    assert render_string("{{ find_by_tags('backend', 'tests') }}", ctx) == (
        "`.claude/skills/demo-go-errors/SKILL.md`"
    )


def test_find_by_tags_answers_one_path_per_skill_however_many_aliases():
    """farrier indexes one skill under several names; counting names would list the
    same file twice in a sentence the agent then reads as two skills."""
    out = render_string("{{ find_by_tags('tests') }}", _tagged_ctx())
    assert out == "`.claude/skills/demo-go-errors/SKILL.md`"


def test_find_by_tags_is_empty_for_an_unmatched_or_empty_query():
    """Empty is falsy, so the surrounding prose can guard on it. And an *empty* query
    is empty rather than everything: `find_by_tags()` asks for no capability in
    particular, and answering with the whole library is the opposite of a query."""
    ctx = _tagged_ctx()
    assert render_string("{{ find_by_tags('mobile') }}", ctx) == ""
    assert render_string("{{ find_by_tags() }}", ctx) == ""
    assert render_string(
        "{{ find_by_tags('mobile') | default('(none installed)', true) }}", ctx
    ) == "(none installed)"


def test_find_by_tags_is_case_insensitive_and_takes_a_list():
    """A tag is a query key: `Web` failing to match `web` would be a silent miss, and
    a prompt that computed its tags has a list rather than positional arguments."""
    ctx = _tagged_ctx()
    expected = "`.claude/skills/demo-react-router/SKILL.md`"
    assert render_string("{{ find_by_tags('WEB') }}", ctx) == expected
    assert render_string("{{ find_by_tags(['web', 'standards']) }}", ctx) == expected


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


# --- skill_load_ref: the imperative sibling of instruction_ref --------------------


def test_skill_load_ref_names_the_installed_command_not_the_asked_for_one(monkeypatch):
    """farrier installs `go` as `demo-go`, so `/go` is a slash command no repo has.

    The Claude branch used to emit the caller's bare argument, which meant the one
    helper whose whole job is "load this skill" named a nonexistent one on every
    Claude run — the default backend.
    """
    monkeypatch.setenv("AGENT_CLI", "claude")
    assert render_string("{{ skill_load_ref('go') }}", _ctx()) == "/demo-go"


def test_skill_load_ref_reads_the_resolved_path_on_a_read_the_file_harness(monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "aider")
    out = render_string("{{ skill_load_ref('go') }}", _ctx())
    assert out.startswith("Read `") and out.endswith("and follow its instructions")
    assert "demo-go/SKILL.md" in out


def test_skill_load_ref_resolves_through_a_pack_namespace(monkeypatch):
    """Same resolver as every other helper: an exact-key lookup missed a namespaced
    skill here while `instruction_ref` found it, so the two disagreed about one file."""
    monkeypatch.setenv("AGENT_CLI", "claude")
    assert render_string("{{ skill_load_ref('story-docs') }}", _ns_ctx()) == (
        "/demo-process-story-docs"
    )


def test_skill_load_ref_unresolved_still_describes_where_the_skill_would_live(monkeypatch):
    """Nothing resolves, so the caller's fallback path stands and the command is the
    bare name — the honest answer for a skill this repo has not installed, and
    unchanged from before the resolver was wired in."""
    monkeypatch.setenv("AGENT_CLI", "claude")
    ctx = _ctx()
    assert render_string("{{ skill_load_ref('nope', 'x/nope/SKILL.md') }}", ctx) == "/nope"
    monkeypatch.setenv("AGENT_CLI", "aider")
    assert render_string("{{ skill_load_ref('nope', 'x/nope/SKILL.md') }}", ctx) == (
        "Read `x/nope/SKILL.md` and follow its instructions"
    )


if __name__ == "__main__":
    import subprocess
    import sys

    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
