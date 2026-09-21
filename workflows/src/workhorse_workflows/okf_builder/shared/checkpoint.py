"""The deterministic convergence gate, run when the drain is dry."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ostler import Ostler
from ostler.autofix import run_autofix
from ostler.fmt import run_fmt
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Checkpoint, Settled
from workhorse_workflows.okf_builder.shared.worklist import (
    doctor_row,
    reopen_row,
    repair_keys,
    settle_stale_rows,
)

GROUNDED_CODES = frozenset({
    "missing-required-bullet",
    "unreachable-screen",
    "ambiguous-locator",
    "unnamed-interactive",
    "overlong-normative-bullet",
    "missing-placement",
    "unminted-claim",
    "relation-without-subject",
    "missing-code-symbol",
    "deprecation-without-successor",
    "ungrounded-unspecified",
    "template-outside-repeat",
    "one-way-same-as",
})

_CODE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"test-subject", "code-cites-test"}),
    frozenset({"missing-code-symbol", "dangling-code-ref", "dangling-link",
               "missing-anchor", "unresolved-relation"}),
    frozenset({"compound-normative-bullet", "overlong-normative-bullet",
               "unminted-claim", "relation-without-subject"}),
    frozenset({"unparsed-check", "misfiled-test-ref", "weak-check",
               "undeclared-obligation", "unstated-precondition"}),
    frozenset({"missing-placement", "malformed-placement", "ambiguous-locator",
               "unnamed-interactive", "unreachable-screen", "no-root-screen"}),
)


def _family_rank(code: str) -> int:
    return next((n for n, family in enumerate(_CODE_FAMILIES) if code in family),
                len(_CODE_FAMILIES))


MAX_FINDINGS_PER_ITEM = 25


def _node_of(ref: str, path: str) -> str:
    """The node a finding sits on, out of a doctor `ref` — `<path>#<node>[#<member>]`."""
    if not ref.startswith(path + "#"):
        return path
    return f"{path}#{ref[len(path) + 1 :].split('#')[0]}"


def _related_of(finding: dict) -> list[str]:
    """The book locations a *group* finding is about beyond its own `path` — or `[]`."""
    related = finding.get("related") or []
    return [str(member) for member in related] if isinstance(related, list) else []


TEST_SUBJECT = "test-subject"

NON_ACTIONABLE_CODES = frozenset({
    "unstamped-citation",
    "unreachable-citation",
    "needs-snapshot",
    "needs-out-of-band-observation",
    "needs-target-backend",
    "needs-multi-target-runtime",
    "unwitnessed-check",
})

REGROUNDING_CODES = frozenset({"stale-citation"})


def _actionable_findings(findings: list[dict]) -> list[dict]:
    """Drop findings no agent turn can act on: test-subject nodes and ostler-only codes."""
    pages = {str(f.get("path", "")) for f in findings
             if f.get("code") == TEST_SUBJECT and f.get("ref") == f"{f.get('path', '')}#code"}
    nodes = {_node_of(str(f.get("ref", "") or ""), str(f.get("path", "")))
             for f in findings if f.get("code") == TEST_SUBJECT}
    kept = []
    for finding in findings:
        if finding.get("code") in NON_ACTIONABLE_CODES or finding.get("code") in REGROUNDING_CODES:
            continue
        path = str(finding.get("path", ""))
        page_verdict = finding.get("code") == TEST_SUBJECT and finding.get("ref") == f"{path}#code"
        if path in pages and not page_verdict:
            continue
        node = _node_of(str(finding.get("ref", "") or ""), path)
        if node in nodes and finding.get("code") != TEST_SUBJECT:
            continue
        kept.append(finding)
    return kept


def _repair_items(findings: list[dict]) -> list[dict[str, Any]]:
    """One item per `(file, node, code)`, chunked, carrying that group's findings only."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for finding in _actionable_findings(findings):
        path = str(finding.get("path", ""))
        if _related_of(finding):
            code = str(finding.get("code", ""))
            groups.setdefault(("", str(finding.get("ref", "") or ""), code),
                              []).append(finding)
            continue
        node = _node_of(str(finding.get("ref", "") or ""), path)
        groups.setdefault((path, node, str(finding.get("code", ""))), []).append(finding)

    items: list[dict[str, Any]] = []
    ordered = sorted(
        groups.items(),
        key=lambda kv: (
            0 if any(f.get("severity") == "error" for f in kv[1]) else 1,
            _family_rank(kv[0][2]),
            kv[0],
        ),
    )
    for (path, node, code), group in ordered:
        group.sort(key=lambda f: (f.get("line", 0), str(f.get("ref", ""))))
        chunks = [group[i:i + MAX_FINDINGS_PER_ITEM]
                  for i in range(0, len(group), MAX_FINDINGS_PER_ITEM)]
        for n, chunk in enumerate(chunks, start=1):
            suffix = f"#{n}" if len(chunks) > 1 else ""
            related = sorted({member for finding in chunk
                              for member in _related_of(finding)})
            context: dict[str, Any] = {"code": code}
            if related:
                context["citation"] = node
                context["related"] = related
                context["paths"] = sorted({member.split("#")[0] for member in related})
            else:
                context["node"] = node
                context["path"] = path
            context["grounded"] = code in GROUNDED_CODES
            context["findings"] = chunk
            items.append({
                "kind": f"fix:{code}",
                "target": f"{path}#{node}#{code}{suffix}" if path else f"{node}#{code}{suffix}",
                "context": json.dumps(context, indent=2),
                "requeue": True,
            })
    return items


def _signature(findings: list[dict]) -> str:
    """A stable fingerprint of a finding SET, order-independent."""
    if not findings:
        return ""
    keys = sorted(
        (str(f.get("code", "")), str(f.get("path", "")), str(f.get("ref", "")))
        for f in findings
    )
    return hashlib.sha1(json.dumps(keys).encode()).hexdigest()[:16]


def scoped_findings(report: dict, repo_root: str, features: str) -> list[dict]:
    """Doctor's standing findings located in the service book being built."""
    try:
        prefix = Path(features).resolve().relative_to(
            Path(repo_root).resolve()
        ).as_posix().rstrip("/") if features else ""
    except ValueError:
        prefix = Path(features).as_posix().rstrip("/")
    return [
        finding for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and (not prefix
             or str(finding.get("path", "")) == prefix
             or str(finding.get("path", "")).startswith(prefix + "/"))
    ]


SETTLE_EVERY = 25


@blueprint.node
def settle_stale(
    logger: logging.Logger,
    worklist_path: str,
    repo_root: str = ".",
    features_root: str = "",
    every: int = SETTLE_EVERY,
) -> Settled:
    """Mid-drain, reconcile the repair rows against doctor: close the open rows it no longer reports, and reopen the done rows it still does."""
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    items: list[dict[str, Any]] = [row for row in data.get("items", []) if isinstance(row, dict)]
    done = sum(1 for i in items if i.get("status") == "done")
    pending = sum(1 for i in items if i.get("status") == "pending")
    last = data.get("settled_done")
    due = not isinstance(last, int) or done < last or done - last >= every
    fixable = any(
        i.get("status") in ("pending", "blocked", "done") and doctor_row(i) for i in items
    )
    if not due or not fixable:
        return Settled(pending_count=pending, at_done=done if isinstance(last, int) else 0)

    error = ""
    standing: list[dict[str, Any]] = []
    settled = reopened = 0
    try:
        findings = scoped_findings(Ostler(repo_root).doctor().data, repo_root, features_root)
        standing = _repair_items(findings)
        settled = settle_stale_rows(items, standing, where="mid-drain")
        by_key = {key: i for i in items if doctor_row(i) for key in repair_keys([i])}
        for item in standing:
            row = by_key.get(next(iter(repair_keys([item]))))
            if row is None or row.get("status") != "done":
                continue
            if all(f.get("fixable") for f in json.loads(item["context"])["findings"]):
                continue
            reopened += reopen_row(logger, row, item, repo_root)
    except (OSError, ValueError, RuntimeError) as exc:
        error = str(exc)
        logger.warning("settle skipped — ostler doctor failed: %s", exc)
    done = sum(1 for i in items if i.get("status") == "done")
    data["items"] = items
    data["settled_done"] = done
    path.write_text(json.dumps(data, indent=2))
    pending = sum(1 for i in items if i.get("status") == "pending")
    logger.info(
        "settle at %d done: %d standing repair item(s), closed %d stale row(s), "
        "reopened %d standing row(s), %d pending",
        done, len(standing), settled, reopened, pending,
    )
    return Settled(
        ran=True, settled=settled, reopened=reopened, standing=len(standing),
        pending_count=pending,
        at_done=done, error=error,
    )


@blueprint.node(stub=stubs.clean)
def checkpoint_book(
    logger: logging.Logger,
    repo_root: str = ".",
    features_root: str = "",
    prev_round: int = 0,
    prev_signature: str = "",
    prev_stall: int = 0,
) -> Checkpoint:
    """Canonicalize the book, then read doctor, then queue the repairs it names."""
    rnd = prev_round + 1
    okf = Ostler(repo_root)
    if features_root:
        try:
            fixed = run_autofix(okf.graph, [features_root])
            if fixed.changed:
                logger.info("autofixed %d drifted file(s) under %s", len(fixed.changed), features_root)
            result = run_fmt(okf.graph, [features_root])
            if result.changed:
                logger.info("canonicalized %d file(s) under %s", len(result.changed), features_root)
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning("ostler fmt failed for %s: %s", features_root, exc)
        okf.reload()
    else:
        logger.warning("no features root given — skipping ostler fmt; doctor findings are unscoped")

    try:
        findings = scoped_findings(okf.doctor().data, repo_root, features_root)
        out = json.dumps(findings, indent=2)
    except (OSError, ValueError, RuntimeError) as exc:
        findings = [{"severity": "error", "message": str(exc), "path": features_root}]
        out = str(exc)
    clean = not _actionable_findings(findings)

    signature = _signature(findings)
    if clean:
        stall = 0
    elif signature and signature == prev_signature:
        stall = prev_stall + 1
    else:
        stall = 0

    fixups: list[dict[str, Any]] = []
    backfills = 0
    if clean:
        logger.info(
            "round %d: doctor is clean for %s — the gate converges", rnd, features_root or repo_root
        )
    else:
        fixups = _repair_items(findings)
        backfills = sum(1 for i in fixups
                        if str(i["kind"]).removeprefix("fix:") in GROUNDED_CODES)
        errors = sum(1 for f in findings if f.get("severity") == "error")
        logger.info(
            "round %d: doctor reports %d finding(s): %d error, %d warn across %d item(s) "
            "in %s — queuing %d backfill + %d fixup item(s)%s",
            rnd, len(findings), errors, len(findings) - errors, len(fixups),
            features_root or repo_root, backfills, len(fixups) - backfills,
            f" [stall {stall}: same findings as last round]" if stall else "",
        )
    return Checkpoint(
        checkpoint_clean=clean,
        doctor_output=out[-4000:],
        round=rnd,
        fixup_items=fixups,
        backfill_count=backfills,
        fixup_signature=signature,
        stall_rounds=stall,
    )


__all__ = ["GROUNDED_CODES", "MAX_FINDINGS_PER_ITEM", "SETTLE_EVERY", "checkpoint_book",
           "scoped_findings", "settle_stale"]
