"""The run, rendered for the person who has to sign it off.

A QA run leaves a complete account of itself — the ledger, the manifest, the assertion
files, the screenshots and their vet verdicts, the published evidence — and none of it is
shaped for a reader. `qa-run.ndjson` is fifty kilobytes of records in time order;
`qa-evidence.json` lists, under each criterion, every artifact of every scenario that
touched it; `qa evidence-map` joins obligations only. A reviewer asked "was ac:4 actually
tested, and what did the run see?" had to reconstruct the answer from three files, and in
practice did not — which is how an agent's prose in `qa.md` became the thing people read, and
prose is exactly what a reviewer cannot distinguish from a rubber stamp.

This module renders the same facts **per acceptance criterion and per obligation**: which
scenario and which step exercised it, each assertion with its check, what was observed
against what was expected, PASS or FAIL, and the files that back it — and it renders them
deterministically from the ledger, so the document says what the run did and nothing else.
It is written once at the end of every run (`qa-report.md` beside the spec, `qa/<label>/
report.md` for a dry run) and re-rendered on demand by `ostler qa report`.

Two things are deliberate about its shape. It is self-contained in text: `qa/` is ignored by
the repo, so the tables carry the observed values themselves and the links to the raw files
are a convenience for the machine that ran it. And it never reads `qa_plan.py` or the
planner's prose: a report that quoted the plan's intent would be reporting a claim, and the
point is to report what happened.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ostler import registry
from ostler.qa.evidence_map import EvidenceMapError, build_evidence_map, read_json, read_log
from ostler.qa.session import QA_DIRNAME, RUN_LOG, scratch_dirname
from ostler.util import is_mapping

VERSION = 1

#: Where the scored run's report lives — beside `qa-evidence.json`, committed with the story.
REPORT_FILE = "qa-report.md"
#: A dry run's report sits beside that run's own ledger, under `qa/<label>/`.
SCRATCH_REPORT_FILE = "report.md"

#: The three answers a criterion can get. `UNPROVEN` is not a softer `FAIL`: it says no
#: assertion that ran to completion ever looked, which routes to the plan rather than to the
#: product — the same split :mod:`ostler.qa.evidence_map` draws between `uncovered` /
#: `unproven` and `contradicted`.
VERDICTS = ("FAIL", "UNPROVEN", "PASS")

#: Ledger artifact kinds that are bookkeeping rather than evidence a reader wants listed:
#: the assertion files are already linked from their assertion rows, and the rest are the
#: run's own outputs about itself.
_HOUSEKEEPING_KINDS = frozenset({"assertion-result", "run-ledger", "qa-evidence", "qa-report"})
#: Sidecars of a screenshot, folded into the screenshot line rather than listed on their own.
_SCREENSHOT_SIDECARS = frozenset({"layout", "regions", "vet"})
#: Artifacts that describe the scenario as a whole rather than one step of it.
_SCENARIO_LEVEL_KINDS = frozenset({"playwright-trace", "browser-diagnostics", "command-output"})

_CELL_LIMIT = 120


class ReportError(RuntimeError):
    """The ledger is missing or unreadable — there is no run to report on."""


def _qa_dirname(label: str | None, qa_dirname: str | None) -> str:
    if qa_dirname is None:
        return QA_DIRNAME if label is None else scratch_dirname(label)
    if label is not None and scratch_dirname(label) != qa_dirname:
        raise ValueError(f"label {label!r} names {scratch_dirname(label)!r}, not {qa_dirname!r}")
    return qa_dirname


def _label_of(qa_dirname: str) -> str | None:
    """The dry-run label a ledger directory was built from, `None` for the scored `qa`."""
    if qa_dirname == QA_DIRNAME:
        return None
    prefix = QA_DIRNAME + "/"
    return qa_dirname[len(prefix):] if qa_dirname.startswith(prefix) else qa_dirname


# ----------------------------------------------------------------------------- building


def build_report(spec_dir: Path, *, label: str | None = None, qa_dirname: str | None = None) -> dict[str, Any]:
    """Read one run's artifacts and return the report as data.

    ``label`` reads a dry run's ledger under ``<spec>/qa/<label>/`` instead of the scored
    one; ``qa_dirname`` names that directory outright for a caller that already holds it
    (``run_plan`` does) and must agree with ``label`` when both are given. Raises :class:`ReportError` when there is no ledger to read; everything else that is
    missing — the context packet, the manifest, a sidecar — becomes a warning in the report,
    because a report that refused to render a broken run would be absent exactly when it is
    needed.
    """
    spec_dir = Path(spec_dir)
    qa_dirname = _qa_dirname(label, qa_dirname)
    label = _label_of(qa_dirname)
    qa_dir = spec_dir / qa_dirname
    warnings: list[str] = []
    try:
        log = read_log(qa_dir / RUN_LOG)
    except EvidenceMapError as exc:
        raise ReportError(str(exc)) from exc

    context_path = spec_dir / "qa-okf-context.json"
    context: dict[str, Any] = {}
    if context_path.is_file():
        try:
            loaded = read_json(context_path, what="the context packet")
            context = dict(loaded) if is_mapping(loaded) else {}
        except EvidenceMapError as exc:
            warnings.append(str(exc))
    else:
        warnings.append(
            "qa-okf-context.json is missing — the acceptance criteria and obligations this "
            "run owed are unknown, so only what the ledger says is reported."
        )

    start = next((record for record in log if record.get("kind") == "session_start"), {})
    stop = next((record for record in reversed(log) if record.get("kind") == "session_stop"), None)
    if stop is None:
        warnings.append(
            "the ledger has no session_stop record — the run did not close; it is still "
            "going, or the process died before it could write its summary."
        )
    stop = stop or {}
    status = str(stop.get("status") or "incomplete")

    scenarios = _scenarios(log)
    recordings = [
        {
            "target": str(record.get("target", "")),
            "path": str(record.get("path", "")),
            "durationSeconds": record.get("durationSeconds"),
            "width": record.get("width"),
            "height": record.get("height"),
            # The run-clock offset of the recording's first and last frame: what turns a
            # step's ``started_offset_ms`` into a time inside the file.
            "actionStartOffsetMs": record.get("actionStartOffsetMs"),
            "actionEndOffsetMs": record.get("actionEndOffsetMs"),
        }
        for record in log
        if record.get("kind") == "video" and record.get("path")
    ]
    _place_in_recordings(scenarios, recordings)
    asserts = [record for record in log if record.get("kind") == "assert"]
    aborted = {scenario["id"] for scenario in scenarios if scenario["aborted"]}

    criteria_source = [
        item for item in context.get("acceptanceCriteria", []) or [] if is_mapping(item) and item.get("id")
    ]
    obligations_source = [
        item
        for item in context.get("obligations", []) or []
        if is_mapping(item) and item.get("id") and item.get("required", True)
    ]
    context_only = sum(
        1
        for item in context.get("obligations", []) or []
        if is_mapping(item) and item.get("id") and not item.get("required", True)
    )

    criteria = [
        _subject(str(item["id"]), item, scenarios=scenarios, asserts=asserts, aborted=aborted)
        for item in criteria_source
    ]

    statuses: dict[str, dict[str, Any]] = {}
    if obligations_source:
        try:
            for row in build_evidence_map(spec_dir, label=label)["obligations"]:
                statuses[str(row["id"])] = row
        except EvidenceMapError as exc:
            warnings.append(f"the obligation evidence map could not be computed: {exc}")
    obligations = []
    for item in obligations_source:
        subject = _subject(str(item["id"]), item, scenarios=scenarios, asserts=asserts, aborted=aborted)
        row = statuses.get(subject["id"])
        subject["source"] = str(item.get("source", ""))
        subject["evidenceRequired"] = str(item.get("evidenceRequired", ""))
        subject["checksDeclared"] = [
            str(entry["call"])
            for entry in item.get("checksDeclared") or []
            if is_mapping(entry) and entry.get("call")
        ]
        if row is not None:
            subject["status"] = str(row.get("status", ""))
            subject["why"] = str(row.get("why", ""))
            subject["checksMissing"] = list(row.get("checksMissing", []))
            subject["checksInsensitive"] = list(row.get("checksInsensitive", []))
        obligations.append(subject)

    known_ids = {subject["id"] for subject in [*criteria, *obligations]} | {
        str(item["id"])
        for item in context.get("obligations", []) or []
        if is_mapping(item) and item.get("id")
    }
    runner_errors = [
        str(record.get("message", ""))
        + (": " + "; ".join(str(item) for item in record.get("problems", [])) if record.get("problems") else "")
        for record in log
        if record.get("kind") == "runner_error"
    ]
    data: dict[str, Any] = {
        "version": VERSION,
        "story": str(start.get("story", "")),
        "runId": str(start.get("run_id") or stop.get("run_id") or ""),
        "label": label,
        "status": status,
        "startedAt": str(start.get("ts", "")),
        "finishedAt": str(stop.get("ts", "")),
        "ledger": f"{qa_dirname}/{RUN_LOG}",
        "manifest": f"{qa_dirname}/run-manifest.json",
        "counts": {
            "assertions": len(asserts),
            "passed": sum(1 for record in asserts if record.get("result") == "PASS"),
            "failed": sum(1 for record in asserts if record.get("result") != "PASS"),
            "sentinelsFailed": sum(
                1 for record in asserts if record.get("sentinel") and record.get("result") != "PASS"
            ),
            "scenarios": len(scenarios),
            "scenariosPassed": sum(1 for scenario in scenarios if scenario["status"] == "passed"),
            "scenariosFailed": sum(1 for scenario in scenarios if scenario["status"] != "passed"),
            "aborted": len(aborted),
        },
        "contextOnly": context_only,
        "criteria": criteria,
        "obligations": obligations,
        "scenarios": scenarios,
        "recordings": recordings,
        "runnerErrors": runner_errors,
        "warnings": warnings,
    }
    data["warnings"].extend(_warnings(data, known_ids=known_ids, context_known=bool(context)))
    return data


def _scenarios(log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every scenario in ledger order, its steps, and what each step recorded.

    Attribution of an assertion or an artifact to a step reads the ``step`` field the driver
    stamps on the record. A ledger written before that field existed carries only the
    ``step`` record itself, appended when the step closed, and an assertion between two
    step records may have run inside the second or between the two — order cannot tell
    them apart, and guessing put fixture checks under the wrong heading. Such a ledger
    lists its assertions per scenario, outside any step, and says so in the warnings.
    Once one record anywhere carries a stamp, anything unstamped is genuinely outside a step.
    """
    stamped = any("step" in record for record in log if record.get("kind") not in ("step", "scenario_start", "scenario_stop"))
    order: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for record in log:
        if record.get("kind") != "scenario_start":
            continue
        scenario_id = str(record.get("scenario", ""))
        order.append(scenario_id)
        by_id[scenario_id] = {
            "id": scenario_id,
            "target": str(record.get("target", "")),
            "driver": str(record.get("driver", "")),
            "mechanism": str(record.get("mechanism", "")),
            "covers": [str(item) for item in record.get("covers", []) or []],
            "status": "incomplete",
            "aborted": False,
            "assertions": 0,
            "failures": 0,
            "message": "",
            "steps": [],
            "outside": {"asserts": [], "artifacts": []},
            "artifacts": [],
            "stamped": stamped,
            "_steps": {},
        }
    for record in log:
        scenario_id = str(record.get("scenario", ""))
        scenario = by_id.get(scenario_id)
        if scenario is None:
            continue
        kind = str(record.get("kind", ""))
        if kind == "scenario_stop":
            scenario["status"] = str(record.get("status", "") or "incomplete")
            scenario["aborted"] = bool(record.get("aborted"))
            scenario["assertions"] = int(record.get("assertions", 0) or 0)
            scenario["failures"] = int(record.get("failures", 0) or 0)
            scenario["message"] = str(record.get("message", "") or "")
        elif kind == "assert":
            _place(scenario, "asserts", _assert_view(record))
        elif kind == "step":
            step = _step_of(scenario, str(record.get("id", "")), str(record.get("label", "")))
            step["exit_code"] = record.get("exit_code")
            step["unfinished"] = bool(record.get("unfinished"))
            step["error"] = str(record.get("error", "") or "")
            step["startedOffsetMs"] = record.get("started_offset_ms")
            step["endedOffsetMs"] = record.get("ended_offset_ms")
            step["closed"] = True
        elif kind in _HOUSEKEEPING_KINDS or kind == "scenario_start":
            continue
        elif record.get("path"):
            view = _artifact_view(record)
            if kind in _SCENARIO_LEVEL_KINDS:
                scenario["artifacts"].append(view)
            elif kind in _SCREENSHOT_SIDECARS:
                continue
            else:
                _place(scenario, "artifacts", view)
    scenarios = []
    for scenario_id in order:
        scenario = by_id[scenario_id]
        for step in scenario["steps"]:
            if not step.get("closed"):
                # Stamped records named a step the ledger never closed: the scenario died
                # inside it before the driver could write the step record.
                step["unfinished"] = True
                step["exit_code"] = 1
            step.pop("closed", None)
        scenario.pop("_steps")
        scenarios.append(scenario)
    return scenarios


def _place_in_recordings(scenarios: list[dict[str, Any]], recordings: list[dict[str, Any]]) -> None:
    """Give every step the recording knows about a ``video`` placement.

    A step's ``started_offset_ms``/``ended_offset_ms`` and the recording's
    ``actionStartOffsetMs`` are on the same clock (the run's), so the step's place in the
    file is a subtraction. The placement is ``{"path", "at", "until"}`` in seconds into the
    recording of the scenario's target, clamped to the file; ``None`` when the step has no
    stamp, the target was not recorded, or the step lies wholly outside the recording.
    """
    by_target = {r["target"]: r for r in recordings if r.get("actionStartOffsetMs") is not None}
    for scenario in scenarios:
        recording = by_target.get(scenario["target"])
        for step in scenario["steps"]:
            step["video"] = _video_placement(step, recording) if recording else None


def _video_placement(step: Mapping[str, Any], recording: Mapping[str, Any]) -> dict[str, Any] | None:
    started = step.get("startedOffsetMs")
    if started is None:
        return None
    origin = int(recording["actionStartOffsetMs"])
    duration = recording.get("durationSeconds")
    if duration is None:
        end_offset = recording.get("actionEndOffsetMs")
        duration = (int(end_offset) - origin) / 1000 if end_offset is not None else None
    ended = step.get("endedOffsetMs")
    at = (int(started) - origin) / 1000
    until = (int(ended) - origin) / 1000 if ended is not None else at
    if until < 0 or (duration is not None and at > duration):
        return None
    at = max(at, 0.0)
    if duration is not None:
        until = min(until, float(duration))
    return {"path": recording["path"], "at": round(at, 3), "until": round(max(until, at), 3)}


def video_clock(seconds: float) -> str:
    """``m:ss.t`` — how a player shows the position, so a reader can seek by eye."""
    minutes, rest = divmod(max(seconds, 0.0), 60)
    return f"{int(minutes)}:{rest:04.1f}"


def _place(scenario: dict[str, Any], bucket: str, view: dict[str, Any]) -> None:
    if view["step"]:
        _step_of(scenario, view["step"], view["stepLabel"])[bucket].append(view)
    else:
        scenario["outside"][bucket].append(view)


def _step_of(scenario: dict[str, Any], step_id: str, label: str) -> dict[str, Any]:
    step = scenario["_steps"].get(step_id)
    if step is None:
        step = {
            "id": step_id,
            "label": label,
            "exit_code": None,
            "unfinished": False,
            "error": "",
            "startedOffsetMs": None,
            "endedOffsetMs": None,
            "video": None,
            "asserts": [],
            "artifacts": [],
        }
        scenario["_steps"][step_id] = step
        scenario["steps"].append(step)
    elif label and not step["label"]:
        step["label"] = label
    return step


def _assert_view(record: Mapping[str, Any]) -> dict[str, Any]:
    raw_params = record.get("params")
    params: Mapping[str, Any] = raw_params if is_mapping(raw_params) else {}
    raw = str(record.get("raw_result_file", "") or "")
    return {
        "id": str(record.get("id", "")),
        "label": str(record.get("label", "")),
        "check": str(record.get("check", "")),
        "actual": params.get("actual"),
        "expected": params.get("expected"),
        "hasActual": "actual" in params,
        "result": "PASS" if record.get("result") == "PASS" else "FAIL",
        "covers": [str(item) for item in record.get("covers", []) or []],
        "sentinel": bool(record.get("sentinel")),
        "action": record.get("action"),
        "scenario": str(record.get("scenario", "")),
        "step": str(record.get("step", "") or ""),
        "stepLabel": str(record.get("step_label", "") or ""),
        # The raw file is recorded absolute; the report links it relative to the spec.
        "file": f"qa/asserts/{Path(raw).name}" if raw else "",
    }


def _artifact_view(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": str(record.get("kind", "")),
        "path": str(record.get("path", "")),
        "bytes": record.get("bytes"),
        "step": str(record.get("step", "") or ""),
        "stepLabel": str(record.get("step_label", "") or ""),
    }


def _subject(
    subject_id: str,
    item: Mapping[str, Any],
    *,
    scenarios: list[dict[str, Any]],
    asserts: list[dict[str, Any]],
    aborted: set[str],
) -> dict[str, Any]:
    """One criterion or obligation: its verdict and the steps that earned it."""
    bound = [record for record in asserts if subject_id in (record.get("covers") or [])]
    passing = [r for r in bound if r.get("result") == "PASS" and str(r.get("scenario", "")) not in aborted]
    failing = [r for r in bound if r.get("result") != "PASS" and not r.get("sentinel")]
    stopped = [r for r in bound if str(r.get("scenario", "")) in aborted]
    claimed = [scenario["id"] for scenario in scenarios if subject_id in scenario["covers"]]
    if failing:
        verdict, why = "FAIL", f"{len(failing)} assertion(s) covering it failed"
    elif passing:
        verdict, why = "PASS", f"{len(passing)} assertion(s) covering it passed"
    elif stopped:
        verdict = "UNPROVEN"
        why = (
            "every assertion covering it ran inside a scenario that stopped early, so the "
            "run never observed the whole of it"
        )
    elif claimed:
        verdict = "UNPROVEN"
        why = f"claimed by {', '.join(f'`{s}`' for s in claimed)} but no assertion declares `covers` for it"
    else:
        verdict, why = "UNPROVEN", "no scenario claims it and no assertion covers it — it was not tested"

    groups = []
    for scenario in scenarios:
        mine = {r["id"] for r in bound if str(r.get("scenario", "")) == scenario["id"]}
        if not mine and subject_id not in scenario["covers"]:
            continue
        steps = []
        for step in scenario["steps"]:
            hits = [view for view in step["asserts"] if view["id"] in mine]
            if hits:
                steps.append({
                    "id": step["id"],
                    "label": step["label"],
                    "unfinished": step["unfinished"],
                    "video": step.get("video"),
                    "asserts": hits,
                    "artifacts": list(step["artifacts"]),
                })
        outside = [view for view in scenario["outside"]["asserts"] if view["id"] in mine]
        groups.append({
            "scenario": scenario["id"],
            "status": scenario["status"],
            "aborted": scenario["aborted"],
            "target": scenario["target"],
            "driver": scenario["driver"],
            "steps": steps,
            "outside": outside,
        })
    return {
        "id": subject_id,
        "kind": str(item.get("kind", "")),
        "requirement": str(item.get("requirement", "")),
        "verdict": verdict,
        "why": why,
        "scenarios": sorted({str(r.get("scenario", "")) for r in bound} | set(claimed)),
        "passing": len(passing),
        "failing": len(failing),
        "groups": groups,
    }


def _warnings(data: dict[str, Any], *, known_ids: set[str], context_known: bool) -> list[str]:
    """What a reviewer should distrust — the list that answers "was this rubber-stamped?"."""
    out: list[str] = []
    for subject in data["criteria"]:
        if subject["verdict"] == "UNPROVEN":
            out.append(f"`{subject['id']}` is UNPROVEN: {subject['why']}.")
    for subject in data["obligations"]:
        status = subject.get("status") or subject["verdict"]
        if status not in ("covered", "PASS"):
            why = subject.get("why") or subject["why"]
            out.append(f"obligation `{subject['id']}` is {status}: {why}")
    uncovered_asserts: list[str] = []
    no_actual: list[str] = []
    unknown: dict[str, set[str]] = {}
    for scenario in data["scenarios"]:
        if scenario["aborted"]:
            reason = scenario["message"] or "it did not run to completion"
            out.append(f"scenario `{scenario['id']}` was aborted — {reason}")
        elif scenario["status"] == "incomplete":
            out.append(f"scenario `{scenario['id']}` never stopped — the ledger has no scenario_stop for it.")
        for view in _all_asserts(scenario):
            if view["sentinel"]:
                continue
            if not view["covers"]:
                uncovered_asserts.append(view["id"])
            if not view["hasActual"] or view["actual"] is None:
                no_actual.append(view["id"])
            for cover in view["covers"]:
                if context_known and cover not in known_ids:
                    unknown.setdefault(cover, set()).add(view["id"])
        for cover in scenario["covers"]:
            if context_known and cover not in known_ids:
                unknown.setdefault(cover, set()).add(scenario["id"])
    if uncovered_asserts:
        out.append(
            f"{len(uncovered_asserts)} assertion(s) declare no `covers`, so they prove nothing "
            f"for any criterion or obligation: {', '.join(f'`{i}`' for i in uncovered_asserts)}"
        )
    if no_actual:
        out.append(
            f"{len(no_actual)} assertion(s) recorded no `actual` value — the report can show "
            f"their verdict but not what was observed: {', '.join(f'`{i}`' for i in no_actual)}"
        )
    for cover, sources in sorted(unknown.items()):
        out.append(
            f"`{cover}` is covered by {', '.join(f'`{s}`' for s in sorted(sources))} but "
            "qa-okf-context.json does not list it — a claim about nothing the story owes."
        )
    if data["scenarios"] and not any(s["stamped"] for s in data["scenarios"]) and any(
        s["steps"] and (s["outside"]["asserts"] or s["outside"]["artifacts"]) for s in data["scenarios"]
    ):
        out.append(
            "this ledger predates step stamps — the driver did not record which step each "
            "assertion ran inside, so assertions are listed per scenario rather than per "
            "step; re-run the plan for a step-by-step account."
        )
    for error in data["runnerErrors"]:
        out.append(f"runner error: {error}")
    return out


def _all_asserts(scenario: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    for step in scenario["steps"]:
        yield from step["asserts"]
    yield from scenario["outside"]["asserts"]


# ----------------------------------------------------------------------------- rendering


def render_report(data: Mapping[str, Any], *, spec_dir: Path | None = None) -> str:
    """The report as markdown. ``spec_dir`` lets the renderer read a screenshot's vet
    verdict off disk; without it the screenshot is linked and the verdict line is omitted."""
    lines: list[str] = []
    counts = data["counts"]
    label = data.get("label")
    lines.append(f"# QA report — {data['story'] or '(unnamed story)'}")
    lines.append("")
    lines.append(f"<!-- run: {data['runId']} status: {data['status']} -->")
    lines.append("")
    status = str(data["status"]).upper()
    lines.append("| | |")
    lines.append("|---|---|")
    lines.append(f"| Run | `{data['runId']}`{' (dry run `' + str(label) + '`)' if label else ''} |")
    lines.append(f"| Status | **{status}** |")
    lines.append(f"| Started / finished | {data['startedAt'] or '?'} — {data['finishedAt'] or '(never closed)'} |")
    tally = f"{counts['passed']} passed, {counts['failed']} failed"
    if counts.get("sentinelsFailed"):
        tally += (
            f" ({counts['sentinelsFailed']} of the failures are harness sentinels:"
            " a scenario that never ran to completion)"
        )
    lines.append(f"| Assertions | {tally} |")
    lines.append(
        f"| Scenarios | {counts['scenarios']} run, {counts['scenariosPassed']} passed, "
        f"{counts['scenariosFailed']} failed, {counts['aborted']} aborted |"
    )
    lines.append(f"| Ledger | `{data['ledger']}` · `{data['manifest']}` |")
    for recording in data["recordings"]:
        dims = f"{recording['width']}×{recording['height']}" if recording.get("width") else ""
        duration = f"{recording['durationSeconds']:.0f}s" if recording.get("durationSeconds") else ""
        detail = " ".join(part for part in (dims, duration) if part)
        lines.append(f"| Recording (`{recording['target']}`) | [{recording['path']}]({recording['path']}) {detail} |")
    if data["recordings"]:
        lines.append(
            f"| Frames | each recorded step below says where it sits in the recording; "
            f"`ostler qa frames --spec {_spec_arg(spec_dir)} --step STEP-ID` writes the frames "
            f"around it (`--around`/`--fps` widen or thicken the window) |"
        )
    lines.append("")
    lines.append(
        "Rendered by `ostler qa report` from the run ledger; nothing here is written by hand. "
        "The tables carry the observed values themselves; the linked files under `qa/` exist on "
        "the machine that ran this and are not committed."
    )
    lines.append("")

    # -- summary
    lines.append("## Summary")
    lines.append("")
    lines.append("### Acceptance criteria")
    lines.append("")
    if data["criteria"]:
        lines.append("| id | verdict | requirement | proven by | ✓ | ✗ |")
        lines.append("|---|---|---|---|---|---|")
        for subject in data["criteria"]:
            lines.append(
                f"| {subject['id']} | {_badge(subject['verdict'])} | {_cell(_first_sentence(subject['requirement']))} | "
                f"{_cell(', '.join(f'`{s}`' for s in subject['scenarios']) or '—')} | {subject['passing']} | {subject['failing']} |"
            )
    else:
        lines.append("_No acceptance criteria in `qa-okf-context.json`._")
    lines.append("")
    lines.append("### OKF obligations")
    lines.append("")
    if data["obligations"]:
        lines.append("| id | status | requirement | claimed by | ✓ | ✗ |")
        lines.append("|---|---|---|---|---|---|")
        for subject in data["obligations"]:
            status_text = subject.get("status") or subject["verdict"]
            lines.append(
                f"| `{subject['id']}` | {_badge(status_text)} | {_cell(_first_sentence(subject['requirement']))} | "
                f"{_cell(', '.join(f'`{s}`' for s in subject['scenarios']) or '—')} | {subject['passing']} | {subject['failing']} |"
            )
    else:
        lines.append("_No OKF obligations in scope — `qa-okf-context.json` lists none this change owes evidence for._")
    if data.get("contextOnly"):
        lines.append("")
        lines.append(f"_{data['contextOnly']} further obligation(s) are in scope for reading only and owe no evidence._")
    lines.append("")

    # -- criteria
    lines.append("## Acceptance criteria")
    lines.append("")
    if not data["criteria"]:
        lines.append("_None declared._")
        lines.append("")
    for subject in data["criteria"]:
        lines.extend(_render_subject(subject, spec_dir, heading=f"{subject['id']} — {subject['verdict']}"))

    # -- obligations
    lines.append("## OKF obligations")
    lines.append("")
    if not data["obligations"]:
        lines.append("_None owed._")
        lines.append("")
    for subject in data["obligations"]:
        heading = f"`{subject['id']}` — {subject.get('status') or subject['verdict']}"
        extra: list[str] = []
        if subject.get("source"):
            extra.append(f"Source: `{subject['source']}`" + (f" · evidence required: {subject['evidenceRequired']}" if subject.get("evidenceRequired") else ""))
        if subject.get("checksDeclared"):
            extra.append("Declared checks: " + ", ".join(f"`{call}`" for call in subject["checksDeclared"]))
        if subject.get("checksMissing"):
            extra.append("Declared but never observed passing: " + ", ".join(f"`{call}`" for call in subject["checksMissing"]))
        if subject.get("checksInsensitive"):
            extra.append("Insensitive (cannot go red): " + ", ".join(f"`{call}`" for call in subject["checksInsensitive"]))
        lines.extend(_render_subject(subject, spec_dir, heading=heading, extra=extra))

    # -- scenarios
    lines.append("## Scenarios, step by step")
    lines.append("")
    if not data["scenarios"]:
        lines.append("_The ledger records no scenario._")
        lines.append("")
    for scenario in data["scenarios"]:
        lines.extend(_render_scenario(scenario, spec_dir))

    # -- warnings
    lines.append("## Warnings")
    lines.append("")
    if data["warnings"]:
        lines.extend(f"- {warning}" for warning in data["warnings"])
    else:
        lines.append("_None — every criterion and obligation has a passing assertion, every assertion names what it covers, and every scenario ran to completion._")
    lines.append("")
    return "\n".join(lines)


def _render_subject(subject: Mapping[str, Any], spec_dir: Path | None, *, heading: str, extra: list[str] | None = None) -> list[str]:
    lines = [f"### {heading}", ""]
    if subject["requirement"]:
        lines.extend(f"> {line}" for line in str(subject["requirement"]).strip().splitlines())
        lines.append("")
    for line in extra or []:
        lines.append(line + "  ")
    if extra:
        lines.append("")
    if subject["verdict"] == "UNPROVEN" or not subject["groups"]:
        lines.append(f"_{_capitalise(subject['why'])}._")
        lines.append("")
    for group in subject["groups"]:
        state = group["status"] + (" — **aborted**" if group["aborted"] else "")
        lines.append(f"**Scenario `{group['scenario']}`** — {state} (target `{group['target']}`, {group['driver']})")
        lines.append("")
        if not group["steps"] and not group["outside"]:
            lines.append("_Claims this in `covers` but no assertion inside it does._")
            lines.append("")
        for step in group["steps"]:
            suffix = " — **did not finish**" if step["unfinished"] else ""
            lines.append(f"_Step: {step['label'] or step['id']}_{suffix}{_video_note(step, spec_dir)}")
            lines.append("")
            lines.extend(_assert_table(step["asserts"]))
            lines.extend(_artifact_lines(step["artifacts"], spec_dir))
        if group["outside"]:
            lines.append("_Outside any step_")
            lines.append("")
            lines.extend(_assert_table(group["outside"]))
    return lines


def _video_note(step: Mapping[str, Any], spec_dir: Path | None) -> str:
    """`` — recording 0:06.4–0:06.9 · `ostler qa frames …` `` for a step the recording covers."""
    video = step.get("video")
    if not video:
        return ""
    span = video_clock(video["at"])
    if video["until"] > video["at"]:
        span += f"–{video_clock(video['until'])}"
    link = f"[{span}]({video['path']}#t={video['at']})"
    return f" — recording {link} · `ostler qa frames --spec {_spec_arg(spec_dir)} --step {step['id']}`"


def _spec_arg(spec_dir: Path | None) -> str:
    """The ``--spec`` a reader types: the spec dir relative to the working directory when
    it is under it (the usual ``docs/specs/<story>``), the absolute path otherwise."""
    if spec_dir is None:
        return "SPEC"
    try:
        return str(spec_dir.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(spec_dir)


def _assert_table(views: list[dict[str, Any]]) -> list[str]:
    lines = ["| # | assertion | check | actual | expected | result | evidence |", "|---|---|---|---|---|---|---|"]
    for view in views:
        evidence = f"[{Path(view['file']).name}]({view['file']})" if view["file"] else "—"
        label = view["label"] + (" _(harness sentinel)_" if view["sentinel"] else "")
        lines.append(
            f"| {view['action'] if view['action'] is not None else ''} | {_cell(label)} | `{_cell(view['check'])}` | "
            f"{_code(view['actual']) if view['hasActual'] else '—'} | {_code(view['expected'])} | "
            f"{_badge(view['result'])} | {evidence} |"
        )
    lines.append("")
    return lines


def _artifact_lines(views: list[dict[str, Any]], spec_dir: Path | None) -> list[str]:
    lines: list[str] = []
    for view in views:
        if view["kind"] == "screenshot":
            lines.append(f"![{Path(view['path']).name}]({view['path']})  ")
            lines.append(f"Screenshot `{view['path']}`" + _vet_summary(view["path"], spec_dir) + "  ")
        else:
            lines.append(f"Artifact ({view['kind']}): [{view['path']}]({view['path']})  ")
    if lines:
        lines.append("")
    return lines


def _render_scenario(scenario: Mapping[str, Any], spec_dir: Path | None) -> list[str]:
    state = scenario["status"] + (" — **aborted**" if scenario["aborted"] else "")
    lines = [f"### `{scenario['id']}` — {state}", ""]
    covers = ", ".join(f"`{c}`" for c in scenario["covers"]) or "_(none)_"
    lines.append(
        f"Covers {covers} · target `{scenario['target']}` · {scenario['driver']}"
        + (f" ({scenario['mechanism']})" if scenario["mechanism"] else "")
        + f" · {scenario['assertions']} assertion(s), {scenario['failures']} failed"
    )
    if scenario["message"]:
        lines.append("")
        lines.append(f"> {_cell(scenario['message'])}")
    lines.append("")
    if not scenario["steps"] and not scenario["outside"]["asserts"] and not scenario["outside"]["artifacts"]:
        lines.append("_No step, assertion or artifact was recorded._")
        lines.append("")
    for number, step in enumerate(scenario["steps"], start=1):
        outcome = "did not finish" if step["unfinished"] else ("failed" if step["exit_code"] else "ok")
        if step["error"]:
            outcome += f" — {_code(_cell(step['error']))}"
        lines.append(f"{number}. **{step['label'] or step['id']}** — {outcome}{_video_note(step, spec_dir)}")
        lines.extend(_step_items(step["asserts"], step["artifacts"], spec_dir))
    if scenario["outside"]["asserts"] or scenario["outside"]["artifacts"]:
        lines.append("- _Outside any step_" if scenario["stamped"] or not scenario["steps"] else "- _Assertions (this ledger does not say which step each ran in)_")
        lines.extend(_step_items(scenario["outside"]["asserts"], scenario["outside"]["artifacts"], spec_dir, indent="  "))
    lines.append("")
    for view in scenario["artifacts"]:
        lines.append(f"{_kind_title(view['kind'])}: [{view['path']}]({view['path']})  ")
    if scenario["artifacts"]:
        lines.append("")
    return lines


def _step_items(asserts: list[dict[str, Any]], artifacts: list[dict[str, Any]], spec_dir: Path | None, *, indent: str = "   ") -> list[str]:
    lines: list[str] = []
    for view in asserts:
        mark = "✓" if view["result"] == "PASS" else "✗"
        covers = f" (covers {', '.join(f'`{c}`' for c in view['covers'])})" if view["covers"] else " (covers nothing)"
        actual = f" — actual {_code(view['actual'])}" if view["hasActual"] else ""
        if view["result"] != "PASS":
            actual += f", expected {_code(view['expected'])}"
        sentinel = " _(harness sentinel)_" if view["sentinel"] else ""
        lines.append(f"{indent}- {mark} {_cell(view['label'])}{sentinel}{actual}{covers}")
    for view in artifacts:
        if view["kind"] == "screenshot":
            lines.append(f"{indent}- 📷 [{Path(view['path']).name}]({view['path']}){_vet_summary(view['path'], spec_dir)}")
        else:
            lines.append(f"{indent}- 📎 {view['kind']}: [{view['path']}]({view['path']})")
    return lines


def _vet_summary(screenshot: str, spec_dir: Path | None) -> str:
    """` — vet: …` for a screenshot that was registered against the book, else nothing."""
    if spec_dir is None:
        return ""
    vet_path = (spec_dir / screenshot).with_suffix(".vet.json")
    if not vet_path.is_file():
        return ""
    try:
        vet = json.loads(vet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return " — vet: (unreadable)"
    if not is_mapping(vet):
        return " — vet: (unreadable)"
    verdicts = [item for item in vet.get("verdicts", []) or [] if is_mapping(item)]
    findings = [item for item in verdicts if item.get("status") != "matched"]
    where = f"screen `{vet.get('screen', '?')}`" + (f" state `{vet['state']}`" if vet.get("state") else "")
    if findings:
        detail = "; ".join(
            f"{item.get('node_id', '?')} {item.get('status', '?')}" for item in findings
        )
        return f" — vet: {where}, {len(findings)} finding(s): {_cell(detail)}"
    if not verdicts:
        return f" — vet: {where}, the book places no component on it to check ({vet.get('regionCount', '?')} regions scanned)"
    return f" — vet: {where}, all {len(verdicts)} component(s) where the book places them ({vet.get('regionCount', '?')} regions scanned)"


def _kind_title(kind: str) -> str:
    return {
        "playwright-trace": "Playwright trace",
        "browser-diagnostics": "Browser diagnostics",
        "command-output": "Stdout",
    }.get(kind, kind)


def _badge(text: str) -> str:
    if text in ("PASS", "covered", "passed"):
        return f"✓ {text}"
    if text in ("FAIL", "contradicted", "failed"):
        return f"✗ {text}"
    return f"⚠ {text}"


def _first_sentence(text: str, limit: int = _CELL_LIMIT) -> str:
    flat = " ".join(str(text).split())
    if ". " in flat:
        flat = flat.split(". ", 1)[0] + "."
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _cell(text: Any) -> str:
    flat = " ".join(str(text).split())
    return flat.replace("|", "\\|")


def _code(value: Any, limit: int = _CELL_LIMIT) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return "`" + text.replace("|", "\\|").replace("`", "'") + "`"


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


# ----------------------------------------------------------------------------- writing


def report_path(spec_dir: Path, *, label: str | None = None, qa_dirname: str | None = None) -> Path:
    """Where a run's report lives: ``<spec>/qa-report.md``, or ``<spec>/qa/<label>/report.md``
    for a dry run, beside the ledger it renders."""
    spec_dir = Path(spec_dir)
    qa_dirname = _qa_dirname(label, qa_dirname)
    if qa_dirname == QA_DIRNAME:
        return spec_dir / REPORT_FILE
    return spec_dir / qa_dirname / SCRATCH_REPORT_FILE


def write_report(spec_dir: Path, *, label: str | None = None, qa_dirname: str | None = None) -> Path:
    """Build, render and write the report; returns the path written.

    The scored report carries the `spec.<stem>` frontmatter every spec doc carries, so it is
    an OKF Concept like `qa.md` beside it. The dry-run one sits under `qa/`, which the spec
    glob never reaches, and so is left untyped.
    """
    spec_dir = Path(spec_dir)
    qa_dirname = _qa_dirname(label, qa_dirname)
    data = build_report(spec_dir, qa_dirname=qa_dirname)
    body = render_report(data, spec_dir=spec_dir)
    path = report_path(spec_dir, qa_dirname=qa_dirname)
    if qa_dirname == QA_DIRNAME:
        body = f"---\ntype: {registry.spec_type_for(REPORT_FILE)}\n---\n\n" + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def run_id_of(path: Path) -> str | None:
    """The run id a written report was rendered from, or `None` for a file that is not one.

    Read off the marker `render_report` writes, so a downstream gate can tell a report of
    *this* run from one left behind by the last.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("<!-- run: ") and " status: " in line:
            return line[len("<!-- run: "):].split(" status: ", 1)[0].strip()
    return None
