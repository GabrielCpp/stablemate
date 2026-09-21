"""Every code `ostler doctor` can emit is classified here on purpose."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import workhorse_workflows.okf_builder as okf_builder_pkg
from ostler import doctor
from workhorse_workflows.okf_builder.shared.checkpoint import (
    _CODE_FAMILIES,
    GROUNDED_CODES,
    NON_ACTIONABLE_CODES,
)

REPAIR_DIR = Path(okf_builder_pkg.__file__).parent / "main" / "prompts" / "repair"

DEFAULT_PROMPT_CODES = frozenset({
    "ambiguous-locator",
    "bad-heading-type",
    "dangling-code-ref",
    "dangling-link",
    "directory-code-ref",
    "duplicate-container-heading",
    "extends-type-mismatch",
    "fixture-arg-mismatch",
    "fixture-needs-cycle",
    "fixture-needs-target-args",
    "fixture-secret-name",
    "fixture-step-kind",
    "fixture-step-no-run",
    "fixture-undeclared-provides",
    "invalid-role",
    "malformed-declaration",
    "malformed-defect",
    "malformed-placement",
    "missing-anchor",
    "missing-required-bullet",
    "missing-required-section",
    "no-root-screen",
    "okf-missing-type",
    "overlong-normative-bullet",
    "qa-fixture-bullet",
    "schema",
    "stale-declaration",
    "stale-defect",
    "unaddressable-selector",
    "undecodable-code-symbol",
    "unknown-book-fixture",
    "unknown-type",
    "unnamed-interactive",
    "unparsed-capture",
    "unreachable-screen",
    "unreadable",
    "unresolved-extends",
    "unresolved-relation",
})

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
    "story-id-mismatch",
    "story-key-collision",
    "story-conflict",
    "orphan-seed",
    "qa-fixture-declaration",
    "runbook-bad-kind",
    "runbook-bad-reuse",
    "runbook-incomplete",
    "runbook-local-only",
    "runbook-missing",
    "runbook-multi-service",
    "runbook-scenario-frame",
    "story-covers-no-seed",
    "story-fixture-stray",
    "story-section-order",
    "story-status-mismatch",
    "unclassified-seed",
    "undeclared-story-fixture",
    "unknown-story-fixture",
    "unmigrated-fixture-declaration",
    "unused-story-fixture",
    "unwritten-story",
})


def _emitted_codes() -> set[str]:
    """The codes `doctor.py` constructs `Finding`s with, read off its AST."""
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


BUILDER_CODES = frozenset({"stale-citation", "dangling"})


def _fragment_codes() -> set[str]:
    return {p.stem for p in REPAIR_DIR.glob("*.md")} - {"_default"}


def test_every_doctor_code_is_classified_on_purpose() -> None:
    emitted = _emitted_codes()
    fragments = _fragment_codes()
    classified = fragments | DEFAULT_PROMPT_CODES | ORG_GRAPH_CODES | NON_ACTIONABLE_CODES

    unclassified = emitted - classified
    assert not unclassified, (
        f"doctor emits codes okf-builder has never classified: {sorted(unclassified)}. "
        f"Write a fragment under {REPAIR_DIR}, or add each to DEFAULT_PROMPT_CODES / "
        f"ORG_GRAPH_CODES in this file — on purpose, with a reviewer."
    )

    retired = classified - emitted - BUILDER_CODES
    assert not retired, (
        f"classified codes doctor no longer emits: {sorted(retired)} — a rename upstream, "
        f"and whatever fragment or set entry carries the old name is now dead."
    )


def test_the_buckets_do_not_overlap() -> None:
    """One classification per code — a fragment beside a DEFAULT entry is a contradiction."""
    fragments = _fragment_codes()
    assert not fragments & DEFAULT_PROMPT_CODES
    assert not fragments & ORG_GRAPH_CODES
    assert not fragments & NON_ACTIONABLE_CODES
    assert not DEFAULT_PROMPT_CODES & ORG_GRAPH_CODES
    assert not DEFAULT_PROMPT_CODES & NON_ACTIONABLE_CODES
    assert not ORG_GRAPH_CODES & NON_ACTIONABLE_CODES


def test_the_drain_order_and_grounding_name_real_codes() -> None:
    """A rename upstream must not quietly strip a code of its rank or its grounding."""
    emitted = _emitted_codes()
    for family in _CODE_FAMILIES:
        assert family <= emitted, sorted(family - emitted)
    assert GROUNDED_CODES <= emitted, sorted(GROUNDED_CODES - emitted)
