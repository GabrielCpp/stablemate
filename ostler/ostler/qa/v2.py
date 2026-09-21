"""Version-2 QA orchestration across command, browser, and mobile drivers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from ostler.qa.drivers import DriverBlocked, QaDriver, ScenarioResult, create_driver
from ostler.qa.plan import PlanDocument, check_runtime_requirements
from ostler.qa.session import QA_DIRNAME, QaSession
from ostler.qa.report import REPORT_FILE, ReportError, write_report


def run_plan(
    document: PlanDocument,
    *,
    root: Path,
    stop_on_fail: bool = False,
    only: list[str] | None = None,
    qa_dirname: str = QA_DIRNAME,
) -> tuple[str, str, dict[str, Any]]:
    """Execute a validated plan and return ``(status, message, summary)``."""
    plan = document.data
    spec_dir = document.spec_dir
    scored = qa_dirname == QA_DIRNAME
    selected = list(plan["scenarios"])
    if only is not None:
        known = {str(scenario["id"]) for scenario in selected}
        unknown = [name for name in only if name not in known]
        if unknown:
            message = f"unknown scenario(s): {', '.join(sorted(unknown))}"
            return "invalid", message, {"status": "invalid", "problems": [message]}
        selected = [scenario for scenario in selected if str(scenario["id"]) in set(only)]
    wanted_targets = {str(scenario["target"]) for scenario in selected}

    runtime_problems = check_runtime_requirements(document, targets=wanted_targets)
    if runtime_problems:
        message = "QA run blocked:\n" + "\n".join(f"  - {item}" for item in runtime_problems)
        return "blocked", message, {"status": "blocked", "problems": runtime_problems}

    qa_dir = spec_dir / qa_dirname
    if qa_dir.exists():
        shutil.rmtree(qa_dir)
    qa_dir.mkdir(parents=True)
    if scored:
        (spec_dir / "qa-evidence.json").unlink(missing_ok=True)
        (spec_dir / REPORT_FILE).unlink(missing_ok=True)

    secret_values = {
        name: _secret_value(declaration, root)
        for name, declaration in plan.get("secrets", {}).items()
    }
    variables = {
        f"input.{name}": str((spec_dir / str(path)).resolve())
        for name, path in plan.get("inputs", {}).items()
    }
    variables["qa_dir"] = str(qa_dir.resolve())
    session = QaSession.create(
        spec_dir,
        document.run_id,
        document.story,
        {key: str(value) for key, value in plan.get("env", {}).items()},
        secret_values=secret_values,
        qa_dirname=qa_dirname,
    )
    session.write_session_start()
    drivers: dict[str, QaDriver] = {}
    results: dict[str, ScenarioResult] = {}
    status = "passed"
    cleanup_errors: list[str] = []
    runner_errors: list[str] = []
    summary: dict[str, Any] = {}
    evidence: Path | None = None
    try:
        for daemon in plan.get("background", []):
            for reset_path in daemon.get("reset_paths", []):
                Path(session.expand(str(reset_path), variables)).unlink(missing_ok=True)
            _start_daemon(session, daemon, variables, root)
        for target_id, target in plan["targets"].items():
            if target_id not in wanted_targets:
                continue
            driver = create_driver(
                session,
                target_id,
                target,
                root=root,
                variables=variables,
                obligation_documents=plan.get("obligationDocuments", {}),
            )
            drivers[target_id] = driver
            driver.start()
            session.append(
                {
                    "kind": "driver_start",
                    "target": target_id,
                    "driver": target["driver"],
                }
            )
        for scenario in selected:
            scenario_id = str(scenario["id"])
            target_id = str(scenario["target"])
            for name in scenario.get("restart", []):
                _restart_daemon(session, plan, str(name), variables, root, scenario_id)
            session.append(
                {
                    "kind": "scenario_start",
                    "scenario": scenario_id,
                    "target": target_id,
                    "driver": plan["targets"][target_id]["driver"],
                    "mechanism": scenario["mechanism"],
                    "covers": scenario.get("covers", []),
                }
            )
            result = drivers[target_id].run(scenario)
            results[scenario_id] = result
            session.append(
                {
                    "kind": "scenario_stop",
                    "scenario": scenario_id,
                    "target": target_id,
                    "driver": plan["targets"][target_id]["driver"],
                    "status": result.status,
                    "assertions": result.assertions,
                    "failures": result.failures,
                    **({"aborted": True} if result.aborted else {}),
                    **({"message": result.message} if result.message else {}),
                }
            )
            if result.status != "passed":
                status = result.status
                if stop_on_fail:
                    break
    except DriverBlocked as exc:
        status = "blocked"
        runner_errors.append(str(exc))
        session.append({"kind": "runner_error", "status": status, "message": str(exc)})
    except KeyboardInterrupt:
        status = "blocked"
        runner_errors.append("interrupted")
        session.append({"kind": "runner_error", "status": status, "message": "interrupted"})
    except Exception as exc:  # noqa: BLE001
        status = "invalid"
        runner_errors.append(f"{type(exc).__name__}: {exc}")
        session.append({"kind": "runner_error", "status": status, "message": str(exc)})
    finally:
        for target_id, driver in reversed(drivers.items()):
            try:
                driver.stop()
                session.append(
                    {
                        "kind": "driver_stop",
                        "target": target_id,
                        "driver": plan["targets"][target_id]["driver"],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"{target_id}: {exc}")
        if cleanup_errors:
            status = "invalid"
            runner_errors.append(f"driver cleanup failed: {'; '.join(cleanup_errors)}")
            session.append(
                {
                    "kind": "runner_error",
                    "status": status,
                    "message": "driver cleanup failed",
                    "problems": cleanup_errors,
                }
            )
        if scored:
            evidence = _write_evidence(document, results, status)
            session.register_artifact(evidence, kind="qa-evidence")
        summary = session.close(status=status)
        session.finalize_log_artifact()
        try:
            report = write_report(spec_dir, qa_dirname=qa_dirname)
        except (ReportError, OSError) as exc:
            report = None
            runner_errors.append(f"qa report not written: {exc}")

    summary.update(
        {
            "status": status,
            "runId": document.run_id,
            "qa_run_log": f"{qa_dirname}/qa-run.ndjson",
            "manifest": f"{qa_dirname}/run-manifest.json",
            **({"report": str(report.relative_to(spec_dir))} if report else {}),
            "scenarios": {
                name: {
                    "status": result.status,
                    "assertions": result.assertions,
                    "failures": result.failures,
                    **({"aborted": True} if result.aborted else {}),
                    **({"message": result.message} if result.message else {}),
                }
                for name, result in results.items()
            },
        }
    )
    if cleanup_errors:
        summary["cleanup_errors"] = cleanup_errors
    if runner_errors:
        summary["runner_errors"] = runner_errors
    message = (
        f"QA run {status.upper()}: {summary.get('pass_count', 0)} assertions passed, "
        f"{summary.get('fail_count', 0)} failed, {len(results)} scenarios"
    )
    if runner_errors:
        message += f" — {'; '.join(runner_errors)}"
    return status, message, summary


def _write_evidence(
    document: PlanDocument,
    results: dict[str, ScenarioResult],
    status: str,
) -> Path:
    aborted = {
        scenario_id
        for scenario_id, result in results.items()
        if result.aborted
    }
    log_records: list[dict[str, Any]] = []
    log_path = document.spec_dir / "qa" / "qa-run.ndjson"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("kind") == "assert":
            log_records.append(record)
    manifest_path = document.spec_dir / "qa" / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts_by_scenario: dict[str, list[str]] = {}
    for artifact in manifest.get("artifacts", []):
        scenario = artifact.get("scenario") if isinstance(artifact, dict) else None
        if scenario:
            artifacts_by_scenario.setdefault(str(scenario), []).append(str(artifact["path"]))

    def row(item: Any) -> dict[str, Any]:
        """One criterion or obligation, judged against *every* assertion covering it."""
        source = item if isinstance(item, dict) else {"id": str(item)}
        item_id = str(source["id"])
        records = [record for record in log_records if item_id in record.get("covers", [])]
        failing = [
            record
            for record in records
            if record.get("result") != "PASS" and not record.get("sentinel")
        ]
        sentinels = [
            record
            for record in records
            if record.get("result") != "PASS" and record.get("sentinel")
        ]
        stopped = [
            record
            for record in records
            if record.get("result") == "PASS" and str(record.get("scenario", "")) in aborted
        ]
        proving = [
            record
            for record in records
            if record.get("result") == "PASS" and str(record.get("scenario", "")) not in aborted
        ]
        refs: list[str] = []
        evidence: list[str] = []
        for index, record in enumerate(records, start=1):
            scenario = str(record.get("scenario", ""))
            action = record.get("action", index)
            refs.append(f"{scenario}:assert:{action}")
            if record.get("result") == "PASS" and scenario not in aborted:
                evidence.extend(artifacts_by_scenario.get(scenario, []))
        row_data = {
            "id": item_id,
            "verdict": "Pass" if proving and not failing else "Fail",
            "log_refs": refs,
            "evidence": sorted(set(evidence)),
        }
        if failing:
            row_data["failing_log_refs"] = [
                f"{record.get('scenario', '')}:assert:{record.get('action', '?')}"
                for record in failing
            ]
        if stopped or sentinels:
            row_data["aborted_log_refs"] = [
                f"{record.get('scenario', '')}:assert:{record.get('action', '?')}"
                for record in [*stopped, *sentinels]
            ]
        return row_data

    criteria = []
    for item in document.context.get("acceptanceCriteria", []):
        criterion = row(item)
        criterion["kind"] = (
            str(item.get("kind", "behavioral")) if isinstance(item, dict) else "behavioral"
        )
        criteria.append(criterion)
    obligations = [row(item) for item in document.context.get("obligations", [])]
    data = {
        "runId": document.run_id,
        "qa_run_log": "qa/qa-run.ndjson",
        "report": REPORT_FILE,
        "overall": {
            "passed": "Pass",
            "failed": "Fail",
            "blocked": "Blocked",
            "invalid": "Invalid",
        }[status],
        "criteria": criteria,
        "obligations": obligations,
    }
    path = document.spec_dir / "qa-evidence.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _daemon_cwd(session: QaSession, daemon: Mapping[str, Any], variables: dict[str, str], root: Path) -> Path:
    """The directory a daemon starts in: its declared `cwd` under the root, else the root."""
    raw = daemon.get("cwd")
    if not raw:
        return root
    candidate = Path(session.expand(str(raw), variables))
    cwd = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not cwd.is_relative_to(root.resolve()):
        raise RuntimeError(f"background daemon '{daemon.get('name')}': cwd {raw} resolves outside the repo root")
    if not cwd.is_dir():
        raise RuntimeError(f"background daemon '{daemon.get('name')}': cwd {raw} is not a directory")
    return cwd


def _start_daemon(
    session: QaSession, daemon: Mapping[str, Any], variables: dict[str, str], root: Path
) -> int:
    """Start one declared daemon, expanding its argv and cwd the way the plan wrote them."""
    return session.start_daemon(
        str(daemon["name"]),
        [session.expand(str(part), variables) for part in daemon["argv"]],
        ready_check=daemon.get("ready_check"),
        timeout=float(daemon.get("timeout", 30)),
        cwd=_daemon_cwd(session, daemon, variables, root),
    )


def _restart_daemon(
    session: QaSession,
    plan: Mapping[str, Any],
    name: str,
    variables: dict[str, str],
    root: Path,
    scenario_id: str,
) -> None:
    """Stop the named daemon and start its declaration again, on a scenario's behalf."""
    declaration = next(d for d in plan.get("background", []) if str(d["name"]) == name)
    session.stop_daemon(name, reason="restart")
    pid = _start_daemon(session, declaration, variables, root)
    session.append(
        {"kind": "daemon_restart", "name": name, "pid": pid, "scenario": scenario_id}
    )


def _secret_value(declaration: dict[str, Any], root: Path) -> str:
    """The runtime value of one declared secret, from its environment variable or its file."""
    if "from_file" in declaration:
        raw = (root / str(declaration["from_file"])).read_text(encoding="utf-8")
        return raw[:-1] if raw.endswith("\n") else raw
    return os.environ[declaration["from_env"]]
