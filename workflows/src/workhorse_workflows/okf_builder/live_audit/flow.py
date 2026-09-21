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

#: The ledger persists beside the plan it fingerprints, one file per spec dir — the same
#: directory `run_qa_plan` already writes `qa/qa-run.ndjson` under.
LEDGER_FILE = "qa-ledger.json"

#: Where a book-compiled plan and its evidence live when no authored spec dir names one —
#: deliberately outside `docs/specs`, so `compile_plan_gaps`'s rendered skeleton is never
#: mistaken for an authored plan and is never written back into the book tree it was
#: compiled from.
_COMPILED_RUN_ROOT = ".qa-live-audit"

#: The synthetic `spec_dir` label `discover_compiled_targets` reports for "no authored
#: spec dir names a plan, but the book itself is a plan source" — never a real path under
#: `docs/specs`, so it can never collide with one, and it reads unambiguously in a report.
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


#: Playwright's own wording (`playwright/_impl/_errors.py` via the JS driver's
#: `strict mode violation: ${locator} resolved to ${matches.length} elements:...`) for a
#: locator that matched more than the one element a `verify: visible` check needs. By the
#: time this flow sees it, the exception itself is long gone — it was raised inside the
#: scenario subprocess, caught by `ostler_qa.py`'s `_run` (`except BaseException:`), and
#: folded into the scenario's terminal `error`/`message` as `traceback.format_exc()`. So
#: this is matched as text, not as an exception type; the phrase is Playwright's own and
#: is not used for anything else a scenario could raise.
_STRICT_MODE_VIOLATION_RE = re.compile(r"strict mode violation:.*resolved to \d+ elements", re.DOTALL)


def _strict_mode_violation_gaps(
    covers: Sequence[Any], message: str
) -> list[dict[str, Any]] | None:
    """Finding 8: a Playwright strict-mode violation is a book gap, never a failed check.

    `compile.py` already does the honest thing here — it emits the author's `selector:`
    locator as-is and never guesses a `.first` on the caller's behalf, because `selector:`
    is unique by the author's intent, not by construction, and intent is not a guarantee.
    When the intent is wrong, Playwright's own strict mode raises with a message that names
    exactly what happened: the subject the book pointed at resolved to more than one element
    on the rendered page. That is ATTRIBUTABLE to the book in a way nothing else a scenario
    can raise is — it can never mean the app answered wrong, only that the book named its
    subject imprecisely — so it must never be scored as a failed assertion or land in the
    ledger as one: `needs_rerun` would then carry a false failure forward on every pass whose
    fingerprint does not move, exactly the way a genuine failure should.

    Returns one gap per real obligation id (`okf:...`) the scenario's `covers=[...]` names,
    same as `compile.py`'s own Amendment 1 (one gap per covered obligation, not a single
    representative) — or `None` when the message does not match, or the scenario covers no
    real obligation id to key a gap to (nothing to attribute it to; the caller falls back to
    reporting it as an ordinary failure).
    """
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
    """`book_context` against *repo_root*, or ({}, note) when the layout cannot support it.

    `book_context` diffs one repo's git history against its own empty tree; a docs tree
    that does not live inside `repo_root` — the split docs-repo/checkout layout a
    multi-repo book can use — has no path relative to it to diff, so compiling a plan
    from the book itself is not yet supported for that split. The honest answer is a
    blocked report naming the gap, never a silent fallback that fabricates a green one.
    """
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
    """Run one spec directory's QA plan for real and fingerprint every scenario.

    An authored `docs/specs/<story>/qa_plan.py` is the plan whenever one exists, unchanged
    from before this docstring. **A book with no authored plan is not a book with nothing
    to audit** — `discover_compiled_targets` hands this node `BOOK_TARGET` in that case,
    and this falls through to compiling the plan from the book's own current obligations
    (`ostler.qa.context.book_context` + `ostler.qa.compile.compile_plan_gaps`), written
    under a scratch run directory (`_COMPILED_RUN_ROOT`) — never into `docs/specs` — and
    run from there. The two paths converge immediately after: fingerprinting, the ledger,
    and `run_qa_plan` do not know or care which one produced their `scenarios_data`.

    Only claims whose fingerprint moved since the ledger's last record are actually
    executed (`only=` into `run_qa_plan`, a real scored subset — see `runner.run_qa_plan`).
    A claim whose fingerprint is unchanged is not re-run: its previously recorded verdict
    is carried into this report verbatim, marked `source="carried"` rather than `"fresh"`,
    so a caller can tell a genuinely-just-verified claim from one this pass never touched.
    `rerun_all=True` forces every claim through `run_qa_plan` regardless of its
    fingerprint — the operator override for "the fixture data or environment moved in a
    way no citation captures, run everything for real."

    **Measured 2026-09-15, against a real book with no authored plan** (a small
    seat-booking-style app; see this slice's commit for the number's provenance): 21
    nodes compiled to 67 obligations, 51 of them declaring at least one `verify:` check
    (the other 16 declare none at all — pure book debt `compile_plan_gaps` never reports
    a `Gap` for, since there is no check to fail to compile). Of those 51, **zero**
    compiled gap-free — 106 gaps total (64 `unresolved-precondition`: a missing fixture,
    request body, or template variable; 42 `uncompilable-claim`: no route, or a
    subject-observing check like `persists`/`count`/`unchanged`/`keys_unchanged`, which
    always gaps regardless of route, since compiling one would mean inventing the
    arrangement the book never wrote). 24 of the 51 sit on a routed node and still gap
    only on the missing fixture/body/template-var; the rest have no route at all. Today's
    compiler turns a routed, checkable obligation into a runnable call and turns
    everything else into a `Gap` this report carries as blocked book debt, never as a
    failed scenario (see `LiveAuditReport`/`_live_audit_gate_message`) and never as a
    ledger row (a gapped obligation has no scenario to fingerprint or record). Slice 3
    (fixture-node execution) is what is expected to move that 0% up — nothing here
    invents an arrangement the book has not written yet.

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
        # An authored plan's scenarios are hand-written, independent of what the
        # auto-compiler would have done with the same obligations — a compile gap here is
        # reported alongside the run, never used to drop a scenario a human already wrote.
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
        # A compiled scenario with any gapped check still gets a function body (compile.py
        # always emits one once an obligation declares a check, gap-free or not) — running
        # it would score a claim the compiler itself could not finish, which is exactly the
        # blocked/failed conflation condition 2 forbids. Only the gap-free ones run; every
        # gapped obligation is reported (via `gaps` above) and nothing else — no
        # `ScenarioResult`, no fingerprint, no ledger row.
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
        # Never `only=None` here even when `rerun_all` — `to_run` already lists every
        # gap-free scenario id when `rerun_all` is set (`fingerprints` only ever has keys
        # for `scenarios_data`, the gap-free subset), and passing `None` on the compiled
        # path would run the whole plan file, gapped scenario functions included.
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
                # Finding 8: this scenario proved nothing about the obligations it covers —
                # report it as blocked book debt, the same as a compile gap, never as a
                # failed assertion. No `ScenarioResult`, no ledger row: `record_result` is
                # skipped on purpose, so `needs_rerun` keeps re-attempting it every pass
                # instead of carrying a false failure forward under an unmoved fingerprint.
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
        # Nothing compiled clean enough to run at all — the whole-book equivalent of the
        # "plan could not be loaded" block above, except every reason is a named `Gap`
        # rather than a load failure. This is the expected outcome for a book like
        # seat-booking's measurement in this node's docstring: every obligation blocked,
        # nothing executed, the operator gate parked immediately — not a bug to fix here.
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


@blueprint.node
def discover_compiled_targets(logger: logging.Logger, docs_path: str = "", repo_dir: str = "") -> list[str]:
    """`[BOOK_TARGET]` when the book serves something and no spec dir authors its own plan.

    `discover_spec_dirs` finds every story's own `qa_plan.py`; a book documenting an
    already-existing app with no authored story has none, which used to make `LiveAudit`
    report zero specs — and the caller's gate is an `any(...)` over that empty report
    list, so it passed silently, having run nothing and said nothing. `LiveAudit.start()`
    calls this only when `discover_spec_dirs` (or an explicit `spec_dirs=`) found nothing,
    so an authored plan always takes precedence where one exists.

    `has_served_surface` is the same test `runner.ensure_stack` and doctor's
    `runbook-missing` already gate on: a book serving nothing has no live behavior to
    audit against a stack, compiled or authored, so there is nothing to hand back either.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    graph = model.load(docs_root)
    return [BOOK_TARGET] if runbook.has_served_surface(graph) else []


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
