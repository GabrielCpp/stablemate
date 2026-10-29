"""The repository manifest: location, loading, folds, strays and the last good value."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import pytest

from stablemate_core.config import ConfigError
from stablemate_core.manifest import (
    find_manifest,
    load_manifest,
    locate_manifest,
    parse_manifest_text,
)
from stablemate_core.schema import Manifest, reference_rows, render_reference, yaml_value

_SRC = Path("agents.yml")



def test_every_manifest_key_has_a_meaning_and_an_example():
    """A key declared without its documentation would print as a blank entry in the reference."""
    rows = reference_rows(Manifest)

    assert rows
    assert [r.path for r in rows if not r.description.strip() or not r.examples] == []


def test_the_reference_lists_every_manifest_key_in_yaml():
    text = render_reference(Manifest, title="M", render=yaml_value)

    for row in reference_rows(Manifest):
        assert f"### `{row.path}`" in text
    assert "`agents.codex.skills_from`" in text


def test_agents_yml_wins_over_a_legacy_name(tmp_path):
    (tmp_path / "ostler.yml").write_text("packs: []\n")
    (tmp_path / "agents.yml").write_text("packs: []\n")

    assert locate_manifest(tmp_path) == tmp_path / "agents.yml"


def test_a_legacy_name_is_found_with_a_warning(tmp_path, caplog):
    (tmp_path / ".agents.yml").write_text("packs: []\n")

    with caplog.at_level(logging.WARNING):
        found = locate_manifest(tmp_path)

    assert found == tmp_path / ".agents.yml"
    assert "legacy manifest name" in caplog.text


def test_find_walks_up_to_the_nearest_manifest(tmp_path):
    (tmp_path / "agents.yml").write_text("packs: []\n")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)

    assert find_manifest(deep) == tmp_path / "agents.yml"
    assert find_manifest(Path("/")) is None


def test_the_agents_list_form_enables_exactly_those_harnesses():
    manifest = parse_manifest_text("agents: [claude]\n", _SRC)

    assert manifest.agents.enabled() == {"codex": False, "claude": True, "copilot": False}


def test_a_skills_from_table_enables_and_links():
    manifest = parse_manifest_text(
        "agents:\n  claude: true\n  codex: {skills_from: claude}\n", _SRC
    )

    assert manifest.agents.links() == {"codex": "claude"}
    assert manifest.agents.enabled()["codex"] is True


def test_a_link_to_a_disabled_harness_names_its_key_path():
    with pytest.raises(ConfigError, match=r"agents.*skills_from"):
        parse_manifest_text("agents:\n  codex: {skills_from: claude}\n", _SRC)


def test_vars_merges_into_template_and_template_wins():
    manifest = parse_manifest_text(
        "vars: {a: 1, b: 2}\ntemplate: {b: 3}\n", _SRC
    )

    assert manifest.template.mapping() == {"a": 1, "b": 3}
    assert "vars" not in (manifest.model_extra or {})


def test_workflow_services_and_lint_fold_to_the_top_level():
    manifest = parse_manifest_text(
        "workflow:\n  github_token_env: TOK\n  services:\n    api: {test: pytest}\n  lint:\n    api: ruff\n",
        _SRC,
    )

    assert manifest.workflow.githubTokenEnv == "TOK"
    assert manifest.services["api"].test == "pytest"
    assert manifest.lint == {"api": "ruff"}


def test_the_top_level_services_table_beats_the_workflow_one():
    manifest = parse_manifest_text(
        "services:\n  api: {test: top}\nworkflow:\n  services:\n    api: {test: nested}\n",
        _SRC,
    )

    assert manifest.services["api"].test == "top"


def test_include_readme_keeps_its_old_spellings():
    manifest = parse_manifest_text(
        "localInstructions:\n  - text: hi\n    includeReadme: none\n", _SRC
    )

    assert manifest.localInstructions[0].includeReadme is False


def test_a_local_instruction_that_selects_nothing_is_rejected():
    with pytest.raises(ConfigError, match="localInstructions.0"):
        parse_manifest_text("localInstructions:\n  - paths: ['.']\n", _SRC)


def test_a_bad_hook_manager_names_its_key_path():
    with pytest.raises(ConfigError, match="hooks.manager"):
        parse_manifest_text("hooks: {manager: svn}\n", _SRC)


def test_a_file_scaffold_entry_is_rejected_with_the_migration_hint():
    with pytest.raises(ConfigError, match="scaffold ids"):
        parse_manifest_text("scaffolds:\n  - {path: x}\n", _SRC)


def test_a_top_level_list_is_no_manifest():
    with pytest.raises(ConfigError, match="not a YAML mapping"):
        parse_manifest_text("- a\n", _SRC)


def test_unparsable_yaml_is_a_config_error():
    with pytest.raises(ConfigError, match="could not be read"):
        parse_manifest_text("a: [\n", _SRC)


def test_an_empty_file_is_an_empty_manifest():
    assert parse_manifest_text("", _SRC).packs == []


def test_a_dead_key_is_kept_and_warned_about(tmp_path, caplog):
    path = tmp_path / "agents.yml"
    path.write_text("packs: []\nworkspace: {x: 1}\n")

    with caplog.at_level(logging.WARNING):
        manifest = load_manifest(path)

    assert "workspace" in (manifest.model_extra or {})
    assert "workspace" in caplog.text


def test_the_free_value_tables_never_warn(tmp_path, caplog):
    path = tmp_path / "agents.yml"
    path.write_text("template: {anything: 1}\nrepo: {name: x, custom: 2}\n")

    with caplog.at_level(logging.WARNING):
        load_manifest(path)

    assert caplog.text == ""


def test_a_first_load_that_fails_raises_with_a_key_path(tmp_path):
    path = tmp_path / "agents.yml"
    path.write_text("packs: nope\n")

    with pytest.raises(ConfigError, match="packs"):
        load_manifest(path)


def test_a_reload_that_fails_keeps_the_last_good_manifest(tmp_path, caplog):
    path = tmp_path / "agents.yml"
    path.write_text("packs: [a]\n")
    old = os.stat(path).st_mtime_ns - 10_000_000_000
    os.utime(path, ns=(old, old))
    assert load_manifest(path).packs == ["a"]

    path.write_text("packs: nope\n")
    with caplog.at_level(logging.WARNING):
        kept = load_manifest(path)

    assert kept.packs == ["a"]
    assert "keeping the last good manifest" in caplog.text


def test_an_unchanged_settled_file_is_not_read_again(tmp_path):
    path = tmp_path / "agents.yml"
    path.write_text("packs: [a]\n")
    old = os.stat(path).st_mtime_ns - 10_000_000_000
    os.utime(path, ns=(old, old))

    assert load_manifest(path) is load_manifest(path)


def test_a_top_level_prompts_mapping_folds_into_workflow_prompts(caplog):
    with caplog.at_level(logging.WARNING):
        manifest = parse_manifest_text(
            "prompts:\n  dev-plan: p/plan.md\nworkflow:\n  prompts:\n    fix-ci: p/ci.md\n",
            Path("fold/agents.yml"),
        )

    assert manifest.workflow.prompts == {"dev-plan": "p/plan.md", "fix-ci": "p/ci.md"}
    assert manifest.prompts == []
    assert "legacy shape" in caplog.text


def test_a_top_level_prompts_mapping_wins_per_key():
    manifest = parse_manifest_text(
        "prompts:\n  plan: a.md\nworkflow:\n  prompts:\n    plan: b.md\n    qa: c.md\n", _SRC
    )

    assert manifest.workflow.prompts == {"plan": "a.md", "qa": "c.md"}


def test_a_prompts_list_stays_the_farrier_selection():
    manifest = parse_manifest_text(
        "prompts: [review]\nworkflow:\n  prompts:\n    dev-plan: p/plan.md\n", _SRC
    )

    assert manifest.prompts == ["review"]
    assert manifest.workflow.prompts == {"dev-plan": "p/plan.md"}


def test_a_rewrite_after_the_guard_with_the_mtime_reset_is_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr("stablemate_core.manifest._RACY_NS", 50_000_000)
    path = tmp_path / "agents.yml"
    path.write_text("packs: [a]\n")
    stat = os.stat(path)
    assert load_manifest(path).packs == ["a"]

    time.sleep(0.2)
    path.write_text("packs: [b]\n")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert load_manifest(path).packs == ["b"]
