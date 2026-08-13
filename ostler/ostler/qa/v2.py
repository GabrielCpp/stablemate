"""Version-2 QA orchestration across command, browser, and mobile drivers."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ostler.qa.drivers import DriverBlocked, QaDriver, ScenarioResult, create_driver
from ostler.qa.plan import PlanDocument, check_runtime_requirements
from ostler.qa.sandbox import Sandbox, SandboxConfig
from ostler.qa.session import QA_DIRNAME, QaSession


def run_plan(
    document: PlanDocument,
    *,
    root: Path,
    stop_on_fail: bool = False,
    only: list[str] | None = None,
    qa_dirname: str = QA_DIRNAME,
    sandboxed: bool = False,
) -> tuple[str, str, dict[str, Any]]:
    """Execute a validated plan and return ``(status, message, summary)``.

    ``only`` runs just the named scenarios — the rest of the plan is skipped, and so are the
    targets none of them use. ``qa_dirname`` puts the ledger somewhere other than ``qa/``.
    Together they are the dry run a planner uses to find out whether a scenario it just wrote
    actually resolves, without paying for the whole plan and without leaving anything the
    evidence gate would later read as a result: outside ``qa/`` no ``qa-evidence.json`` is
    written at all, so a plan tuned until it passed cannot become its own proof.
    """
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

    # After selection, not before. This used to run against every target the plan declares,
    # so a one-scenario dry run of an HTTP check was blocked by a mobile toolchain it would
    # never have touched — and the block reads as a plan defect, not a machine one.
    runtime_problems = check_runtime_requirements(
        document, targets=wanted_targets, sandboxed=sandboxed
    )
    if runtime_problems:
        message = "QA run blocked:\n" + "\n".join(f"  - {item}" for item in runtime_problems)
        return "blocked", message, {"status": "blocked", "problems": runtime_problems}

    qa_dir = spec_dir / qa_dirname
    if qa_dir.exists():
        shutil.rmtree(qa_dir)
    qa_dir.mkdir(parents=True)
    if scored:
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
        qa_dirname=qa_dirname,
    )
    session.write_session_start()
    drivers: dict[str, QaDriver] = {}
    results: dict[str, ScenarioResult] = {}
    status = "passed"
    cleanup_errors: list[str] = []
    #: Why the run stopped, in the words of whatever raised. The ledger has always carried
    #: this as a `runner_error` record, but the caller only ever saw the counts below — so a
    #: run that died before its first scenario reported "0 scenarios" and nothing else, and
    #: the coder workflow's QA gate, having no cause to act on, sent a valid plan back to be
    #: re-planned until its rework guard ran out. A gate can only route around a failure it
    #: can read.
    runner_errors: list[str] = []
    summary: dict[str, Any] = {}
    evidence: Path | None = None
    #: Run-scoped, not module-scoped: it owns containers and a bound port, and the only
    #: place guaranteed to reach them again is the `finally` below. A singleton would leak
    #: both down every exception path this function already handles.
    sandbox: Sandbox | None = None
    try:
        if sandboxed:
            sandbox = Sandbox(SandboxConfig.load(root), session=session, root=root)
            sandbox.start()
        for daemon in plan.get("background", []):
            session.start_daemon(
                str(daemon["name"]),
                [session.expand(str(part), variables) for part in daemon["argv"]],
                ready_check=daemon.get("ready_check"),
                timeout=float(daemon.get("timeout", 30)),
                cwd=root,
            )
        for target_id, target in plan["targets"].items():
            if target_id not in wanted_targets:
                continue
            driver = create_driver(
                session,
                target_id,
                target,
                root=root,
                variables=variables,
                sandbox=sandbox,
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
                    # `_grade` composes the only account of *why* a scenario failed, and it
                    # was being computed and dropped: the ledger recorded a failure count and
                    # the reason survived nowhere but a stdout tail in `steps/`. A reader of
                    # the run artifacts could see that something failed and not what.
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
        # The class name earns its place: the failure that motivated this was an
        # `AttributeError` from inside the runner, and "'dict' object has no attribute
        # 'timeout'" reads like a plan defect until you know it is a Python one.
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
        if sandbox is not None:
            try:
                sandbox.stop()
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(f"sandbox: {exc}")
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

    summary.update(
        {
            "status": status,
            "runId": document.run_id,
            "qa_run_log": f"{qa_dirname}/qa-run.ndjson",
            "manifest": f"{qa_dirname}/run-manifest.json",
            "scenarios": {
                name: {
                    "status": result.status,
                    "assertions": result.assertions,
                    "failures": result.failures,
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
        """One criterion or obligation, judged against *every* assertion covering it.

        A criterion is Pass only when the run log proves it and nothing in the same log
        disproves it. Reading the passing assertions alone — which this did — makes a
        criterion Pass as soon as any one of its scenario's steps succeeded, so a live
        journey that walked eight steps and failed the ninth reported all seven ACs Pass
        under an `overall: Fail`. Downstream that artifact is worse than absent: the QA
        assessor either routes on a verdict the run contradicts, or spends a turn every
        pass rediscovering that it must read `qa-run.ndjson` instead.
        """
        source = item if isinstance(item, dict) else {"id": str(item)}
        item_id = str(source["id"])
        records = [record for record in log_records if item_id in record.get("covers", [])]
        failing = [record for record in records if record.get("result") != "PASS"]
        refs: list[str] = []
        evidence: list[str] = []
        for index, record in enumerate(records, start=1):
            scenario = str(record.get("scenario", ""))
            action = record.get("action", index)
            refs.append(f"{scenario}:assert:{action}")
            # Only a passing assertion's artifacts are proof. `artifact vet` requires each
            # Pass row to cite a file from this run's manifest, and a failing scenario's
            # trace would satisfy that check while proving the opposite.
            if record.get("result") == "PASS":
                evidence.extend(artifacts_by_scenario.get(scenario, []))
        row_data = {
            "id": item_id,
            "verdict": "Pass" if records and not failing else "Fail",
            "log_refs": refs,
            "evidence": sorted(set(evidence)),
        }
        if failing:
            # Named separately from `log_refs` so a consumer can route on the disproof
            # without re-deriving it from the log the artifact exists to summarize.
            row_data["failing_log_refs"] = [
                f"{record.get('scenario', '')}:assert:{record.get('action', '?')}"
                for record in failing
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
