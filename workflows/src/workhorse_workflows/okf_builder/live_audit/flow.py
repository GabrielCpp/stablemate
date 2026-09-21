"""Live behavioral audit lane: real pass/fail per claim, fingerprinted against the ledger."""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ostler import model
from ostler.path import features_root as features_root_of, specs_root_in
from ostler.qa import runbook
from ostler.qa.compile import Refusal, compile_plan_gaps
from ostler.qa.context import book_context
from ostler.qa.plan import load_plan, resolve_spec_dir
from ostler.refs import code_refs
from ostler.source_snapshots import book_repository
from pydantic import BaseModel, ConfigDict
from workhorse.pyflow import Done, Workflow

from workhorse_workflows.kit import find_docs_root, find_repo_root
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.ledger import (
    claim_fingerprint, load_ledger, needs_rerun, record_result,
)
from workhorse_workflows.qa.runner import ensure_stack, run_qa_plan
from workhorse_workflows.qa.schemas import StackStatus

LEDGER_FILE = "qa-ledger.json"

_COMPILED_RUN_ROOT = ".qa-live-audit"

BOOK_TARGET = "(book)"


class ScenarioResult(BaseModel):
    """One scenario's real verdict, plus what the ledger needs to judge a re-run."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    assertions: int = 0
    failures: int = 0
    message: str = ""
    code_refs: tuple[str, ...] = ()
    fingerprint: str = ""
    changed: bool = True
    source: str = "fresh"


class LiveAuditReport(BaseModel):
    """One spec directory's outcome: either blocked before anything ran, or a real run."""

    model_config = ConfigDict(extra="forbid")

    spec_dir: str
    status: str
    stack: StackStatus | None = None
    scenarios: tuple[ScenarioResult, ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()
    notes: str = ""


def _node_text(node: Any) -> str:
    """A stable text rendering of one book node, for fingerprinting its content."""
    return "\n".join(f"{key}: {value}" for key, value, _line in node.bullet_order)


def _fixture_texts_for(
    covers: list[Any],
    obligations_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, Any],
) -> dict[str, str]:
    """Every fixture node text a scenario's covered obligations declare, keyed by node id."""
    texts: dict[str, str] = {}
    for cover_id in covers:
        obligation = obligations_by_id.get(str(cover_id))
        if not obligation:
            continue
        for row in obligation.get("fixturesDeclared") or []:
            name = row.get("name") if isinstance(row, dict) else None
            if not name or name in texts:
                continue
            node = nodes_by_id.get(name)
            if node is not None:
                texts[name] = _node_text(node)
    return texts


def _covered_node_ids(covers: list[Any]) -> list[str]:
    """Every `okf:<node-id>:<suffix>`-shaped covers id's middle segment, in order."""
    ids: list[str] = []
    for item in covers:
        text = str(item)
        if not text.startswith("okf:"):
            continue
        parts = text.split(":")
        if len(parts) >= 3:
            ids.append(":".join(parts[1:-1]))
    return ids


_STRICT_MODE_VIOLATION_RE = re.compile(r"strict mode violation:.*resolved to \d+ elements", re.DOTALL)


def _strict_mode_violation_gaps(
    covers: Sequence[Any], message: str
) -> list[dict[str, Any]] | None:
    """Finding 8: a Playwright strict-mode violation is a book gap, never a failed check."""
    hit = _STRICT_MODE_VIOLATION_RE.search(message)
    if hit is None:
        return None
    obligation_ids = [str(item) for item in covers if str(item).startswith("okf:")]
    if not obligation_ids:
        return None
    detail = (
        "a Playwright strict-mode violation: the compiled locator resolved to more than "
        f"one element on the rendered page ({hit.group(0)}) — the book names this subject "
        "imprecisely; this can never mean the app is wrong"
    )
    return [
        {"obligation_id": obligation_id, "kind": "unresolved-precondition", "detail": detail}
        for obligation_id in obligation_ids
    ]


def _book_context_or_note(
    graph: Any, docs_root: Path, repo_root: Path
) -> tuple[dict[str, Any], str]:
    """`book_context` against *repo_root*, or ({}, note) when the layout cannot support it."""
    try:
        features_root_rel = (
            features_root_of(graph).resolve().relative_to(repo_root.resolve()).as_posix()
        )
    except ValueError:
        return {}, (
            f"this book's docs root {features_root_of(graph)} is not inside the checkout "
            f"{repo_root} whose git history a plan would be diffed against — compiling a "
            "plan from the book itself is not yet supported for that layout; author a "
            "qa_plan.py for this spec dir instead"
        )
    return book_context(repo_root, features_root=features_root_rel), ""


@blueprint.node
def audit_one_spec(
    logger: logging.Logger,
    spec_dir: str,
    docs_path: str = "",
    repo_dir: str = "",
    rerun_all: bool = False,
) -> LiveAuditReport:
    """Run one spec directory's QA plan for real and fingerprint every scenario."""
    docs_root = find_docs_root(docs_path, repo_dir)
    repo_root = find_repo_root(repo_dir)
    graph = model.load(docs_root)
    own_repository = book_repository(features_root_of(graph))

    stack = ensure_stack(logger, docs_path, repo_dir, near=str(docs_root / spec_dir))
    if stack.ready in ("none", "no"):
        return LiveAuditReport(spec_dir=spec_dir, status="blocked", stack=stack, notes=stack.notes)

    authored_path = docs_root / spec_dir / "qa_plan.py"
    gaps: tuple[dict[str, Any], ...] = ()
    gapped_ids: set[str] = set()

    if authored_path.is_file():
        resolved_spec_dir = resolve_spec_dir(Path(spec_dir) / "qa_plan.py", Path(spec_dir), docs_root)
        document, problems = load_plan(Path(spec_dir) / "qa_plan.py", resolved_spec_dir, docs_root)
        if document is None:
            return LiveAuditReport(
                spec_dir=spec_dir, status="blocked", stack=stack,
                notes="; ".join(problems) or "plan could not be loaded",
            )
        if document.context:
            result = compile_plan_gaps(document.context, story=document.story)
            gaps = tuple(
                {"obligation_id": g.obligation_id, "kind": g.kind, "detail": g.detail}
                for g in result.gaps
            )
        context = document.context
        all_scenarios = [s for s in document.data.get("scenarios", []) if isinstance(s, dict)]
        scenarios_data = all_scenarios
        plan_file_for_run: str | None = None
        run_spec_dir = spec_dir
    else:
        context, note = _book_context_or_note(graph, docs_root, repo_root)
        if not context:
            return LiveAuditReport(spec_dir=spec_dir, status="blocked", stack=stack, notes=note)
        result = compile_plan_gaps(context, story=BOOK_TARGET)
        if isinstance(result, Refusal):
            kinds = sorted({g.kind for g in result.gaps})
            return LiveAuditReport(
                spec_dir=spec_dir, status="blocked", stack=stack,
                notes=(f"no scenario compiled from the book: {len(result.gaps)} gap(s) across "
                       f"{', '.join(kinds) or 'no kinds'}"),
            )
        run_dir = docs_root / _COMPILED_RUN_ROOT / "book"
        run_dir.mkdir(parents=True, exist_ok=True)
        plan_path = run_dir / "qa_plan.py"
        plan_path.write_text(result.source, encoding="utf-8")
        (run_dir / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
        document, problems = load_plan(plan_path, run_dir, docs_root)
        if document is None:
            return LiveAuditReport(
                spec_dir=spec_dir, status="blocked", stack=stack,
                notes="compiled plan could not be loaded: " + ("; ".join(problems) or "unknown"),
            )
        gaps = tuple(
            {"obligation_id": g.obligation_id, "kind": g.kind, "detail": g.detail}
            for g in result.gaps
        )
        gapped_ids = {g.obligation_id for g in result.gaps}
        resolved_spec_dir = run_dir
        all_scenarios = [s for s in document.data.get("scenarios", []) if isinstance(s, dict)]
        scenarios_data = [
            s for s in all_scenarios if not (set(s.get("covers") or []) & gapped_ids)
        ]
        plan_file_for_run = str(plan_path)
        run_spec_dir = str(run_dir)

    nodes_by_id = {node.id: node for node in graph.ui_nodes}
    obligations_by_id = {
        str(o.get("id")): o
        for o in (context or {}).get("obligations", [])
        if isinstance(o, dict)
    }
    ledger_path = resolved_spec_dir / LEDGER_FILE
    ledger = load_ledger(ledger_path)

    fingerprints: dict[str, str] = {}
    refs_by_id: dict[str, list[str]] = {}
    changed_by_id: dict[str, bool] = {}
    for scenario in scenarios_data:
        scenario_id = str(scenario.get("id") or "")
        covers = scenario.get("covers") or []
        refs: list[str] = []
        for node_id in _covered_node_ids(covers):
            node = nodes_by_id.get(node_id)
            if node is not None:
                refs.extend(code_refs(node.meta.get("code")))
        fixture_texts = _fixture_texts_for(covers, obligations_by_id, nodes_by_id)
        claim_content = json.dumps(scenario, sort_keys=True, default=str)
        fingerprint = claim_fingerprint(
            refs, fixture_texts, claim_content, repo_root, own_repository=own_repository,
        )
        fingerprints[scenario_id] = fingerprint
        refs_by_id[scenario_id] = refs
        changed_by_id[scenario_id] = needs_rerun(ledger, scenario_id, fingerprint)

    to_run = [
        sid for sid in fingerprints if rerun_all or changed_by_id[sid]
    ]

    run: Any = None
    scenario_summaries: dict[str, Any] = {}
    run_notes = "no claim's fingerprint changed since its last recorded run; nothing re-run"
    if to_run:
        run = run_qa_plan(
            logger, run_spec_dir, docs_path, repo_dir, only=to_run, plan_file=plan_file_for_run,
        )
        summaries = run.ostler.get("scenarios") if isinstance(run.ostler, dict) else None
        scenario_summaries = summaries if isinstance(summaries, dict) else {}
        run_notes = run.notes

    results: list[ScenarioResult] = []
    extra_gaps: list[dict[str, Any]] = []
    for scenario in scenarios_data:
        scenario_id = str(scenario.get("id") or "")
        fingerprint = fingerprints[scenario_id]
        refs = refs_by_id[scenario_id]
        if scenario_id in to_run:
            summary = scenario_summaries.get(scenario_id) or {}
            fallback_status = run.status if run is not None else "invalid"
            status = str(summary.get("status") or fallback_status)
            assertions = int(summary.get("assertions") or 0)
            failures = int(summary.get("failures") or 0)
            message = str(summary.get("message") or "")
            strict_mode_gaps = _strict_mode_violation_gaps(scenario.get("covers") or [], message)
            if strict_mode_gaps is not None:
                extra_gaps.extend(strict_mode_gaps)
                continue
            ledger = record_result(
                ledger_path, ledger, scenario_id, fingerprint, status,
                assertions=assertions, failures=failures, message=message,
            )
            source = "fresh"
        else:
            record = ledger.get("claims", {}).get(scenario_id) or {}
            status = str(record.get("verdict") or "")
            assertions = int(record.get("assertions") or 0)
            failures = int(record.get("failures") or 0)
            message = str(record.get("message") or "")
            source = "carried"
        results.append(ScenarioResult(
            id=scenario_id, status=status, assertions=assertions, failures=failures,
            message=message, code_refs=tuple(refs), fingerprint=fingerprint,
            changed=changed_by_id[scenario_id], source=source,
        ))

    if extra_gaps:
        gaps = (*gaps, *extra_gaps)

    if not scenarios_data:
        return LiveAuditReport(
            spec_dir=spec_dir, status="blocked", stack=stack, gaps=gaps,
            notes=(
                f"{len(gaps)} obligation(s) blocked on a compile gap; nothing compiled "
                "clean enough to run" if gaps else "no obligations to audit"
            ),
        )

    return LiveAuditReport(
        spec_dir=spec_dir, status="ran", stack=stack, scenarios=tuple(results),
        gaps=gaps, notes=run_notes,
    )


@blueprint.node
def discover_spec_dirs(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> list[str]:
    """Every spec directory under the book's `specs` root that declares a `qa_plan.py`."""
    docs_root = find_docs_root(docs_path, repo_dir)
    root = specs_root_in(docs_root)
    if not root.is_dir():
        return []
    return sorted(str(p.parent.relative_to(docs_root)) for p in root.rglob("qa_plan.py"))


@blueprint.node
def discover_compiled_targets(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> list[str]:
    """`[BOOK_TARGET]` when the book serves something and no spec dir authors its own plan."""
    docs_root = find_docs_root(docs_path, repo_dir)
    graph = model.load(docs_root)
    return [BOOK_TARGET] if runbook.has_served_surface(graph) else []


class LiveAudit(Workflow):
    """Run every spec dir's compiled QA plan for real; this is `main/flow.py`'s audit gate."""

    docs_path: str = ""
    repo_dir: str = ""
    spec_dirs: tuple[str, ...] = ()
    rerun_all: bool = False

    def start(self) -> Done:
        spec_dirs = self.spec_dirs or self.call(discover_spec_dirs, self.docs_path, self.repo_dir)
        if not spec_dirs:
            spec_dirs = self.call(discover_compiled_targets, self.docs_path, self.repo_dir)
        reports = [
            self.call(audit_one_spec, spec_dir, self.docs_path, self.repo_dir, self.rerun_all)
            for spec_dir in spec_dirs
        ]
        return Done({"reports": [r.model_dump() for r in reports]}).because(
            "every spec dir's plan executed; blocked entries name the refusal reason"
        )


__all__ = [
    "BOOK_TARGET", "LiveAudit", "LiveAuditReport", "ScenarioResult", "audit_one_spec",
    "discover_compiled_targets", "discover_spec_dirs",
]
