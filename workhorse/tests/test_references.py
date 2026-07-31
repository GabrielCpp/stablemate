"""Preflight for unresolvable skill/prompt references (workhorse/references.py).

The bug being guarded: an `instruction_ref("x")` that resolves to nothing renders the
prose "generated x instruction file when installed" into a live agent prompt and says
nothing about it. These cover the static scan that names those references before the
run, and the render-time warning that catches the ones a static scan cannot see.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse.references import (  # noqa: E402
    MissingReference,
    format_missing,
    missing_references,
    referenced_names,
    resolve_instruction,
)
from workhorse.templates import render_string  # noqa: E402


# --- the scan -------------------------------------------------------------------


def test_every_helper_alias_is_scanned() -> None:
    """The aliases are the point of parsing instead of grepping for one name."""
    source = (
        "{{ instruction_ref('a') }} {{ instruction_file('b') }} {{ skill_file('c') }}\n"
        "{{ prompt_ref('d') }} {{ prompt_file('e') }}\n"
    )
    assert referenced_names(source) == {
        ("skill", "a"),
        ("skill", "b"),
        ("skill", "c"),
        ("prompt", "d"),
        ("prompt", "e"),
    }


def test_calls_inside_blocks_and_filters_are_found() -> None:
    """A call is a call wherever the AST puts it — statement, filter arg, or nested."""
    source = (
        "{% if repo.big %}{{ instruction_ref('deep') | upper }}{% endif %}\n"
        "{% for p in ['1'] %}{{ prompt_ref('looped') }}{% endfor %}\n"
    )
    assert referenced_names(source) == {("skill", "deep"), ("prompt", "looped")}


# --- optional references: the plural helpers and the installed-skill guard --------


def test_plural_helper_arguments_are_never_required() -> None:
    """`instruction_refs` asks which of these the repo has; absent IS the answer."""
    source = "{{ instruction_refs('go', 'flutter', 'pulumi') }}{{ prompt_refs('a', 'b') }}"
    assert referenced_names(source) == set()


def test_plural_aliases_are_optional_too() -> None:
    source = "{{ instruction_files('x') }}{{ skill_files('y') }}{{ prompt_files('z') }}"
    assert referenced_names(source) == set()


def test_tag_query_arguments_are_not_skill_names() -> None:
    """`find_by_tags('web', 'tests')` names a capability, not a file. Descending into
    it would report every tag in every prompt as a missing skill — the preflight would
    be all noise on precisely the prompts that stopped hard-coding skill names."""
    source = "{{ find_by_tags('web', 'tests') }}{{ find_by_tags('backend') }}"
    assert referenced_names(source) == set()


def test_a_tag_query_beside_a_real_reference_hides_neither() -> None:
    source = "{{ find_by_tags('web') }} {{ instruction_ref('story-docs') }}"
    assert referenced_names(source) == {("skill", "story-docs")}


def test_a_prompt_of_tag_queries_reports_nothing(tmp_path: Path) -> None:
    """The whole-workflow scan, not just the AST walk: a prompt that asks only by
    capability is unresolvable-by-nothing however thin the repo's manifest is."""
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "qa.md").write_text(
        "{{ find_by_tags('backend', 'tests') }}\n", encoding="utf-8"
    )
    assert missing_references(tmp_path, {"_instructions": {"go": "skills/go.md"}}) == []


def test_reference_behind_an_installed_skill_guard_is_not_required() -> None:
    """A Go repo must not fail preflight for the Flutter branch it never renders."""
    source = "{% if isUsingInstruction('flutter') %}{{ instruction_ref('flutter') }}{% endif %}"
    assert referenced_names(source) == set()


def test_the_guard_only_covers_its_own_branch() -> None:
    """`else` renders precisely when the skill is absent, so its refs are required."""
    source = (
        "{% if isUsingInstruction('flutter') %}{{ instruction_ref('flutter-testing') }}"
        "{% else %}{{ instruction_ref('go-testing') }}{% endif %}"
    )
    assert referenced_names(source) == {("skill", "go-testing")}


def test_each_elif_is_judged_by_its_own_test() -> None:
    source = (
        "{% if isUsingInstruction('flutter') %}{{ instruction_ref('flutter') }}"
        "{% elif repo.web %}{{ instruction_ref('react-router') }}{% endif %}"
    )
    assert referenced_names(source) == {("skill", "react-router")}


def test_a_guard_covers_references_nested_deeper_in_its_branch() -> None:
    source = (
        "{% if isUsingInstruction('flutter') %}{% for x in ys %}"
        "{{ instruction_ref('flutter-state') }}{% endfor %}{% endif %}"
    )
    assert referenced_names(source) == set()


def test_an_unguarded_reference_beside_a_guarded_one_is_still_required() -> None:
    """The guard is positional — it must not leak to the rest of the template."""
    source = (
        "{% if isUsingInstruction('flutter') %}{{ instruction_ref('flutter') }}{% endif %}\n"
        "{{ instruction_ref('developer') }}"
    )
    assert referenced_names(source) == {("skill", "developer")}


def test_guarded_prompts_are_not_reported_by_the_workflow_preflight(tmp_path: Path) -> None:
    """End to end: the false positive that made --dry-run fail on a non-Flutter repo."""
    root = _workflow(
        tmp_path,
        plan=(
            "{% if isUsingInstruction('flutter') %}{{ instruction_ref('flutter') }}{% endif %}\n"
            "{{ instruction_refs('go', 'flutter', 'pulumi') }}\n"
            "{{ instruction_ref('developer') }}\n"
        ),
    )
    context = {"_instructions": {"go": "go.md", "developer": "dev.md"}, "_prompts": {}}
    assert missing_references(root, context) == []


def test_non_constant_argument_is_skipped_not_guessed() -> None:
    source = "{{ instruction_ref(skill_name) }}{{ instruction_ref('literal') }}"
    assert referenced_names(source) == {("skill", "literal")}


def test_argless_call_is_skipped() -> None:
    assert referenced_names("{{ instruction_ref() }}") == set()


def test_unrelated_call_is_ignored() -> None:
    assert referenced_names("{{ workhorse_var('story') }}{{ skill_dir() }}") == set()


def test_mention_in_prose_is_not_a_call() -> None:
    """The reason this is a Jinja parse: prose about the helper is not a reference."""
    source = "Call `instruction_ref('story-docs')` to get the path.\n"
    assert referenced_names(source) == set()


def test_unparseable_template_yields_nothing() -> None:
    """The syntax error belongs to the render; reporting it twice helps nobody."""
    assert referenced_names("{% if unclosed %}") == set()


# --- resolution -----------------------------------------------------------------


def test_exact_match_wins() -> None:
    assert resolve_instruction({"story-docs": "a.md"}, "story-docs") == "a.md"


def test_unique_suffix_resolves_through_pack_namespacing() -> None:
    instructions = {"process-story-docs": ".agents/skills/process-story-docs/SKILL.md"}
    assert resolve_instruction(instructions, "story-docs") == instructions["process-story-docs"]


def test_aliases_of_one_skill_are_not_an_ambiguity() -> None:
    """Farrier indexes one skill under several keys; uniqueness is judged on the path."""
    path = ".agents/skills/process-story-docs/SKILL.md"
    instructions = {"process-story-docs": path, "acme-process-story-docs": path}
    assert resolve_instruction(instructions, "story-docs") == path


def test_two_packs_ending_the_same_way_resolve_to_nothing() -> None:
    instructions = {"a-story-docs": "a.md", "b-story-docs": "b.md"}
    assert resolve_instruction(instructions, "story-docs") is None


def test_unknown_name_resolves_to_nothing() -> None:
    assert resolve_instruction({"other": "o.md"}, "story-docs") is None


# --- the workflow-level preflight -----------------------------------------------


def _workflow(tmp_path: Path, **prompts: str) -> Path:
    root = tmp_path / "wf"
    (root / "prompts").mkdir(parents=True)
    for name, body in prompts.items():
        (root / "prompts" / f"{name}.md").write_text(body, encoding="utf-8")
    return root


def test_missing_references_names_what_will_not_resolve(tmp_path: Path) -> None:
    root = _workflow(
        tmp_path,
        plan="{{ instruction_ref('story-docs') }} {{ instruction_ref('nope') }}",
        review="{{ prompt_ref('absent') }}",
    )
    context = {"_instructions": {"story-docs": "a.md"}, "_prompts": {}}
    assert missing_references(root, context) == [
        MissingReference("skill", "nope", "prompts/plan.md"),
        MissingReference("prompt", "absent", "prompts/review.md"),
    ]


def test_everything_resolving_reports_nothing(tmp_path: Path) -> None:
    root = _workflow(tmp_path, plan="{{ instruction_ref('story-docs') }}{{ prompt_ref('p') }}")
    context = {"_instructions": {"story-docs": "a.md"}, "_prompts": {"p": "p.md"}}
    assert missing_references(root, context) == []


def test_nested_prompt_directories_are_scanned(tmp_path: Path) -> None:
    root = tmp_path / "wf"
    (root / "prompts" / "sub").mkdir(parents=True)
    (root / "prompts" / "sub" / "deep.md").write_text("{{ instruction_ref('x') }}", "utf-8")
    found = missing_references(root, {"_instructions": {}})
    assert [m.template for m in found] == ["prompts/sub/deep.md"]


def test_docs_outside_prompts_are_not_scanned(tmp_path: Path) -> None:
    """A workflow's README showing the helper in a fenced example is not a defect."""
    root = _workflow(tmp_path, plan="ok")
    (root / "README.md").write_text("{{ instruction_ref('example-only') }}", encoding="utf-8")
    assert missing_references(root, {"_instructions": {}}) == []


def test_no_manifest_at_all_is_skipped_whole(tmp_path: Path) -> None:
    """hello-world and most tests run manifest-free: unresolved is their normal state."""
    root = _workflow(tmp_path, plan="{{ instruction_ref('anything') }}")
    assert missing_references(root, {}) == []


def test_a_manifest_missing_only_prompts_still_checks_skills(tmp_path: Path) -> None:
    root = _workflow(tmp_path, plan="{{ instruction_ref('gone') }}")
    found = missing_references(root, {"_instructions": {"other": "o.md"}})
    assert [(m.kind, m.name) for m in found] == [("skill", "gone")]


def test_report_is_stable_across_runs(tmp_path: Path) -> None:
    root = _workflow(
        tmp_path,
        b="{{ instruction_ref('two') }}{{ instruction_ref('one') }}",
        a="{{ prompt_ref('z') }}",
    )
    context = {"_instructions": {}, "_prompts": {}}
    first = missing_references(root, context)
    assert [(m.template, m.name) for m in first] == [
        ("prompts/a.md", "z"),
        ("prompts/b.md", "one"),
        ("prompts/b.md", "two"),
    ]
    assert missing_references(root, context) == first


def test_format_missing_names_the_cost_and_the_fix() -> None:
    report = format_missing([MissingReference("skill", "story-docs", "prompts/plan.md")])
    assert "1 reference" in report
    assert "story-docs" in report
    assert "prompts/plan.md" in report
    assert "agents.yml" in report


def test_format_missing_of_nothing_is_empty() -> None:
    assert format_missing([]) == ""


# --- the render-time warning ----------------------------------------------------


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture()
def captured() -> Iterator[list[str]]:
    handler = _Capture()
    logger = logging.getLogger("workhorse.templates")
    logger.addHandler(handler)
    try:
        yield handler.messages
    finally:
        logger.removeHandler(handler)


def test_unresolved_reference_still_renders_the_placeholder(captured: list[str]) -> None:
    """Fail soft: the prompt keeps a sentence the agent can read. It is just not silent."""
    out = render_string("{{ instruction_ref('gone') }}", {"_instructions": {"o": "o.md"}})
    assert out == "generated gone instruction file when installed"
    assert any("gone" in m for m in captured)


def test_resolved_reference_says_nothing(captured: list[str]) -> None:
    out = render_string("{{ instruction_ref('here') }}", {"_instructions": {"here": "h.md"}})
    assert out == "h.md"
    assert captured == []


def test_manifest_free_render_says_nothing(captured: list[str]) -> None:
    """No manifest means nothing was ever expected to resolve — warning would be noise."""
    render_string("{{ instruction_ref('gone') }}", {})
    assert captured == []


def test_quiet_render_says_nothing(captured: list[str]) -> None:
    """Telemetry labels re-render before every node; warning there means thousands of lines."""
    render_string("{{ prompt_ref('gone') }}", {"_prompts": {}}, quiet=True)
    assert captured == []


# --- the plural helpers at render time ------------------------------------------


def test_instruction_refs_renders_only_what_the_repo_installed(captured: list[str]) -> None:
    """The whole point: a Go repo is never told to read a Flutter skill."""
    context = {"_instructions": {"go": "skills/go.md", "pulumi": "skills/pulumi.md"}}
    out = render_string("{{ instruction_refs('go', 'flutter', 'pulumi') }}", context)
    assert out == "`skills/go.md`, `skills/pulumi.md`"
    assert "flutter" not in out
    # …and dropping a name the repo never installed is not worth a warning either.
    assert captured == []


def test_instruction_refs_of_nothing_installed_is_empty_and_falsy() -> None:
    """Empty is what lets `{% if %}` drop the sentence instead of leaving 'e.g. '."""
    source = "{% set r = instruction_refs('flutter', 'flutter-testing') %}{% if r %}e.g. {{ r }}{% endif %}"
    assert render_string(source, {"_instructions": {"go": "g.md"}}) == ""


def test_instruction_refs_accepts_a_list_as_well_as_varargs() -> None:
    context = {"_instructions": {"go": "g.md", "pulumi": "p.md"}}
    source = "{% set names = ['go', 'flutter', 'pulumi'] %}{{ instruction_refs(names) }}"
    assert render_string(source, context) == "`g.md`, `p.md`"


def test_instruction_refs_dedupes_aliases_of_one_skill() -> None:
    """Farrier indexes one skill under several names; that is one file, not two."""
    path = "skills/process-story-docs/SKILL.md"
    context = {"_instructions": {"process-story-docs": path, "acme-process-story-docs": path}}
    out = render_string("{{ instruction_refs('process-story-docs', 'story-docs') }}", context)
    assert out == f"`{path}`"


def test_prompt_refs_drops_the_absent_ones() -> None:
    context = {"_prompts": {"triage": "p/triage.md"}}
    assert render_string("{{ prompt_refs('triage', 'gone') }}", context) == "`p/triage.md`"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
