"""Go benchmark truth is executed independently; semantic scores use validated IDs."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from ostler.behavior import AuditPreparation, AuditVerdicts, CandidateVerdict, ClaimVerdict, validate_verdicts
from paddock import loader
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]
FIXTURE = DATA / "fixtures/okf-behavior-go"


@pytest.mark.parametrize(("before", "after", "failure"), [
    ("", "", ""),
    ('errors.New("limit must be nonnegative")', 'nil', "error"),
    ('return "empty", 0, nil', 'return "sent", 0, nil', "empty"),
    ('return "sent", len(selected), nil', 'return "queued", len(selected), nil', "success"),
    ('append(*sent, selected...)', 'append([]string{}, selected...)', "success"),
])
def test_go_oracle_rejects_each_real_behavior_mutant(
    tmp_path: Path, before: str, after: str, failure: str,
) -> None:
    go = shutil.which("go")
    assert go is not None, "Go compiler is required for the controlled behavior oracle"
    shutil.copytree(FIXTURE / "source", tmp_path / "source")
    shutil.copyfile(FIXTURE / "oracle/service_test.go", tmp_path / "source/service_test.go")
    source = tmp_path / "source/service.go"
    if before:
        text = source.read_text()
        assert text.count(before) == 1
        text = text.replace(before, after)
        if failure == "error":
            text = text.replace('import "errors"\n', "")
        source.write_text(text)
    result = subprocess.run([go, "test", "-count=1", "-v", "./..."], cwd=source.parent,
                            env={**os.environ, "GOCACHE": str(tmp_path / "cache"), "GOWORK": "off"},
                            capture_output=True, text=True, timeout=120)
    if failure:
        assert result.returncode != 0, "oracle accepted a known source defect"
        assert f"--- FAIL: TestDispatchContract/{failure}" in result.stdout, result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        for name in ("success", "empty", "error", "empty-error", "zero", "bounded"):
            assert f"--- PASS: TestDispatchContract/{name}" in result.stdout


@pytest.mark.parametrize("missing", [False, True])
def test_go_task_uses_separate_fixture_without_changing_seed(tmp_path: Path, missing: bool) -> None:
    task = loader.load_named(DATA, "okf-behavior-audit")
    stage = tmp_path / "stage"
    repo = stage / "repo"
    shutil.copytree(DATA / "fixtures/okf-behavior/source", repo)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    run = Run(task=task, label="go-test", stage=stage, repo=repo, scratch=tmp_path,
              config=DATA / task.config, data_dir=DATA, store=tmp_path,
              seed=Pointer.load(DATA / "configs/seeds/okf-behavior.toml"),
              project=DATA.parents[1], params={"language": "go"})
    task.steps[0].fn(run)
    cases = stage / "artifacts/cases"
    trials = json.loads((cases / "trials.json").read_text())
    assert [trial["id"] for trial in trials] == ["control", "omissions", "incorrect"]
    assert {trial["source"] for trial in trials} == {"service.go"}
    assert {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before
    for trial in trials:
        witness = cases / trial["id"] / "witness"
        assert not (witness / "service.py").exists()
        assert not list(witness.rglob("*truth*"))
        assert not list(witness.rglob("*_test.go"))
        assert (witness / "service.go").read_bytes() == (FIXTURE / "source/service.go").read_bytes()
    assert trials[0]["expected"] == {}
    assert set(trials[1]["expected"]) == {"OMIT-ERROR", "OMIT-EMPTY"}
    assert set(trials[2]["expected"]) == {"WRONG-RESPONSE", "WRONG-EFFECT"}
    books = [(cases / trial["id"] / "witness/docs/features/dispatch/dispatch.md").read_text() for trial in trials]
    assert len(books[0].split("\n- ")) - len(books[1].split("\n- ")) == 2
    assert "- raises:" not in books[1] and "For empty input" not in books[1]
    assert books[2] == books[0].replace(
        "Appends the selected items, in input order, to the supplied sent list.",
        "Replaces the supplied sent list with the selected items in input order.",
    ).replace("status `sent`", "status `queued`")
    task.steps[1].fn(run)
    with patch.object(Run, "cli", return_value=subprocess.CompletedProcess([], 0)) as cli, \
            patch("groom.store.run_profile", return_value={}):
        task.steps[2].fn(run)
    assert cli.call_count == 3
    for call in cli.call_args_list:
        assert "workhorse-okf-builder" in call.args
        index = call.args.index("workhorse-okf-builder")
        assert call.args[index + 1:index + 3] == ("run", "audit")
        params = json.loads(call.args[call.args.index("--params") + 1])
        assert params["source_path"] == "service.go" and params["max_packets"] == 1
    outcomes = []
    for trial in trials:
        directory = cases / trial["id"]
        packet = AuditPreparation.model_validate_json((directory / "preparation.json").read_text()).packets[0]
        verdicts = AuditVerdicts(packet_digest=packet.digest,
                                claims=tuple(ClaimVerdict(id=item.id, status="unresolved", explanation="sent queued append error")
                                             for item in packet.claims),
                                candidates=tuple(CandidateVerdict(id=item.id, status="missing" if missing else "unresolved",
                                                                  explanation="sent queued append error")
                                                 for item in packet.candidates))
        report = validate_verdicts(packet, verdicts)
        output = directory / "review.json"
        output.write_text(json.dumps({"status": "partial", "reports": [report.model_dump(mode="json")]}))
        outcomes.append({"id": trial["id"], "returncode": 0, "seconds": 1, "unchanged": True,
                         "report": str(output.relative_to(stage)), "model_turns": 1})
    (cases / "outcomes.json").write_text(json.dumps(outcomes))
    assert task.score is not None
    rows = task.score(run).data["cases"]
    assert rows[1]["caught"] == (["OMIT-EMPTY", "OMIT-ERROR"] if missing else [])
    assert rows[1]["missed"] == ([] if missing else ["OMIT-EMPTY", "OMIT-ERROR"])
    assert rows[2]["caught"] == []
    assert rows[2]["missed"] == ["WRONG-EFFECT", "WRONG-RESPONSE"]
    assert bool(rows[0]["unmatched_adverse"]) is missing
    source = cases / "control/witness/service.go"
    source.write_text(source.read_text().replace('"sent"', '"queued"'))
    with pytest.raises(ValueError, match="stale prepared evidence"):
        task.score(run)
