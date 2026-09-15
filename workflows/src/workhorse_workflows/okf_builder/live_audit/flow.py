"""Live behavioral audit lane: real pass/fail per claim, fingerprinted against the ledger.

Sibling to `okf_builder/audit/flow.py`'s LLM-based review, this flow runs no agent turn at
all. For each spec directory's already-authored `qa_plan.py` it brings up the book's
declared QA stack, executes the plan through `qa/runner.py` (the same functions `coder`'s
QA gate calls), and threads every scenario through the slice-5 ledger
(`shared/ledger.py`) so a caller can tell which claims changed since their last recorded
run.

Doctor's `runbook-missing` finding is a warn, not a gate — a repo that never authored a
runbook still gets a doctor report, not a blocked run there. This flow enforces the block
`ensure_stack` already encodes for exactly that condition (`StackStatus.ready in ("none",
"no")`), which is the extension the plan's slice-6 line asks for; `doctor.py`'s own
severity is untouched. A blocked spec dir is recorded in the report rather than raised —
the run is over the whole book, and one service's undeclared stack must not stop every
other spec dir from reporting.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
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

#: `ensure_stack`'s own health probe passes the instant a force-recreated container answers
#: its first request, which can be moments before a sibling service it depends on (an auth
#: emulator seeded by a one-shot `seed` container in the same compose file) has actually
#: absorbed that seed data — the plan's first scenarios then see a connection reset or a
#: real-but-wrong response (`EMAIL_NOT_FOUND` for an account the seed step already
#: reported seeding), not a 5xx. A stack this flow just brought up (not one it adopted
#: already serving) gets re-polled until the same probe passes a second time, rather than
#: trusting `ensure_stack`'s first pass — a fixed sleep tried here first (3s, then 10s)
#: still left one scenario in four hitting a live but not-yet-settled stack.
FRESH_STACK_SETTLE_TRIES = 10
FRESH_STACK_SETTLE_INTERVAL_S = 2.0


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


class LiveAuditReport(BaseModel):
    """One spec directory's outcome: either blocked before anything ran, or a real run."""

    model_config = ConfigDict(extra="forbid")

    spec_dir: str
    status: str  # "blocked" | "ran"
    stack: StackStatus | None = None
    scenarios: tuple[ScenarioResult, ...] = ()
    gaps: tuple[dict[str, Any], ...] = ()
    notes: str = ""


#: How many consecutive passing probes prove the stack (and whatever it depends on, like a
#: sibling service's seed data) has stopped changing, rather than just answered once.
FRESH_STACK_SETTLE_CONSECUTIVE = 3


def _wait_for_settled(entry_url: str, logger: logging.Logger) -> None:
    """Re-poll a freshly brought-up stack's own health URL until it is stably answering.

    `ensure_stack` already proved the URL answers once; a single pass is not proof the
    stack (and a sibling one-shot seed step it may depend on) has stopped changing
    underneath it, so this asks again, spaced out, requiring several passes in a row before
    `run_qa_plan`'s real requests start. Bounded by `FRESH_STACK_SETTLE_TRIES` — a stack
    that never stabilizes is a job for `run_qa_plan` and the scenario failures it will
    report, not an infinite wait here.
    """
    if not entry_url:
        return
    consecutive = 0
    for attempt in range(FRESH_STACK_SETTLE_TRIES):
        time.sleep(FRESH_STACK_SETTLE_INTERVAL_S)
        try:
            urllib.request.urlopen(entry_url, timeout=5)  # noqa: S310
        except urllib.error.HTTPError:
            pass  # any HTTP response (even a 404 off this bare entry_url) proves it is up
        except urllib.error.URLError as exc:
            consecutive = 0
            logger.info("settle probe %d/%d against %s not ready yet: %s",
                        attempt + 1, FRESH_STACK_SETTLE_TRIES, entry_url, exc)
            continue
        consecutive += 1
        if consecutive >= FRESH_STACK_SETTLE_CONSECUTIVE:
            return


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
) -> LiveAuditReport:
    """Run one spec directory's already-authored QA plan and fingerprint every scenario.

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
    if "brought up" in stack.notes:
        _wait_for_settled(stack.entry_url, logger)

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

    run = run_qa_plan(logger, spec_dir, docs_path, repo_dir)
    scenario_summaries = run.ostler.get("scenarios") if isinstance(run.ostler, dict) else None
    scenario_summaries = scenario_summaries if isinstance(scenario_summaries, dict) else {}

    nodes_by_id = {node.id: node for node in graph.ui_nodes}
    ledger_path = resolved_spec_dir / LEDGER_FILE
    ledger = load_ledger(ledger_path)

    results: list[ScenarioResult] = []
    for scenario in document.data.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get("id") or "")
        refs: list[str] = []
        for node_id in _covered_node_ids(scenario.get("covers") or []):
            node = nodes_by_id.get(node_id)
            if node is not None:
                refs.extend(code_refs(node.meta.get("code")))
        summary = scenario_summaries.get(scenario_id) or {}
        status = str(summary.get("status") or run.status)
        fingerprint = claim_fingerprint(
            refs, {}, scenario_id, repo_root, own_repository=own_repository,
        )
        changed = needs_rerun(ledger, scenario_id, fingerprint)
        ledger = record_result(ledger_path, ledger, scenario_id, fingerprint, status)
        results.append(ScenarioResult(
            id=scenario_id, status=status,
            assertions=int(summary.get("assertions") or 0),
            failures=int(summary.get("failures") or 0),
            message=str(summary.get("message") or ""),
            code_refs=tuple(refs), fingerprint=fingerprint, changed=changed,
        ))

    return LiveAuditReport(
        spec_dir=spec_dir, status="ran", stack=stack, scenarios=tuple(results),
        gaps=gaps, notes=run.notes,
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
    """Standalone live-audit lane: run every spec dir's compiled QA plan for real.

    Sibling to `Audit`, not wired into `main/flow.py`'s `semantic_audit` state machine —
    building this lane as a genuinely standalone flow was a scoped decision for this pass;
    see the drive-by report that introduced this module. Runnable directly:

        workhorse-okf-builder run live-audit --params \
            '{"docs_path": "...", "repo_dir": "...", "spec_dirs": ["docs/specs/claims-crud"]}'
    """

    docs_path: str = ""
    repo_dir: str = ""
    #: Story spec directories (each holding a `qa_plan.py`), relative to `docs_path`. Empty
    #: means every spec dir `discover_spec_dirs` finds under the book's `specs` root.
    spec_dirs: tuple[str, ...] = ()

    def start(self) -> Done:
        spec_dirs = self.spec_dirs or self.call(discover_spec_dirs, self.docs_path, self.repo_dir)
        reports = [
            self.call(audit_one_spec, spec_dir, self.docs_path, self.repo_dir)
            for spec_dir in spec_dirs
        ]
        return Done({"reports": [r.model_dump() for r in reports]}).because(
            "every spec dir's plan executed; blocked entries name the refusal reason"
        )


__all__ = [
    "LiveAudit", "LiveAuditReport", "ScenarioResult", "audit_one_spec", "discover_spec_dirs",
]
