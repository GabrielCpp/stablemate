"""Live behavioral audit lane: real pass/fail per claim, fingerprinted against the ledger.

This is `main/flow.py`'s `semantic_audit` state, reached only from a doctor-clean
checkpoint. It runs no agent turn at all: for each spec directory's already-authored
`qa_plan.py` it brings up the book's declared QA stack, executes the plan through
`qa/runner.py` (the same functions `coder`'s QA gate calls), and threads every scenario
through the ledger (`shared/ledger.py`) so a caller can tell which claims changed since
their last recorded run. It replaces the retired LLM-based behavior audit, which judged
claims by model review rather than by running them.

Doctor's `runbook-missing` finding is an error — a served surface with no stack runbook
fails doctor before this state is ever reached. This flow's own `ensure_stack` block
(`StackStatus.ready in ("none", "no")`) is therefore a defensive backstop, not the real
gate: it only fires for a repo that authored a runbook doctor accepted but whose stack
still fails to come up at run time. A blocked spec dir is recorded in the report rather
than raised — the run is over the whole book, and one service's stack trouble must not
stop every other spec dir from reporting.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ostler import model
from ostler.path import features_root as features_root_of, specs_root_in
from ostler.qa.compile import compile_plan_gaps
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

#: The ledger persists beside the plan it fingerprints, one file per spec dir — the same
#: directory `run_qa_plan` already writes `qa/qa-run.ndjson` under.
LEDGER_FILE = "qa-ledger.json"


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
    #: Whether this fingerprint differs from the ledger's last recorded one for this claim
    #: — independent of `source`, since `rerun_all` can force a fresh execution of a claim
    #: whose fingerprint did not move at all.
    changed: bool = True
    #: "fresh": executed this pass. "carried": the fingerprint matched the ledger's last
    #: record, so the recorded verdict was reused verbatim rather than re-run.
    source: str = "fresh"


class LiveAuditReport(BaseModel):
    """One spec directory's outcome: either blocked before anything ran, or a real run."""

    model_config = ConfigDict(extra="forbid")

    spec_dir: str
    status: str  # "blocked" | "ran"
    stack: StackStatus | None = None
    scenarios: tuple[ScenarioResult, ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()
    notes: str = ""


def _node_text(node: Any) -> str:
    """A stable text rendering of one book node, for fingerprinting its content.

    `UINode` carries no single `text` field — its content is `meta`/`bullet_order`, the
    same bullets in document order. Rendering the ordered `key: value` pairs means an edit
    to a fixture's setup steps (a changed seed value, a reordered step) changes this text
    even though the node's identity and code citations do not.
    """
    return "\n".join(f"{key}: {value}" for key, value, _line in node.bullet_order)


def _fixture_texts_for(
    covers: list[Any],
    obligations_by_id: dict[str, dict[str, Any]],
    nodes_by_id: dict[str, Any],
) -> dict[str, str]:
    """Every fixture node text a scenario's covered obligations declare, keyed by node id.

    `fixturesDeclared` rows (`ostler.qa.context`'s `_parse_fixtures`) name the fixture by
    the same stem a `fixture:`/`needs:` bullet cites, which is the fixture node's own id in
    `nodes_by_id` — resolving it gives the node whose bullets a change to the fixture's
    arrangement would edit.
    """
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
    """Every `okf:<node-id>:<suffix>`-shaped covers id's middle segment, in order.

    A scenario's `covers=[...]` mixes bare acceptance-criterion ids (`"ac:1"`) with
    obligation ids the book's own context builder minted
    (`ostler.qa.context`'s ``f"okf:{node['id']}:{suffix}"``). Only the latter names a
    graph node the ledger can cite bytes from; the former is skipped rather than raised
    on, since a scenario is free to cover both kinds in the same list.
    """
    ids: list[str] = []
    for item in covers:
        text = str(item)
        if not text.startswith("okf:"):
            continue
        parts = text.split(":")
        if len(parts) >= 3:
            ids.append(":".join(parts[1:-1]))
    return ids


@blueprint.node
def audit_one_spec(
    logger: logging.Logger,
    spec_dir: str,
    docs_path: str = "",
    repo_dir: str = "",
    rerun_all: bool = False,
) -> LiveAuditReport:
    """Run one spec directory's already-authored QA plan and fingerprint every scenario.

    Only claims whose fingerprint moved since the ledger's last record are actually
    executed (`only=` into `run_qa_plan`, a real scored subset — see `runner.run_qa_plan`).
    A claim whose fingerprint is unchanged is not re-run: its previously recorded verdict
    is carried into this report verbatim, marked `source="carried"` rather than `"fresh"`,
    so a caller can tell a genuinely-just-verified claim from one this pass never touched.
    `rerun_all=True` forces every claim through `run_qa_plan` regardless of its
    fingerprint — the operator override for "the fixture data or environment moved in a
    way no citation captures, run everything for real."

    `own_repository` is resolved and threaded through every ledger call the same way
    `doctor.py` does it (`book_repository(features_root_of(graph))`): the ledger's
    default (`own_repository=""`) folds every citation — same-repo ones included — into
    its unreadable-file sentinel, which would silently mark every fingerprint identical
    regardless of what the cited files actually say.

    Cited source lives in the checkout (`repo_dir`), not necessarily beside the book
    (`docs_path` may name a separate docs repo) — so `claim_fingerprint`'s `repo_root`
    is resolved via `find_repo_root`, not `find_docs_root`.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    repo_root = find_repo_root(repo_dir)
    graph = model.load(docs_root)
    own_repository = book_repository(features_root_of(graph))

    stack = ensure_stack(logger, docs_path, repo_dir)
    if stack.ready in ("none", "no"):
        return LiveAuditReport(spec_dir=spec_dir, status="blocked", stack=stack, notes=stack.notes)

    resolved_spec_dir = resolve_spec_dir(Path(spec_dir) / "qa_plan.py", Path(spec_dir), docs_root)
    document, problems = load_plan(Path(spec_dir) / "qa_plan.py", resolved_spec_dir, docs_root)
    if document is None:
        return LiveAuditReport(
            spec_dir=spec_dir, status="blocked", stack=stack,
            notes="; ".join(problems) or "plan could not be loaded",
        )

    gaps: tuple[dict[str, Any], ...] = ()
    if document.context:
        _source, gap_list = compile_plan_gaps(document.context, story=document.story)
        gaps = tuple(
            {"obligation_id": g.obligation_id, "kind": g.kind, "detail": g.detail}
            for g in gap_list
        )

    nodes_by_id = {node.id: node for node in graph.ui_nodes}
    obligations_by_id = {
        str(o.get("id")): o
        for o in (document.context or {}).get("obligations", [])
        if isinstance(o, dict)
    }
    ledger_path = resolved_spec_dir / LEDGER_FILE
    ledger = load_ledger(ledger_path)

    scenarios_data = [s for s in document.data.get("scenarios", []) if isinstance(s, dict)]
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
        # The compiled claim itself: the scenario's own rendered assertions and steps, not
        # its bare id — an edited `preconditions`/`checkpoints`/`forbid` list must move the
        # fingerprint even when no cited file or fixture text changed.
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
        run = run_qa_plan(logger, spec_dir, docs_path, repo_dir, only=None if rerun_all else to_run)
        summaries = run.ostler.get("scenarios") if isinstance(run.ostler, dict) else None
        scenario_summaries = summaries if isinstance(summaries, dict) else {}
        run_notes = run.notes

    results: list[ScenarioResult] = []
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

    return LiveAuditReport(
        spec_dir=spec_dir, status="ran", stack=stack, scenarios=tuple(results),
        gaps=gaps, notes=run_notes,
    )


@blueprint.node
def discover_spec_dirs(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> list[str]:
    """Every spec directory under the book's `specs` root that declares a `qa_plan.py`.

    Used when the caller names no `spec_dirs` explicitly — the CLI surface takes a book
    root and a checkout path, decoupled from any one service's spec layout, and this is
    how it finds what to run without either argument naming a story by hand.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    root = specs_root_in(docs_root)
    if not root.is_dir():
        return []
    return sorted(str(p.parent.relative_to(docs_root)) for p in root.rglob("qa_plan.py"))


class LiveAudit(Workflow):
    """Run every spec dir's compiled QA plan for real; this is `main/flow.py`'s audit gate.

    `OkfBuilder.semantic_audit` hands off to this flow. It also stays runnable directly,
    standalone, for exercising a book's QA plans without driving the whole builder:

        workhorse-okf-builder run live-audit --params \
            '{"docs_path": "...", "repo_dir": "...", "spec_dirs": ["docs/specs/claims-crud"]}'
    """

    docs_path: str = ""
    repo_dir: str = ""
    #: Story spec directories (each holding a `qa_plan.py`), relative to `docs_path`. Empty
    #: means every spec dir `discover_spec_dirs` finds under the book's `specs` root.
    spec_dirs: tuple[str, ...] = ()
    #: Force every claim in every spec dir through `run_qa_plan`, ignoring the ledger's
    #: fingerprints — the operator override for a targeted re-run that would otherwise
    #: carry forward claims whose citations do not capture what actually changed.
    rerun_all: bool = False

    def start(self) -> Done:
        spec_dirs = self.spec_dirs or self.call(discover_spec_dirs, self.docs_path, self.repo_dir)
        reports = [
            self.call(audit_one_spec, spec_dir, self.docs_path, self.repo_dir, self.rerun_all)
            for spec_dir in spec_dirs
        ]
        return Done({"reports": [r.model_dump() for r in reports]}).because(
            "every spec dir's plan executed; blocked entries name the refusal reason"
        )


__all__ = [
    "LiveAudit", "LiveAuditReport", "ScenarioResult", "audit_one_spec", "discover_spec_dirs",
]
