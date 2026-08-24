"""`farrier library --check` exists because the failure it names is invisible everywhere else.

``_front_matter`` answers malformed YAML with ``{}``, so a skill whose fence does not
parse still installs — it just loses its description, its ``applyTo`` and its ``tags`` on
the way, and every downstream symptom (a thin description, a tag query that returns
nothing) reads like an authoring choice. When this check was first run against the real
library it found 36 of 130 skills in exactly that state, whole stacks of them, silently.

So the tests that matter here are of two kinds. The first pins the shapes that actually
broke — the ones an author writes on purpose because they look correct. The second pins
what must *not* be reported, because a checker that cries about `tags: [go, backend]`
teaches people to run it with their eyes closed; both false-positive tests below are
regressions from a first draft that reported 130 warnings and 34 errors that were not.

    ./.venv/bin/python -m pytest tests/test_library_check.py
"""

from __future__ import annotations

from pathlib import Path

from farrier.frontmatter import _front_matter
from farrier.library_check import check_library, check_text, format_findings


def _codes(text: str, path: Path | None = None, **kwargs) -> list[str]:
    # The default path's directory is `t` so it agrees with `_skill`'s default `name:`;
    # a mismatch there is its own finding and would show up in every unrelated assertion.
    return [f.code for f in check_text(text, path or Path("skills/t/SKILL.md"), **kwargs)]


def _skill(front: str, *, name: str = "t") -> str:
    return f"---\nname: {name}\ndescription: A thing\ntags: [go]\n{front}---\n\n# Thing\n\nRules.\n"


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --- the three shapes that actually broke the library -------------------------------


def test_a_glob_starting_with_a_star_is_an_unparsable_error():
    """`applyTo: **/*.go` — `*` opens a YAML alias. 94 real skills were written this way."""
    assert _codes(_skill("applyTo: **/*.go\n")) == ["unparsable"]


def test_a_template_expression_starting_with_a_brace_is_an_unparsable_error():
    """`{` opens a flow mapping, so every templated `applyTo` in the library died here."""
    assert _codes(_skill("applyTo: {{ app.dir }}/**/*.dart\n")) == ["unparsable"]


def test_a_double_quoted_value_containing_an_inner_quote_is_an_unparsable_error():
    """The scalar ends at the inner `"`; this is what survived the first repair pass."""
    text = '---\nname: t\ndescription: "Work in {{ x | default("app") }}"\ntags: [go]\n---\n\n# T\n'
    assert _codes(text) == ["unparsable"]


def test_the_quoted_spelling_of_all_three_is_clean():
    """Every `unparsable` message prescribes single quotes — so single quotes must pass."""
    assert _codes(_skill("applyTo: '**/*.go'\n")) == []
    assert _codes(_skill("applyTo: '{{ app.dir }}/**/*.dart'\n")) == []
    assert _codes('---\nname: t\ndescription: \'Use {{ x | default("app") }}\'\ntags: [go]\n---\n\n# T\n') == []


def test_unparsable_is_exactly_the_case_farrier_reads_as_no_front_matter():
    """The finding's whole claim: what this reports is what the renderer silently loses."""
    broken = _skill("applyTo: **/*.go\n")
    assert _front_matter(broken) == {}
    assert "unparsable" in _codes(broken)

    intact = _skill("applyTo: '**/*.go'\n")
    assert _front_matter(intact)["tags"] == ["go"]


# --- values YAML accepts but reads as something other than the text written ---------


def test_an_unquoted_hash_truncates_the_value_and_is_an_error():
    """YAML accepts this, so nothing errors — the value just quietly gets shorter."""
    text = "---\nname: t\ndescription: Use for API work # and the CLI\ntags: [go]\n---\n\n# T\n"
    findings = check_text(text, Path("skills/t/SKILL.md"))
    assert [f.code for f in findings] == ["truncated-by-comment"]
    assert "'Use for API work'" in findings[0].message


def test_a_value_starting_with_an_indicator_that_happens_to_parse_is_a_warning():
    """`description: &ref A thing` parses — to `'A thing'`, the `&ref` eaten as an anchor."""
    text = "---\nname: t\ndescription: &ref A thing\ntags: [go]\n---\n\n# T\n"
    assert _codes(text) == ["fragile"]


def test_an_unquoted_template_expression_mid_value_is_a_warning():
    text = "---\nname: t\ndescription: Rules for {{ repo.name }} services\ntags: [go]\n---\n\n# T\n"
    assert _codes(text) == ["fragile"]


# --- what must NOT be reported ------------------------------------------------------


def test_a_tag_yaml_reads_as_a_bool_or_null_is_reported_with_the_name_it_installs_under():
    """`[on, docs]` installs `true`: no tag goes missing, one is just spelled otherwise."""
    findings = check_text("---\nname: t\ntags: [on, docs]\ndescription: A\n---\n\n# T\n", Path("skills/t/SKILL.md"))
    assert [f.code for f in findings] == ["tag-retyped"]
    assert "installs as `true`" in findings[0].message

    for word, installed in (("no", "false"), ("null", "none"), ("~", "none")):
        text = f"---\nname: t\ntags: [{word}, docs]\ndescription: A\n---\n\n# T\n"
        assert [f.code for f in check_text(text, Path("skills/t/SKILL.md"))] == ["tag-retyped"], word
        assert f"installs as `{installed}`" in check_text(text, Path("skills/t/SKILL.md"))[0].message


def test_quoting_a_retyped_tag_is_the_fix_the_message_prescribes():
    assert _codes("---\nname: t\ntags: ['on', docs]\ndescription: A\n---\n\n# T\n") == []


def test_the_real_tag_vocabulary_needs_no_quoting():
    """The answer to "should these be quoted": no — they are plain scalars YAML keeps."""
    vocab = "standards, planning, docs, go, backend, cli, web, mobile, infra, entrypoint, tests, qa, codegen, runbook"
    assert _codes(f"---\nname: t\ntags: [{vocab}]\ndescription: A\n---\n\n# T\n") == []


def test_a_flow_sequence_is_the_documented_spelling_for_tags_not_a_fragile_value():
    """Regression: `[` is an indicator, so a first draft flagged all 130 tagged skills."""
    assert _codes(_skill("")) == []
    assert _codes("---\nname: t\ndescription: A thing\ntags: [go, backend, tests]\n---\n\n# T\n") == []


def test_a_missing_name_is_not_reported_at_all():
    """Regression: farrier derives the installed name from the path, never from this key."""
    assert _codes("---\ndescription: A thing\ntags: [go]\n---\n\n# T\n") == []


def test_a_quoted_colon_or_brace_is_clean_wherever_it_appears():
    assert _codes("---\nname: t\ndescription: 'Use for a: b work'\ntags: [go]\n---\n\n# T\n") == []


def test_a_prompt_is_not_asked_for_tags():
    """A prompt is addressed by name and answers no capability query."""
    text = "---\nagent: agent\ndescription: Write an epic\n---\n\n# Write\n"
    assert check_text(text, Path("prompts/write.md"), require_tags=False) == []


# --- the advisory findings ----------------------------------------------------------


def test_a_skill_with_no_tags_is_warned_but_not_failed():
    findings = check_text("---\nname: t\ndescription: A thing\n---\n\n# T\n", Path("skills/t/SKILL.md"))
    assert [(f.code, f.level) for f in findings] == [("untagged", "warning")]


def test_a_missing_description_is_warned_because_the_fallback_restates_the_title():
    assert "missing-description" in _codes("---\nname: t\ntags: [go]\n---\n\n# T\n")


def test_a_name_that_disagrees_with_its_directory_is_warned():
    """farrier installs under the directory name, so the key misleads only the reader."""
    findings = check_text(_skill("", name="qa-acme-local"), Path("skills/acme/qa-local/SKILL.md"))
    assert [f.code for f in findings] == ["name-mismatch"]
    assert "qa-local" in findings[0].message


def test_a_name_matching_its_directory_is_silent():
    assert check_text(_skill("", name="qa-local"), Path("skills/acme/qa-local/SKILL.md")) == []


# --- structural failures ------------------------------------------------------------


def test_a_file_with_no_fence_is_an_error_and_stops_further_checks():
    findings = check_text("# Just a heading\n\nProse.\n", Path("skills/t/SKILL.md"))
    assert [f.code for f in findings] == ["no-frontmatter"]


def test_front_matter_that_is_not_a_mapping_is_an_error():
    assert _codes("---\n- one\n- two\n---\n\n# T\n") == ["not-a-mapping"]


def test_crlf_front_matter_is_read_the_same_as_lf():
    assert _codes(_skill("applyTo: '**/*.go'\n").replace("\n", "\r\n")) == []


# --- walking a library --------------------------------------------------------------


def test_check_library_reads_skills_and_prompts_and_counts_what_it_read(tmp_path):
    root = tmp_path / "library"
    _write(root, "skills/go/api/SKILL.md", _skill("", name="api"))
    _write(root, "skills/go/cli/SKILL.md", _skill("applyTo: **/*.go\n", name="cli"))
    _write(root, "prompts/write.md", "---\nagent: agent\ndescription: Write\n---\n\n# Write\n")

    findings, checked = check_library([root])

    assert checked == 3
    assert [f.code for f in findings] == ["unparsable"]


def test_a_bundled_reference_without_front_matter_is_not_a_source(tmp_path):
    """`references/api.md` carries no fence by design — only files making claims count."""
    root = tmp_path / "library"
    _write(root, "skills/go/api/SKILL.md", _skill("", name="api"))
    _write(root, "skills/go/api/references/api.md", "# Endpoints\n\nProse.\n")
    _write(root, "prompts/shared/snippet.md", "Just prose.\n")

    findings, checked = check_library([root])

    assert (findings, checked) == ([], 1)


def test_an_overlay_layer_shadowing_a_base_file_is_checked_once(tmp_path):
    """Layers are walked in precedence order; the same resolved path must not double-report."""
    root = tmp_path / "library"
    _write(root, "skills/go/api/SKILL.md", _skill("applyTo: **/*.go\n", name="api"))

    findings, checked = check_library([root, root])

    assert (len(findings), checked) == (1, 1)


# --- the report ---------------------------------------------------------------------


def test_errors_print_before_warnings_so_a_truncated_terminal_shows_what_fails(tmp_path):
    root = tmp_path / "library"
    _write(root, "skills/go/api/SKILL.md", "---\nname: api\ndescription: A\n---\n\n# A\n")
    _write(root, "skills/go/cli/SKILL.md", _skill("applyTo: **/*.go\n", name="cli"))

    findings, checked = check_library([root])
    report = format_findings(findings, checked, root)

    lines = [line for line in report.split("\n") if line]
    assert lines[0].startswith("error:") and lines[1].startswith("warning:")
    assert lines[0].startswith("error: skills/go/cli/SKILL.md")  # rendered relative to root
    assert lines[-1] == "1 error(s), 1 warning(s) across 2 sources"


def test_a_clean_library_says_so_rather_than_printing_nothing():
    assert format_findings([], 12) == "ok: 12 library sources, all front matter parses"


def test_a_stuttering_basename_warns_and_names_the_installed_name(tmp_path):
    """Never an error: both spellings install identically, so the source is fine."""
    skill = tmp_path / "library" / "skills" / "flutter" / "flutter-api" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: flutter-api\ndescription: x\ntags: [a]\n---\n\nBody.\n",
        encoding="utf-8",
    )

    findings, _ = check_library([tmp_path / "library"])

    stutter = [f for f in findings if f.code == "group-stutter"]
    assert [f.level for f in stutter] == ["warning"]
    assert "'flutter-api'" in stutter[0].message


def test_a_basename_that_merely_starts_like_its_folder_is_not_a_stutter(tmp_path):
    """`go/gopls` is not `go/go-pls`: the collapse keys on a segment boundary."""
    skill = tmp_path / "library" / "skills" / "go" / "gopls" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: gopls\ndescription: x\ntags: [a]\n---\n\nBody.\n", encoding="utf-8"
    )

    findings, _ = check_library([tmp_path / "library"])

    assert [f for f in findings if f.code == "group-stutter"] == []
