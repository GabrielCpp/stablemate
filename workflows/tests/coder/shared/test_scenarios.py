"""The plan's Test Scenarios section, and the two escapes read off it.

The regression that matters most is the mixed list: a plan with one QA-only scenario and
one `component` scenario still arms the gate. Deriving the escape from "some scenario has
no test" would disable the red gate for the majority of real plans, which all carry at
least one QA-only entry.
"""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared.scenarios import (
    escape_in_text,
    parse_scenarios,
    plan_escape,
    qa_only_scenarios,
)

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


def test_a_mixed_scenario_list_still_arms_the_gate(tmp_path: Path) -> None:
    assert plan_escape(_plan(tmp_path, MIXED), "plan.md") == ""
    assert escape_in_text(MIXED) == ""


def test_a_list_that_is_entirely_qa_only_derives_the_escape(tmp_path: Path) -> None:
    assert plan_escape(_plan(tmp_path, ALL_QA), "plan.md") == "qa_only"
    assert escape_in_text(ALL_QA) == "qa_only"


def test_the_declared_marker_beats_the_derivation(tmp_path: Path) -> None:
    """A planner that wrote `regression-only` has stated its intent; the parse cannot overrule it."""
    text = "Test scenarios: regression-only\n\n" + ALL_QA
    assert plan_escape(_plan(tmp_path, text), "plan.md") == "regression_only"


def test_the_qa_only_marker_arms_the_escape_over_a_mixed_list(tmp_path: Path) -> None:
    text = "Test scenarios: qa-only\n\n" + MIXED
    assert plan_escape(_plan(tmp_path, text), "plan.md") == "qa_only"


def test_a_plan_with_no_scenario_section_yields_no_escape(tmp_path: Path) -> None:
    """Falling back to TDD costs a rework lap; inventing the escape disables the gate."""
    assert plan_escape(_plan(tmp_path, "## 1. Summary\n\nNothing here.\n"), "plan.md") == ""
    assert escape_in_text("") == ""


def test_a_missing_spec_dir_yields_no_escape() -> None:
    assert plan_escape(None, "plan.md") == ""
    assert qa_only_scenarios(None, "plan.md") == []


def test_the_layer_plan_is_read_before_the_root_plan(tmp_path: Path) -> None:
    _plan(tmp_path, MIXED, "backend-plan.md")
    _plan(tmp_path, ALL_QA, "plan.md")
    assert plan_escape(tmp_path, "backend-plan.md") == ""
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
