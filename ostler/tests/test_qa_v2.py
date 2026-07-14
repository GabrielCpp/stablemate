from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from ostler.artifact.kinds import _qa_evidence_vet
from ostler.qa.plan import load_plan, validate_v2
from ostler.qa.run import cmd_run, cmd_validate
from ostler.qa.drivers import _compile_maestro


def _context(spec: Path) -> str:
    obligation = "okf:docs/features/demo/item.md:contract"
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "base": "base",
                "head": "head",
                "changedCode": [],
                "directNodes": [],
                "contracts": [],
                "journeys": [],
                "journeyNodes": [],
                "verificationRefs": [],
                "healthFindings": [],
                "acceptanceCriteria": [],
                "obligations": [
                    {
                        "id": obligation,
                        "kind": "contract",
                        "node": "item",
                        "source": "docs/features/demo/item.md",
                        "requirement": "item is emitted",
                        "evidenceRequired": "live",
                        "reasons": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return obligation


def _plan(spec: Path, obligation: str) -> Path:
    plan = {
        "version": 2,
        "run_id": "qa-run-1",
        "story": "story-1",
        "targets": {"api": {"driver": "command"}},
        "scenarios": [
            {
                "id": "api-contract",
                "target": "api",
                "mechanism": "live",
                "covers": [obligation],
                "actions": [
                    {
                        "do": "command",
                        "id": "emit",
                        "cmd": "printf '{\"value\":\"ok\"}'",
                        "assert_contains": "ok",
                        "out": "qa/steps/emit.json",
                    }
                ],
            }
        ],
    }
    path = spec / "qa-plan.yml"
    path.write_text(yaml.safe_dump(plan, sort_keys=False), encoding="utf-8")
    return path


def test_v2_command_run_owns_log_manifest_and_evidence(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    stale = spec / "qa/stale.txt"
    stale.parent.mkdir()
    stale.write_text("old", encoding="utf-8")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed"
    assert not stale.exists()
    records = [
        json.loads(line)
        for line in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["kind"] == "session_start"
    assert records[-1]["kind"] == "session_stop"
    assert records[-1]["status"] == "passed"
    assert any(
        row.get("kind") == "assert"
        and obligation in row.get("covers", [])
        and row.get("result") == "PASS"
        for row in records
    )
    manifest = json.loads((spec / "qa/run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runId"] == "qa-run-1"
    for artifact in manifest["artifacts"]:
        artifact_path = spec / artifact["path"]
        assert artifact_path.is_file()
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["obligations"][0]["verdict"] == "Pass"
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []


def test_v2_validation_rejects_disposable_input_and_unasserted_coverage(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    (spec / "qa").mkdir(parents=True)
    obligation = _context(spec)
    payload = spec / "qa/payload.json"
    payload.write_text("{}", encoding="utf-8")
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["inputs"] = {"payload": "qa/payload.json"}
    data["scenarios"][0]["actions"][0].pop("assert_contains")
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    outcome = cmd_validate(plan, root=tmp_path)

    assert outcome.status == "invalid"
    assert any("disposable qa" in problem for problem in outcome.data["problems"])
    assert any("no machine assertion" in problem for problem in outcome.data["problems"])


def test_v2_secret_is_runtime_only_and_redacted(tmp_path: Path, monkeypatch):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["secrets"] = {"token": {"from_env": "QA_TOKEN"}}
    action = data["scenarios"][0]["actions"][0]
    action["cmd"] = "printf '{{secret.token}}'"
    action["assert_contains"] = "{{secret.token}}"
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    monkeypatch.setenv("QA_TOKEN", "top-secret-value")

    outcome = cmd_run(plan, root=tmp_path)

    assert outcome.status == "passed"
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [
            spec / "qa/qa-run.ndjson",
            spec / "qa/qa-session.json",
            spec / "qa/steps/emit.json",
        ]
        if path.exists()
    )
    assert "top-secret-value" not in persisted
    assert "{{secret.token}}" in (spec / "qa/qa-run.ndjson").read_text(encoding="utf-8")


def test_load_plan_requires_okf_context(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    plan = _plan(spec, "okf:missing")
    document, problems = load_plan(plan, spec, tmp_path)
    assert not problems and document is not None
    assert any("qa-okf-context.json is required" in item for item in validate_v2(document))


def test_maestro_compiler_emits_native_two_document_flow():
    flow = _compile_maestro(
        {"app_id": "com.example.app"},
        {
            "id": "profile",
            "actions": [
                {"do": "launch", "clear_state": False},
                {"do": "tap", "locator": {"text": "Profile"}},
                {"do": "fill", "locator": {"id": "display-name"}, "value": "Updated"},
                {"expect": "value", "locator": {"id": "display-name"}, "value": "Updated"},
                {"capture": "screenshot", "name": "profile-restored"},
            ],
        },
    )
    documents = list(yaml.safe_load_all(flow))
    assert documents[0] == {"appId": "com.example.app"}
    assert documents[1][0] == {"launchApp": {"clearState": False}}
    assert {"takeScreenshot": "profile-restored"} in documents[1]


def test_recording_cannot_be_disabled_by_the_plan_itself(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    obligation = _context(spec)
    plan = _plan(spec, obligation)
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    data["policy"] = {"recording_exempt_targets": ["web"]}
    data["targets"] = {
        "web": {
            "driver": "playwright",
            "base_url": "http://localhost:3000",
            "recording": {"required": False},
        }
    }
    data["scenarios"][0]["target"] = "web"
    data["scenarios"][0]["actions"] = [
        {"expect": "visible", "locator": {"role": "button", "name": "Add"}}
    ]
    plan.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = cmd_validate(plan, root=tmp_path)
    assert any("repository policy" in problem for problem in result.data["problems"])

    (tmp_path / "ostler.yml").write_text(
        "qa:\n  recordingExemptTargets: [web]\n",
        encoding="utf-8",
    )
    assert cmd_validate(plan, root=tmp_path).status == "passed"


def test_v1_plan_survives_cleanup_and_uses_static_inputs(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    inputs = spec / "qa-inputs"
    inputs.mkdir(parents=True)
    (inputs / "value.txt").write_text("stable-input", encoding="utf-8")
    plan = spec / "qa-plan.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "run_id": "legacy-run",
                "story": "story-1",
                "inputs": {"value": "qa-inputs/value.txt"},
                "steps": [
                    {
                        "id": "read-input",
                        "mechanism": "fixture",
                        "cmd": "cat {{input.value}}",
                        "assert_contains": "stable-input",
                        "out": "qa/steps/value.txt",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (spec / "qa").mkdir()
    (spec / "qa/stale").write_text("stale", encoding="utf-8")

    result = cmd_run(plan, root=tmp_path)

    assert result.status == "passed"
    assert (inputs / "value.txt").is_file()
    assert not (spec / "qa/stale").exists()
    assert (spec / "qa/steps/value.txt").read_text(encoding="utf-8") == "stable-input"


def test_v1_plan_and_inputs_are_rejected_under_disposable_qa(tmp_path: Path):
    spec = tmp_path / "docs/specs/story-1"
    qa = spec / "qa"
    qa.mkdir(parents=True)
    (qa / "input.json").write_text("{}", encoding="utf-8")
    plan = qa / "qa-plan.yml"
    plan.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "run_id": "bad",
                "story": "story-1",
                "inputs": {"payload": "qa/input.json"},
                "steps": [],
            }
        ),
        encoding="utf-8",
    )
    result = cmd_validate(plan, spec, root=tmp_path)
    assert any("qa-plan.yml cannot live" in item for item in result.data["problems"])
    assert any("input 'payload'" in item for item in result.data["problems"])
