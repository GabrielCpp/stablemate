"""The obligation→evidence join: coverage as a set difference, not a reading.

Someone used to answer "is every obligation backed by an executed assertion?" by opening
the plan, the run log and the evidence artifact and holding them in their head — once per
story, forever, and wrong whenever the three disagreed quietly. Every fact that answer needs
is already written down by the run:

* ``qa-okf-context.json`` — the obligations the change owes evidence for, and the checks
  each one's ``verify:`` bullets declare.
* ``qa/qa-run.ndjson`` — what the run actually claimed (``scenario_start.covers``) and what
  it actually observed (``assert`` records, with the check name and arguments on the ones
  made through :meth:`Qa.verify`).
* ``qa/run-manifest.json`` — the files each scenario produced, with their hashes.
* ``qa-evidence.json`` — the verdict that was published downstream.

Joining them is arithmetic. What it produces is one row per obligation and a status the
reader routes on rather than re-derives, which is the whole point: `uncovered` is a set
difference, and a set difference does not have an opinion or run out of budget.

The log is the ground truth and ``qa-evidence.json`` is a summary of it, so where they
disagree the row says `contradicted` and reports both. That case is not hypothetical — an
audit found an obligation published `Fail` with no refs at all under an `overall: Pass`,
by hand, which is exactly the labour this replaces.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ostler import checks
from ostler.qa import sensitivity
from ostler.qa.session import QA_DIRNAME, scratch_dirname
from ostler.util import is_mapping

VERSION = 1

#: The five answers, ordered worst-first so a summary reads top-down.
#:
#: `unproven` sits second because it is urgent and it is *not* `contradicted`. A scenario
#: that died mid-body — a `KeyError` on a field the plan misspelled, a timeout, a browser
#: left unclean — never observed the product at all, and reporting that as a disproof is how
#: a clean tree with a correct book got accused of a defect it did not have. The obligation
#: is unproven, the plan is what failed, and the two route to different repairs.
#: `insensitive` sits just above `covered` because it is the quietest of the failures: every
#: assertion ran, every one passed, and none of them could have done anything else. It is
#: below the three that report missing evidence because there *is* evidence here — it just
#: does not discriminate — and a reader with both should repair the missing one first.
STATUSES = (
    "contradicted",
    "unproven",
    "uncovered",
    "claimed-but-unasserted",
    "insensitive",
    "covered",
)


class EvidenceMapError(RuntimeError):
    """An input is missing or unreadable — the join cannot be computed, only reported."""


def _read_json(path: Path, *, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvidenceMapError(f"{what} is missing at {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceMapError(f"{what} at {path} is unreadable: {exc}") from exc


def _read_log(path: Path) -> list[dict[str, Any]]:
    """The run ledger, one record per line.

    A malformed line is fatal rather than skipped. This file is the ground truth every
    status below is computed from, and silently dropping a record turns a contradiction into
    a clean `uncovered` — the failure mode this whole exercise exists to remove.
    """
    if not path.exists():
        raise EvidenceMapError(f"the run log is missing at {path} — has this spec been run?")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceMapError(f"{path}:{number} is not valid JSON: {exc}") from exc
        if is_mapping(record):
            records.append(dict(record))
    return records


def _artifacts_by_scenario(manifest: Any) -> dict[str, list[str]]:
    """Which files each scenario produced, from the manifest that hashed them.

    Read from the manifest rather than from the run log's own artifact records because the
    manifest is what `artifact vet` holds a Pass row to: a row citing a file the manifest
    does not carry is not evidence, whatever the log says was written.
    """
    by_scenario: dict[str, list[str]] = {}
    if not is_mapping(manifest):
        return by_scenario
    for entry in manifest.get("artifacts", []) or []:
        if not is_mapping(entry) or not entry.get("path"):
            continue
        scenario = entry.get("scenario")
        if scenario:
            by_scenario.setdefault(str(scenario), []).append(str(entry["path"]))
    return by_scenario


def _published(evidence: Any) -> dict[str, dict[str, Any]]:
    """The verdict `qa-evidence.json` published per obligation, if it published one."""
    rows: dict[str, dict[str, Any]] = {}
    if not is_mapping(evidence):
        return rows
    for row in evidence.get("obligations", []) or []:
        if is_mapping(row) and row.get("id"):
            rows[str(row["id"])] = dict(row)
    return rows


def _call_text(name: str, args: Any) -> str | None:
    """The canonical spelling of one recorded check invocation, or `None` if it is not one.

    Through `checks.bind`, which is the same canonicalisation a `verify:` bullet goes
    through — argument order from the spec, `literal` rendering, booleans spelled the
    book's way. Rendering it here by hand instead would compare two strings that agree only
    by accident, and the first `count=1` written after a `title="…"` would read as a missing
    check on an obligation that was in fact observed.
    """
    bound = checks.bind(name, args if is_mapping(args) else {})
    return None if isinstance(bound, str) else bound.text()


def build_evidence_map(spec_dir: Path, *, label: str | None = None) -> dict[str, Any]:
    """Join the four run artifacts into one row per obligation.

    Raises :class:`EvidenceMapError` when an input is absent or unreadable. That is a
    refusal, not an empty map: a map computed over a missing log would report every
    obligation `uncovered`, which is indistinguishable from a run that genuinely asserted
    nothing and is the more likely reading of the two.

    ``label`` reads a dry run's ledger under ``<spec>/qa/<label>/`` instead of the scored
    one, and must be the same label that run was given;
    :class:`ostler.qa.session.ScratchLabelError` for one that could never have named a
    ledger.
    """
    qa_dir = spec_dir / (QA_DIRNAME if label is None else scratch_dirname(label))
    context = _read_json(spec_dir / "qa-okf-context.json", what="the context packet")
    log = _read_log(qa_dir / "qa-run.ndjson")
    manifest = _read_json(qa_dir / "run-manifest.json", what="the run manifest")
    evidence_path = spec_dir / "qa-evidence.json"
    evidence = _read_json(evidence_path, what="the evidence artifact") if evidence_path.exists() else {}

    artifacts = _artifacts_by_scenario(manifest)
    published = _published(evidence)
    overall = str(evidence.get("overall", "")) if is_mapping(evidence) else ""

    asserts = [record for record in log if record.get("kind") == "assert"]
    # The scenarios that stopped somewhere other than the end of their body. A passing
    # assertion inside one of those proved a state the steps after it never got to leave, so
    # it is not evidence that the obligation holds — and reading it as evidence is how a
    # browser locator timing out on the one assertion that would have exposed a defect went
    # out as a covered obligation under an `overall: Fail`.
    aborted_scenarios = {
        str(record.get("scenario", ""))
        for record in log
        if record.get("kind") == "scenario_stop" and record.get("aborted")
    }
    claims: dict[str, set[str]] = {}
    for record in log:
        if record.get("kind") != "scenario_start":
            continue
        for obligation_id in record.get("covers", []) or []:
            claims.setdefault(str(obligation_id), set()).add(str(record.get("scenario", "")))

    scope = [
        obligation
        for obligation in context.get("obligations", []) or []
        if is_mapping(obligation) and obligation.get("id")
    ]
    # Only the obligations the change *owes evidence for*. A context packet also carries the
    # ones pulled in for reading — `required: false`, `evidenceRequired: "context"`, a flow's
    # neighbours — and on a real story they outnumber the owed ones ten to one. Counting them
    # would report a fully-evidenced run as a thousand gaps, which is the same uselessness as
    # reporting none.
    owed = [obligation for obligation in scope if obligation.get("required", True)]
    rows = [
        _row(
            obligation,
            asserts=asserts,
            claims=claims,
            aborted_scenarios=aborted_scenarios,
            artifacts=artifacts,
            published=published,
        )
        for obligation in owed
    ]
    return {
        "version": VERSION,
        "runId": str(evidence.get("runId") or context.get("runId") or ""),
        "overall": overall,
        "counts": {status: sum(1 for row in rows if row["status"] == status) for status in STATUSES},
        "contextOnly": len(scope) - len(owed),
        "obligations": rows,
    }


def _row(
    obligation: Mapping[str, Any],
    *,
    asserts: list[dict[str, Any]],
    claims: dict[str, set[str]],
    aborted_scenarios: set[str],
    artifacts: dict[str, list[str]],
    published: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """One obligation, and everything the run has to say about it."""
    obligation_id = str(obligation["id"])
    bound = [record for record in asserts if obligation_id in (record.get("covers") or [])]
    passing = [
        record
        for record in bound
        if record.get("result") == "PASS"
        and str(record.get("scenario", "")) not in aborted_scenarios
    ]
    aborted = [
        record
        for record in bound
        if record.get("result") == "PASS"
        and str(record.get("scenario", "")) in aborted_scenarios
    ]
    # A failing record is only a disproof if the *plan* made it. The harness synthesizes one
    # over every obligation an aborted scenario claimed (see `PythonDriver._grade`), and that
    # record reports the scenario, not the product — so it is partitioned out here rather
    # than counted as an assertion that ran and disagreed.
    failing = [
        record
        for record in bound
        if record.get("result") != "PASS" and not record.get("sentinel")
    ]
    sentinels = [
        record
        for record in bound
        if record.get("result") != "PASS" and record.get("sentinel")
    ]

    declared = [
        str(entry["call"])
        for entry in obligation.get("checksDeclared") or []
        if is_mapping(entry) and entry.get("call")
    ]
    observed = {
        call
        for record in passing
        if record.get("check")
        and (call := _call_text(str(record["check"]), record.get("check_args"))) is not None
    }
    missing = [call for call in declared if call not in observed]
    # Asked of the *declaration*, not of the run: a call's sensitivity is a property of the
    # check and its arguments, so it is the same answer whatever the product did, and asking
    # it here is what keeps a green ledger from being read as a proof it is not.
    insensitive = [
        call for call in declared
        if isinstance(parsed := checks.parse_check(call), checks.CheckCall)
        and not sensitivity.trial(parsed).sensitive
    ]

    evidence_files = sorted(
        {path for record in passing for path in artifacts.get(str(record.get("scenario", "")), [])}
    )
    status, why = _classify(
        obligation_id,
        claimed=claims.get(obligation_id, set()),
        passing=passing,
        aborted=aborted,
        failing=failing,
        sentinels=sentinels,
        declared=declared,
        missing=missing,
        insensitive=insensitive,
        published=published.get(obligation_id),
    )
    row: dict[str, Any] = {
        "id": obligation_id,
        "kind": str(obligation.get("kind", "")),
        "source": str(obligation.get("source", "")),
        "requirement": str(obligation.get("requirement", "")),
        "evidenceRequired": str(obligation.get("evidenceRequired", "")),
        "status": status,
        "why": why,
        "claimedBy": sorted(claims.get(obligation_id, set())),
        "assertions": {"passing": len(passing), "failing": len(failing)},
        "checksDeclared": declared,
        "checksObserved": sorted(observed),
        "checksMissing": missing,
        "checksInsensitive": insensitive,
        "evidence": evidence_files,
        "logRefs": [_ref(record) for record in bound],
    }
    if failing:
        row["failingLogRefs"] = [_ref(record) for record in failing]
    if aborted or sentinels:
        # One field for both, because they are the same fact about this obligation: the
        # scenario stopped early, so nothing it recorded — the asserts that passed before the
        # stop, or the harness's own note that there was one — says what the product does.
        row["abortedLogRefs"] = [_ref(record) for record in [*aborted, *sentinels]]
    if obligation_id in published:
        row["publishedVerdict"] = str(published[obligation_id].get("verdict", ""))
    return row


def _ref(record: dict[str, Any]) -> str:
    return f"{record.get('scenario', '')}:assert:{record.get('action', '?')}"


def _classify(
    obligation_id: str,
    *,
    claimed: set[str],
    passing: list[dict[str, Any]],
    aborted: list[dict[str, Any]],
    failing: list[dict[str, Any]],
    sentinels: list[dict[str, Any]],
    declared: list[str],
    missing: list[str],
    insensitive: list[str],
    published: dict[str, Any] | None,
) -> tuple[str, str]:
    """The status, and the sentence that says how it was reached.

    Ordered by what a reader must act on first. A disproof outranks a gap, because an
    obligation with a failing assertion is a product defect and one with none is a QA
    defect, and routing them the same way sends the wrong agent. A published verdict the log
    does not support outranks both: it means the artifact downstream consumers read is
    wrong about this obligation, which no amount of correct QA work below it repairs.

    The same reasoning is why an aborted scenario is `unproven` and not `contradicted`. It
    reads like a disproof — there is a failing record bound to the obligation — but the
    record is the harness's, written *because* nothing observed the product, and the usual
    cause is a defect in the plan: a misspelled field, a timeout, a step that raised. Scoring
    that as a product defect accuses whatever tree happened to be under it, including a clean
    one, and sends the repair to the wrong lane.
    """
    verdict = str(published.get("verdict", "")) if published else ""
    if failing:
        return (
            "contradicted",
            f"{len(failing)} assertion(s) bound to it failed — the run observed the product "
            "and it did not do this.",
        )
    if sentinels or (aborted and not passing):
        scenarios = sorted(
            {str(record.get("scenario", "")) for record in [*sentinels, *aborted]}
        )
        return (
            "unproven",
            f"scenario(s) {', '.join(scenarios)} did not run to completion, so nothing in "
            "this run observed the product for this obligation — the assertion(s) that "
            "would have are the ones that never ran. Repair the plan, then re-run: until "
            "one does, this is a claim about the plan and not about the product.",
        )
    if verdict == "Pass" and not passing:
        return (
            "contradicted",
            "qa-evidence.json publishes Pass, and no passing assertion in the run log is "
            "bound to it — the artifact claims evidence the ledger does not hold.",
        )
    if verdict == "Fail" and passing and not missing:
        return (
            "contradicted",
            "qa-evidence.json publishes Fail while every assertion bound to it passed — the "
            "artifact and the ledger disagree, and the ledger is the one that ran.",
        )
    if not passing:
        if claimed:
            return (
                "claimed-but-unasserted",
                f"scenario(s) {', '.join(sorted(claimed))} declare covers=['{obligation_id}'] "
                "and recorded no passing assertion bound to it.",
            )
        return (
            "uncovered",
            "no scenario claims it and no assertion is bound to it — nothing in this run "
            "observed it.",
        )
    if not missing and declared and len(insensitive) == len(declared):
        return (
            "insensitive",
            "every check its `verify:` bullets declare passed, and no observation of the "
            "product could have made any of them fail: "
            + ", ".join(f"`{call}`" for call in insensitive)
            + ". A pass here says the assertion ran, not that the product does this — "
            "repair the declaration, not the app.",
        )
    if missing:
        return (
            "claimed-but-unasserted",
            "the book declares "
            + ", ".join(f"`{call}`" for call in missing)
            + " and no passing assertion invokes it — what was asserted is not what was "
            "claimed to be asserted.",
        )
    return (
        "covered",
        f"{len(passing)} passing assertion(s) bound to it"
        + (
            f", making all {len(declared)} check(s) its `verify:` bullets declare."
            if declared
            else ", and its `verify:` bullets declare no check to hold them to."
        ),
    )


def render_evidence_map(data: dict[str, Any], *, only: str = "") -> list[str]:
    """The map as lines, worst status first.

    Sorted by status rather than by id because the reader is triaging, not auditing: the
    rows that need work are the ones that are not `covered`, and an id-ordered list buries
    them among however many hundred are fine.
    """
    lines = [
        f"# QA evidence map — run {data.get('runId') or '(unknown)'}, "
        f"overall {data.get('overall') or '(none)'}",
        "  " + ", ".join(f"{status}: {data['counts'].get(status, 0)}" for status in STATUSES),
        f"  ({data.get('contextOnly', 0)} further obligations are in scope for context and owe "
        "no evidence)",
        "",
    ]
    for status in STATUSES:
        rows = [row for row in data["obligations"] if row["status"] == status]
        if only and status != only:
            continue
        if not rows:
            continue
        lines.append(f"## {status} ({len(rows)})")
        for row in rows:
            lines.append(f"- {row['id']}  [{row['kind']}]")
            lines.append(f"  {row['requirement']}")
            lines.append(f"  why: {row['why']}")
            if row["evidence"]:
                lines.append(f"  evidence: {', '.join(row['evidence'])}")
        lines.append("")
    return lines
