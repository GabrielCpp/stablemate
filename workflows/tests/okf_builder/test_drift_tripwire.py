"""Every code `ostler doctor` can emit is classified here on purpose.

The August drift happened silently: ostler grew `unminted-claim`,
`relation-without-subject` and the placement checks while okf-builder's prompts stayed
frozen, so the newest codes fell through to the generic repair fragment with no guidance
and the books rotted against a contract nobody had transcribed. This test is the
tripwire: it reads the codes straight out of `doctor`'s source, and every one must be
either

* **fragment-covered** — a file under `main/prompts/repair/` written for that defect,
* in `DEFAULT_PROMPT_CODES` — someone decided `_default.md` (plus the `grounded` flag in
  the item context, where it applies) is enough, or
* in `ORG_GRAPH_CODES` — the epic/story/milestone/backlog/runbook planning graph, which a
  features-book drain never sees.

When ostler adds a code, this fails, and someone classifies it deliberately — writes a
fragment, or argues in a review why the default suffices. The freeze cannot recur
silently.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import workhorse_workflows.okf_builder as okf_builder_pkg
from ostler import doctor
from workhorse_workflows.okf_builder.shared.checkpoint import _CODE_FAMILIES, GROUNDED_CODES

REPAIR_DIR = Path(okf_builder_pkg.__file__).parent / "main" / "prompts" / "repair"

#: Codes whose finding names its own remedy well enough for the generic fragment —
#: mechanical rewrites (`unknown-bullet`, `bad-heading-type`), structural repairs whose
#: target is in the message (`dangling-link`, `missing-anchor`), and the grounded codes
#: whose fragment-worthy sibling already carries the pattern (`ambiguous-locator` rides
#: the `grounded` flag the same way `missing-placement`'s fragment describes).
DEFAULT_PROMPT_CODES = frozenset({
    "ambiguous-locator",
    "bad-heading-type",
    "dangling-code-ref",
    "dangling-link",
    "duplicate-container-heading",
    "empty-required-section",
    "invalid-role",
    "malformed-placement",
    "missing-anchor",
    "missing-required-bullet",
    "missing-required-section",
    "no-entry-point",
    "okf-missing-type",
    "overlong-normative-bullet",
    "qa-fixture-bullet",
    "schema",
    "unknown-book-fixture",
    "unknown-bullet",
    "unknown-type",
    "unnamed-interactive",
    "unreachable-screen",
    "unreadable",
    "unresolved-relation",
})

#: Codes about the planning graph — epics, stories, seeds, milestones, the backlog, story
#: QA runbooks and fixture declarations. They live outside `docs/features/`, so
#: `scoped_findings` never hands them to this workflow's drain.
ORG_GRAPH_CODES = frozenset({
    "backlog-item-in-multiple-milestones",
    "cross-epic-dependency",
    "cross-epic-seed",
    "dangling-dependency",
    "dangling-milestone-dependency",
    "dangling-milestone-epic",
    "dangling-seed",
    "epic-in-multiple-milestones",
    "epic-without-milestone",
    "frozen-mutated",
    "frozen-removed",
    "malformed-dependency-bullet",
    "milestone-cycle",
    "missing-story-file",
    "orphan-seed",
    "qa-fixture-declaration",
    "runbook-bad-kind",
    "runbook-bad-reuse",
    "runbook-incomplete",
    "runbook-local-only",
    "runbook-missing",
    "runbook-multi-service",
    "story-covers-no-seed",
    "story-fixture-stray",
    "story-status-mismatch",
    "unclassified-seed",
    "undeclared-story-fixture",
    "unknown-story-fixture",
    "unused-story-fixture",
    "unwritten-story",
})


def _emitted_codes() -> set[str]:
    """The codes `doctor.py` constructs `Finding`s with, read off its AST.

    A grep would match prose and suggestions; the AST matches only the second argument
    (or `code=`) of a `Finding(...)` call. The one non-literal spelling in the file is a
    variable bound by a conditional expression over two literals
    (`"missing-required-section" if … else "empty-required-section"`), so string
    constants from `IfExp` assignments resolve it; any other dynamic shape is itself
    drift and fails loudly.
    """
    tree = ast.parse(inspect.getsource(doctor))
    ifexp_strings: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.IfExp):
            arms = {
                arm.value
                for arm in (node.value.body, node.value.orelse)
                if isinstance(arm, ast.Constant) and isinstance(arm.value, str)
            }
            for target in node.targets:
                if isinstance(target, ast.Name) and arms:
                    ifexp_strings.setdefault(target.id, set()).update(arms)

    codes: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "Finding"):
            continue
        arg = node.args[1] if len(node.args) >= 2 else None
        for kw in node.keywords:
            if kw.arg == "code":
                arg = kw.value
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            codes.add(arg.value)
        elif isinstance(arg, ast.Name) and ifexp_strings.get(arg.id):
            codes.update(ifexp_strings[arg.id])
        else:
            raise AssertionError(
                f"doctor.py line {node.lineno}: a Finding whose code this tripwire cannot "
                f"read statically — give it a literal (or a two-literal conditional)"
            )
    return codes


def _fragment_codes() -> set[str]:
    return {p.stem for p in REPAIR_DIR.glob("*.md")} - {"_default"}


def test_every_doctor_code_is_classified_on_purpose() -> None:
    emitted = _emitted_codes()
    fragments = _fragment_codes()
    classified = fragments | DEFAULT_PROMPT_CODES | ORG_GRAPH_CODES

    unclassified = emitted - classified
    assert not unclassified, (
        f"doctor emits codes okf-builder has never classified: {sorted(unclassified)}. "
        f"Write a fragment under {REPAIR_DIR}, or add each to DEFAULT_PROMPT_CODES / "
        f"ORG_GRAPH_CODES in this file — on purpose, with a reviewer."
    )

    retired = classified - emitted
    assert not retired, (
        f"classified codes doctor no longer emits: {sorted(retired)} — a rename upstream, "
        f"and whatever fragment or set entry carries the old name is now dead."
    )


def test_the_buckets_do_not_overlap() -> None:
    """One classification per code — a fragment beside a DEFAULT entry is a contradiction."""
    fragments = _fragment_codes()
    assert not fragments & DEFAULT_PROMPT_CODES
    assert not fragments & ORG_GRAPH_CODES
    assert not DEFAULT_PROMPT_CODES & ORG_GRAPH_CODES


def test_the_drain_order_and_grounding_name_real_codes() -> None:
    """A rename upstream must not quietly strip a code of its rank or its grounding.

    Both sets steer behavior by string match: a code missing from `_CODE_FAMILIES` still
    drains (just last), and one missing from `GROUNDED_CODES` still repairs (just without
    the read-the-source demand) — so a stale name fails soft everywhere but here.
    """
    emitted = _emitted_codes()
    for family in _CODE_FAMILIES:
        assert family <= emitted, sorted(family - emitted)
    assert GROUNDED_CODES <= emitted, sorted(GROUNDED_CODES - emitted)
