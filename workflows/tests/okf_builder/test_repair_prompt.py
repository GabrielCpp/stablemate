"""`repair.md` dispatches to the fragment written for the item's doctor code."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from ostler import checks
from workhorse.templates import render

import workhorse_workflows
from workhorse_workflows.okf_builder.shared.vocabulary import check_vocabulary

WORKFLOW_DIR = Path(workhorse_workflows.__file__).parent / "okf_builder"
FRAGMENTS = WORKFLOW_DIR / "main" / "prompts" / "repair"


def _context(code: str) -> dict[str, object]:
    return {
        "item_code": code,
        "item_kind": f"fix:{code}",
        "item_target": f"r1:docs/features/acme/concepts/refund.md#refund#{code}",
        "item_context": json.dumps(
            {
                "code": code,
                "node": "refund",
                "path": "docs/features/acme/concepts/refund.md",
                "grounded": False,
                "findings": [{"code": code, "message": "…", "line": 12}],
            }
        ),
        "check_vocabulary": check_vocabulary(),
        "service": "acme",
        "features_root": "docs/features/acme",
        "repo_root": "/repo",
        "source_root": "src",
        "source_excludes": "",
    }


CODES = sorted(p.stem for p in FRAGMENTS.glob("*.md") if p.stem != "_default")


def test_the_fragment_set_is_not_empty() -> None:
    """A glob that matched nothing would make the parametrized test below vacuous."""
    assert CODES, f"no repair fragments found under {FRAGMENTS}"


@pytest.mark.parametrize("code", CODES)
def test_a_known_code_renders_its_own_fragment(code: str) -> None:
    rendered = render("main/prompts/repair.md", _context(code), WORKFLOW_DIR)

    assert f"### `{code}`" in rendered or code in rendered.split("Where the rule bites")[1]
    assert "The finding's own remedy" not in rendered, (
        f"{code} has a fragment but rendered the default"
    )


def test_an_unknown_code_falls_through_to_the_default() -> None:
    rendered = render("main/prompts/repair.md", _context("no-such-doctor-code"), WORKFLOW_DIR)

    assert "The finding's own remedy" in rendered


def test_the_frame_carries_the_item_through() -> None:
    """`workhorse_var` misses render empty, so the item would vanish without a word."""
    rendered = render("main/prompts/repair.md", _context("weak-check"), WORKFLOW_DIR)

    assert "r1:docs/features/acme/concepts/refund.md#refund#weak-check" in rendered
    assert '"grounded": false' in rendered
    assert "Never make a finding go away by removing the claim it was about." in rendered


def test_every_check_signature_reaches_the_prompt() -> None:
    """Naming the vocabulary is not carrying it, and the difference cost a live round."""
    rendered = render("main/prompts/repair.md", _context("undeclared-obligation"), WORKFLOW_DIR)

    for spec in checks.CHECKS:
        assert spec.signature() in rendered, f"{spec.name} is not in the repair prompt"

    assert "they are not in the list" not in rendered


def test_repair_distinguishes_observation_capture_from_comparison_arguments() -> None:
    rendered = render("main/prompts/repair.md", _context("undeclared-obligation"), WORKFLOW_DIR)
    assert "```python\n" in rendered, "Repair needs an executable evidence-acquisition example"
    assert 'except AssertionError as exc:' in rendered
    assert '"message": str(exc)' in rendered
    assert 'json_path(path="exception.type", equals="AssertionError")' in rendered
    assert "comparison arguments only" in rendered
    assert "scenario-owned" in rendered
    assert "never invented" in rendered


def test_a_check_bearing_code_loads_the_falsifiability_bar_and_others_do_not() -> None:
    """The reference is conditional, so both directions are asserted — a guard that always"""
    bar = "ostler-okf/references/falsifiable-verification.md"

    assert bar in render("main/prompts/repair.md", _context("undeclared-obligation"), WORKFLOW_DIR)
    assert bar not in render("main/prompts/repair.md", _context("missing-placement"), WORKFLOW_DIR)
