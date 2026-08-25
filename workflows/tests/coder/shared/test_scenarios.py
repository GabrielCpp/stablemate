"""The plan's Test Scenarios section, and the QA-only subset the QA lane reads."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared.scenarios import parse_scenarios, qa_only_scenarios

MIXED = """\
## 5. Test Scenarios

### Scenario 1: The cache is reused on a second read
- **AC:** 1
- **Level:** component — through the loader's public surface

### Scenario 2: The refreshed page looks right
- **AC:** 3
- **Level:** QA-only — visual layout, no assertable surface
"""

ALL_QA = """\
## 5. Test Scenarios

### Scenario 1: The refreshed page looks right
- **AC:** 1
- **Level:** QA-only — visual layout

### Scenario 2: The flow crosses both apps
- **AC:** 2
- **Level:** e2e
"""


def _plan(tmp_path: Path, text: str, name: str = "plan.md") -> Path:
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_scenarios_are_parsed_with_their_ac_and_level() -> None:
    scenarios = parse_scenarios(MIXED)
    assert [s.title for s in scenarios] == [
        "The cache is reused on a second read",
        "The refreshed page looks right",
    ]
    assert [s.ac for s in scenarios] == ["1", "3"]
    assert [s.writes_no_test for s in scenarios] == [False, True]


def test_a_plan_with_no_scenario_section_yields_no_scenarios() -> None:
    assert parse_scenarios("## 1. Summary\n\nNothing here.\n") == []


def test_a_missing_spec_dir_yields_no_obligations() -> None:
    assert qa_only_scenarios(None, "plan.md") == []


def test_the_layer_plan_is_read_before_the_root_plan(tmp_path: Path) -> None:
    _plan(tmp_path, MIXED, "backend-plan.md")
    _plan(tmp_path, ALL_QA, "plan.md")
    assert [s.title for s in qa_only_scenarios(tmp_path, "backend-plan.md")] == [
        "The refreshed page looks right"
    ]


def test_qa_only_scenarios_is_the_no_test_subset_of_a_mixed_list(tmp_path: Path) -> None:
    scenarios = qa_only_scenarios(_plan(tmp_path, MIXED), "plan.md")
    assert [s.title for s in scenarios] == ["The refreshed page looks right"]


def test_the_section_ends_at_the_next_heading(tmp_path: Path) -> None:
    """A `### Scenario` under a later section is not this section's."""
    text = ALL_QA + "\n## 6. Verification Commands\n\n### Scenario 9: not one of ours\n"
    assert [s.title for s in parse_scenarios(text)] == [
        "The refreshed page looks right",
        "The flow crosses both apps",
    ]


def test_the_unnumbered_heading_parses_like_the_numbered_one() -> None:
    """`## Test Scenarios` and `## 5. Test Scenarios` name the same section.

    `plan-story.md` dropped the number when the seven-section inventory collapsed to four;
    `_words` was already discarding a leading `5.`, so both spellings live in real plans.
    """
    assert parse_scenarios(MIXED.replace("## 5. Test", "## Test")) == parse_scenarios(MIXED)


def test_the_prompts_own_scenario_example_parses() -> None:
    """The example in `plan-story.md` must be a shape this parser reads.

    It was not: the prompt asked for a numbered list, the parser wants one `###` heading per
    scenario, and a real run's plan therefore yielded zero scenarios — the QA lane received
    no QA-only obligations at all and nothing said so. Pinning the prompt's own example
    against the parser is what makes that divergence loud instead of silent.
    """
    prompt = (
        Path(__file__).parents[3]
        / "src/workhorse_workflows/coder/dev/prompts/plan-story.md"
    ).read_text(encoding="utf-8")
    start = prompt.index("### Test Scenarios")
    example = prompt[prompt.index("```markdown", start) + len("```markdown") :]
    example = example[: example.index("```")]

    # The block is the body of the section, so it is parsed under that section's heading.
    parsed = parse_scenarios("## Test Scenarios\n" + example)
    assert [(s.ac, s.level) for s in parsed] == [("2", "endpoint")], parsed
