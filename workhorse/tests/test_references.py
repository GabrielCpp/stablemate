"""A workflow's prompts name skills by library name, and the run checks them against the harness's catalog."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse._vendor.stablemate_core.skill_refs import (  # noqa: E402
    MissingSkill,
    RetiredHelper,
    SkillCatalog,
    SkillEntry,
)
from workhorse.references import (  # noqa: E402
    MissingReference,
    format_missing,
    helpers_called,
    missing_references,
    referenced_names,
)
from workhorse.templates import render_string  # noqa: E402

HOME_SKILL = Path("/home/dev/.claude/skills")


def _catalog(*names: str) -> SkillCatalog:
    return SkillCatalog.of(
        [SkillEntry(name, name, HOME_SKILL / name / "SKILL.md", ()) for name in names]
    )


def test_every_named_helper_is_scanned() -> None:
    source = "{{ skill_link('a') }} {{ skill_path('b', 'x.md') }} {{ skill_command('c') }}\n"
    assert referenced_names(source) == {("skill", "a"), ("skill", "b"), ("skill", "c")}


def test_calls_inside_blocks_and_filters_are_found() -> None:
    source = (
        "{% if repo.big %}{{ skill_link('deep') | upper }}{% endif %}\n"
        "{% for p in ['1'] %}{{ skill_command('looped') }}{% endfor %}\n"
    )
    assert referenced_names(source) == {("skill", "deep"), ("skill", "looped")}


def test_tag_query_arguments_are_not_skill_names() -> None:
    source = "{{ find_by_tags('web', 'tests') }}{{ find_by_tags('backend') }}"
    assert referenced_names(source) == set()


def test_a_tag_query_beside_a_real_reference_hides_neither() -> None:
    source = "{{ find_by_tags('web') }} {{ skill_link('story-docs') }}"
    assert referenced_names(source) == {("skill", "story-docs")}


def test_reference_behind_a_has_skill_guard_is_not_required() -> None:
    source = "{% if has_skill('flutter') %}{{ skill_link('flutter') }}{% endif %}"
    assert referenced_names(source) == set()


def test_the_guard_only_covers_its_own_branch() -> None:
    source = (
        "{% if has_skill('flutter') %}{{ skill_link('flutter-testing') }}"
        "{% else %}{{ skill_link('go-testing') }}{% endif %}"
    )
    assert referenced_names(source) == {("skill", "go-testing")}


def test_each_elif_is_judged_by_its_own_test() -> None:
    source = (
        "{% if has_skill('flutter') %}{{ skill_link('flutter') }}"
        "{% elif repo.web %}{{ skill_link('react-router') }}{% endif %}"
    )
    assert referenced_names(source) == {("skill", "react-router")}


def test_a_guard_covers_references_nested_deeper_in_its_branch() -> None:
    source = (
        "{% if has_skill('flutter') %}{% for x in ys %}"
        "{{ skill_link('flutter-state') }}{% endfor %}{% endif %}"
    )
    assert referenced_names(source) == set()


def test_an_unguarded_reference_beside_a_guarded_one_is_still_required() -> None:
    source = (
        "{% if has_skill('flutter') %}{{ skill_link('flutter') }}{% endif %}\n"
        "{{ skill_link('developer') }}"
    )
    assert referenced_names(source) == {("skill", "developer")}


def test_non_constant_argument_is_skipped_not_guessed() -> None:
    source = "{{ skill_link(skill_name) }}{{ skill_link('literal') }}"
    assert referenced_names(source) == {("skill", "literal")}


def test_argless_call_is_skipped() -> None:
    assert referenced_names("{{ skill_link() }}") == set()


def test_unrelated_call_is_ignored() -> None:
    assert referenced_names("{{ workhorse_var('story') }}") == set()


def test_a_retired_helper_is_reported_whatever_its_arguments() -> None:
    source = "{{ skill_load_ref('ostler-okf', skill_dir() + '/x') }}{{ isUsingInstruction(n) }}"
    assert referenced_names(source) == {
        ("retired", "skill_load_ref"),
        ("retired", "skill_dir"),
        ("retired", "isUsingInstruction"),
    }


def test_mention_in_prose_is_not_a_call() -> None:
    assert referenced_names("Call `skill_link('story-docs')` to get the link.\n") == set()


def test_unparseable_template_yields_nothing() -> None:
    assert referenced_names("{% if unclosed %}") == set()


def test_helpers_called_names_the_reference_helpers_only() -> None:
    source = "{{ skill_link(x) }}{{ find_by_tags('a') }}{{ has_skill('b') }}{{ prompt_ref('c') }}"
    assert helpers_called(source) == {"skill_link", "find_by_tags", "prompt_ref"}


def _workflow(tmp_path: Path, **prompts: str) -> Path:
    root = tmp_path / "wf"
    (root / "prompts").mkdir(parents=True)
    for name, body in prompts.items():
        (root / "prompts" / f"{name}.md").write_text(body, encoding="utf-8")
    return root


def test_missing_references_names_what_will_not_render(tmp_path: Path) -> None:
    root = _workflow(
        tmp_path,
        plan="{{ skill_link('story-docs') }} {{ skill_command('nope') }}",
        review="{{ prompt_ref('absent') }}",
    )
    assert missing_references(root, _catalog("story-docs")) == [
        MissingReference("skill", "nope", "prompts/plan.md"),
        MissingReference("retired", "prompt_ref", "prompts/review.md"),
    ]


def test_everything_resolving_reports_nothing(tmp_path: Path) -> None:
    root = _workflow(
        tmp_path,
        plan=(
            "{% if has_skill('flutter') %}{{ skill_link('flutter') }}{% endif %}\n"
            "{{ find_by_tags('backend', 'tests') }}\n"
            "{{ skill_command('developer') }}\n"
        ),
    )
    assert missing_references(root, _catalog("developer")) == []


def test_a_flows_own_prompts_are_scanned(tmp_path: Path) -> None:
    root = tmp_path / "wf"
    (root / "dev" / "prompts" / "sub").mkdir(parents=True)
    (root / "dev" / "prompts" / "sub" / "implement.md").write_text("{{ skill_link('x') }}", "utf-8")
    found = missing_references(root, _catalog())
    assert [m.template for m in found] == ["dev/prompts/sub/implement.md"]


def test_docs_outside_prompts_are_not_scanned(tmp_path: Path) -> None:
    root = _workflow(tmp_path, plan="ok")
    (root / "README.md").write_text("{{ skill_link('example-only') }}", encoding="utf-8")
    assert missing_references(root, _catalog()) == []


def test_report_is_stable_across_runs(tmp_path: Path) -> None:
    root = _workflow(
        tmp_path,
        b="{{ skill_link('two') }}{{ skill_link('one') }}",
        a="{{ skill_command('z') }}",
    )
    first = missing_references(root, _catalog())
    assert [(m.template, m.name) for m in first] == [
        ("prompts/a.md", "z"),
        ("prompts/b.md", "one"),
        ("prompts/b.md", "two"),
    ]
    assert missing_references(root, _catalog()) == first


def test_format_missing_names_the_cost_and_the_fix() -> None:
    report = format_missing(
        [
            MissingReference("skill", "story-docs", "prompts/plan.md"),
            MissingReference("retired", "skill_load_ref", "prompts/doc.md"),
        ]
    )
    assert "2 skill reference(s)" in report
    assert "skill 'story-docs' (referenced in prompts/plan.md)" in report
    assert "retired helper `skill_load_ref`" in report
    assert "farrier install" in report


def test_format_missing_of_nothing_is_empty() -> None:
    assert format_missing([]) == ""


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo and a home folder of their own, so the developer's own skills never leak in."""
    home = tmp_path / "home"
    repo = tmp_path / "acme"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CLI", "claude")
    for folder, installed, name in (
        (repo / ".claude/skills", "acme-review", "review"),
        (home / ".claude/skills", "deploy", "deploy"),
    ):
        skill = folder / installed / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            f"---\nname: {installed}\nmetadata:\n  name: {name}\n  tags: [qa]\n---\n",
            encoding="utf-8",
        )
    return repo


def test_a_turn_resolves_repo_and_home_skills_from_its_cwd(workspace: Path) -> None:
    ctx = {"_node_cwd": str(workspace)}
    assert render_string("{{ skill_command('review') }}", ctx) == "/acme-review"
    assert render_string("{{ skill_link('deploy') }}", ctx) == (
        "[deploy](~/.claude/skills/deploy/SKILL.md)"
    )
    assert render_string("{{ find_by_tags('qa') }}", ctx).count("](") == 2


def test_the_harness_picks_the_invocation(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_CLI", "codex")
    (workspace / ".agents/skills/acme-review").mkdir(parents=True)
    (workspace / ".agents/skills/acme-review/SKILL.md").write_text(
        "---\nname: acme-review\nmetadata:\n  name: review\n---\n", encoding="utf-8"
    )
    ctx = {"_node_cwd": str(workspace)}
    assert render_string("{{ skill_command('review') }}", ctx) == "$acme-review"


def test_a_turn_sees_the_skills_of_its_added_dirs(workspace: Path, tmp_path: Path) -> None:
    added = tmp_path / "docs-repo"
    (added / ".claude/skills/style").mkdir(parents=True)
    (added / ".claude/skills/style/SKILL.md").write_text("---\nname: style\n---\n", encoding="utf-8")
    ctx = {"_node_cwd": str(workspace), "_node_add_dirs": [str(added)]}
    assert render_string("{{ has_skill('style') }}", ctx) == "True"
    assert render_string("{{ has_skill('style') }}", {"_node_cwd": str(workspace)}) == "False"


def test_a_named_miss_stops_the_render(workspace: Path) -> None:
    with pytest.raises(MissingSkill):
        render_string("{{ skill_command('absent') }}", {"_node_cwd": str(workspace)})


def test_a_quiet_render_keeps_a_placeholder(workspace: Path) -> None:
    out = render_string("{{ skill_command('absent') }}", {"_node_cwd": str(workspace)}, quiet=True)
    assert out == "generated absent skill when installed"


def test_a_retired_helper_names_its_replacement(workspace: Path) -> None:
    with pytest.raises(RetiredHelper, match="skill_command"):
        render_string("{{ skill_load_ref('review') }}", {"_node_cwd": str(workspace)})


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
