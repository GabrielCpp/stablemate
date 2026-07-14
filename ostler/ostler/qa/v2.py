"""Version-2 QA orchestration across command, browser, and mobile drivers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .drivers import DriverBlocked, QaDriver, ScenarioResult, create_driver
from .plan import PlanDocument, check_runtime_requirements
from .session import QaSession


def run_plan(
    document: PlanDocument,
    *,
    root: Path,
    stop_on_fail: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    """Execute a validated plan and return ``(status, message, summary)``."""
    runtime_problems = check_runtime_requirements(document)
    if runtime_problems:
        message = "QA run blocked:\n" + "\n".join(f"  - {item}" for item in runtime_problems)
        return "blocked", message, {"status": "blocked", "problems": runtime_problems}

    plan = document.data
    spec_dir = document.spec_dir
    qa_dir = spec_dir / "qa"
    if qa_dir.exists():
        shutil.rmtree(qa_dir)
    qa_dir.mkdir(parents=True)
    (spec_dir / "qa-evidence.json").unlink(missing_ok=True)

    secret_values = {
        name: os.environ[declaration["from_env"]]
        for name, declaration in plan.get("secrets", {}).items()
    }
    variables = {
        f"input.{name}": str((spec_dir / str(path)).resolve())
        for name, path in plan.get("inputs", {}).items()
    }
    session = QaSession.create(
        spec_dir,
        document.run_id,
        document.story,
        {key: str(value) for key, value in plan.get("env", {}).items()},
        secret_values=secret_values,
    )
    session.write_session_start()
    drivers: dict[str, QaDriver] = {}
    results: dict[str, ScenarioResult] = {}
    status = "passed"
    cleanup_errors: list[str] = []
    summary: dict[str, Any] = {}
    evidence: Path | None = None
    try:
        for daemon in plan.get("background", []):
            session.start_daemon(
                str(daemon["name"]),
                session.expand(str(daemon["cmd"]), variables),
                ready_check=daemon.get("ready_check"),
                timeout=float(daemon.get("timeout", 30)),
                cwd=root,
            )
        for target_id, target in plan["targets"].items():
            driver = create_driver(
                session,
                target_id,
                target,
                root=root,
                variables=variables,
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
        for scenario in plan["scenarios"]:
            scenario_id = str(scenario["id"])
            target_id = str(scenario["target"])
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
                }
            )
            if result.status != "passed":
                status = result.status
                if stop_on_fail:
                    break
    except DriverBlocked as exc:
        status = "blocked"
        session.append({"kind": "runner_error", "status": status, "message": str(exc)})
    except KeyboardInterrupt:
        status = "blocked"
        session.append({"kind": "runner_error", "status": status, "message": "interrupted"})
    except Exception as exc:  # noqa: BLE001
        status = "invalid"
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
            session.append(
                {
                    "kind": "runner_error",
                    "status": status,
                    "message": "driver cleanup failed",
                    "problems": cleanup_errors,
                }
            )
        evidence = _write_evidence(document, results, status)
        session.register_artifact(evidence, kind="qa-evidence")
        summary = session.close(status=status)
        session.finalize_log_artifact()

    summary.update(
        {
            "status": status,
            "runId": document.run_id,
            "qa_run_log": "qa/qa-run.ndjson",
            "manifest": "qa/run-manifest.json",
            "scenarios": {
                name: {
                    "status": result.status,
                    "assertions": result.assertions,
                    "failures": result.failures,
                }
                for name, result in results.items()
            },
        }
    )
    if cleanup_errors:
        summary["cleanup_errors"] = cleanup_errors
    message = (
        f"QA run {status.upper()}: {summary.get('pass_count', 0)} assertions passed, "
        f"{summary.get('fail_count', 0)} failed, {len(results)} scenarios"
    )
    return status, message, summary


def _write_evidence(
    document: PlanDocument,
    results: dict[str, ScenarioResult],
    status: str,
) -> Path:
    log_records: list[dict[str, Any]] = []
    log_path = document.spec_dir / "qa" / "qa-run.ndjson"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("kind") == "assert" and record.get("result") == "PASS":
            log_records.append(record)
    manifest_path = document.spec_dir / "qa" / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts_by_scenario: dict[str, list[str]] = {}
    for artifact in manifest.get("artifacts", []):
        scenario = artifact.get("scenario") if isinstance(artifact, dict) else None
        if scenario:
            artifacts_by_scenario.setdefault(str(scenario), []).append(str(artifact["path"]))

    def row(item: Any) -> dict[str, Any]:
        source = item if isinstance(item, dict) else {"id": str(item)}
        item_id = str(source["id"])
        records = [record for record in log_records if item_id in record.get("covers", [])]
        refs: list[str] = []
        evidence: list[str] = []
        for index, record in enumerate(records, start=1):
            scenario = str(record.get("scenario", ""))
            action = record.get("action", index)
            refs.append(f"{scenario}:assert:{action}")
            evidence.extend(artifacts_by_scenario.get(scenario, []))
        return {
            "id": item_id,
            "verdict": "Pass" if records else "Fail",
            "log_refs": refs,
            "evidence": sorted(set(evidence)),
        }

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
