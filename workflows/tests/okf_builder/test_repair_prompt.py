"""`repair.md` dispatches to the fragment written for the item's doctor code.

The dispatch is one `{% include %}` over a *list* of candidates — the fragment named by
`item_code`, then `_default.md`. Jinja renders the first that exists, which is what makes a
code nobody wrote a fragment for fall through to the generic remedy instead of raising
`TemplateNotFound` mid-run and killing the drain.

Two things are easy to get wrong here and neither shows up until a live run:

- the include path is resolved against the **workflow package directory**, not the prompt's
  own directory, so `"repair/<code>.md"` — anything short of the full
  `"main/prompts/repair/<code>.md"` — silently misses and every item renders the default;
- `item_code` reaches the template through `workhorse_var`, so a node that forgets to pass it
  renders the empty string, misses every candidate, and again yields the default.

Both failure modes are *silent* — the prompt still renders, just with the wrong instructions
— so they are asserted on the rendered text rather than on the template source.
"""
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


#: Every fragment that exists, keyed by the code it is written for, minus the fallback.
CODES = sorted(p.stem for p in FRAGMENTS.glob("*.md") if p.stem != "_default")


def test_the_fragment_set_is_not_empty() -> None:
    """A glob that matched nothing would make the parametrized test below vacuous."""
    assert CODES, f"no repair fragments found under {FRAGMENTS}"


@pytest.mark.parametrize("code", CODES)
def test_a_known_code_renders_its_own_fragment(code: str) -> None:
    rendered = render("main/prompts/repair.md", _context(code), WORKFLOW_DIR)

    # The fragment's own heading is the marker: each one opens with `### `<code>` — …`.
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
    assert "Never make a finding go away by removing what it was about." in rendered


def test_every_check_signature_reaches_the_prompt() -> None:
    """Naming the vocabulary is not carrying it, and the difference cost a live round.

    A repair turn told that `ostler checks` lists the signatures wrote `count(subject=…,
    expected=1)` and `visible(locator="PDFEngine output", …)` — an argument that does not
    exist and a UI check on a byte slice — and every one came back as a fresh
    `unparsed-check`. The list is short, so it is in the prompt rather than a directory away.
    """
    rendered = render("main/prompts/repair.md", _context("undeclared-obligation"), WORKFLOW_DIR)

    for spec in checks.CHECKS:
        assert spec.signature() in rendered, f"{spec.name} is not in the repair prompt"


def test_a_check_bearing_code_loads_the_falsifiability_bar_and_others_do_not() -> None:
    """The reference is conditional, so both directions are asserted — a guard that always

    fires costs every repair turn the read, and one that never fires silently drops the
    standard the check-bearing fragments are written against.
    """
    bar = "ostler-okf/references/falsifiable-verification.md"

    assert bar in render("main/prompts/repair.md", _context("undeclared-obligation"), WORKFLOW_DIR)
    assert bar not in render("main/prompts/repair.md", _context("missing-placement"), WORKFLOW_DIR)
