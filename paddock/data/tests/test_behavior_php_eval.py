"""PHP benchmark truth is executed independently; semantic scores use validated IDs."""
from __future__ import annotations

import json
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
FIXTURE = DATA / "fixtures/okf-behavior-php"


def _php() -> list[str]:
    """The PHP interpreter: the binary on PATH, else the official CLI image under Docker.

    A missing interpreter is an assertion failure, not a green skip, the same as Go and Node.
    """
    php = shutil.which("php")
    if php is not None:
        return [php]
    docker = shutil.which("docker")
    assert docker is not None, "PHP (or Docker for the php:8.3-cli image) is required for the controlled behavior oracle"
    return [docker, "run", "--rm", "-v", "{cwd}:/work:ro", "-w", "/work", "php:8.3-cli", "php"]


@pytest.mark.parametrize(("before", "after", "failure"), [
    ("", "", ""),
    ('throw new InvalidArgumentException("limit must be nonnegative");', "$limit = 0;", "error"),
    ('return ["status" => "empty", "count" => 0];', 'return ["status" => "sent", "count" => 0];', "empty"),
    ('return ["status" => "sent", "count" => count($selected)];',
     'return ["status" => "queued", "count" => count($selected)];', "success"),
    ("array_push($sent, ...$selected);", "$sent = $selected;", "success"),
])
def test_php_oracle_rejects_each_real_behavior_mutant(
    tmp_path: Path, before: str, after: str, failure: str,
) -> None:
    shutil.copytree(FIXTURE / "source", tmp_path / "source")
    shutil.copyfile(FIXTURE / "oracle/service_test.php", tmp_path / "source/service_test.php")
    source = tmp_path / "source/service.php"
    if before:
        text = source.read_text()
        assert text.count(before) == 1
        source.write_text(text.replace(before, after))
    command = [part.format(cwd=source.parent) for part in _php()] + ["service_test.php"]
    result = subprocess.run(command, cwd=source.parent, capture_output=True, text=True, timeout=300)
    if failure:
        assert result.returncode != 0, "oracle accepted a known source defect"
        assert f"not ok {failure}" in _summary(result.stdout), result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        for name in ("success", "empty", "error", "empty-error", "zero", "bounded"):
            assert f"ok {name}" in _summary(result.stdout), result.stdout


def _summary(tap: str) -> set[str]:
    """Map TAP result lines to `ok <case>` / `not ok <case>` so numbering never matters."""
    summary: set[str] = set()
    for line in tap.splitlines():
        if line.startswith(("ok ", "not ok ")):
            verdict, _, name = line.partition(" - dispatch contract/")
            name = name.split(" #", 1)[0]
            summary.add(f"{'not ok' if verdict.startswith('not') else 'ok'} {name}")
    return summary


@pytest.mark.parametrize("missing", [False, True])
def test_php_task_uses_separate_fixture_without_changing_seed(tmp_path: Path, missing: bool) -> None:
    task = loader.load_named(DATA, "okf-behavior-audit")
    stage = tmp_path / "stage"
    repo = stage / "repo"
    shutil.copytree(DATA / "fixtures/okf-behavior/source", repo)
    before = {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
    run = Run(task=task, label="php-test", stage=stage, repo=repo, scratch=tmp_path,
              config=DATA / task.config, data_dir=DATA, store=tmp_path,
              seed=Pointer.load(DATA / "configs/seeds/okf-behavior.toml"),
              project=DATA.parents[1], params={"language": "php"})
    task.steps[0].fn(run)
    cases = stage / "artifacts/cases"
    trials = json.loads((cases / "trials.json").read_text())
    assert [trial["id"] for trial in trials] == ["control", "omissions", "incorrect"]
    assert {trial["source"] for trial in trials} == {"service.php"}
    assert {str(p.relative_to(repo)): p.read_bytes() for p in repo.rglob("*") if p.is_file()} == before
    for trial in trials:
        witness = cases / trial["id"] / "witness"
        assert not (witness / "service.py").exists()
        assert not list(witness.rglob("*truth*"))
        assert not list(witness.rglob("*_test.php"))
        assert (witness / "service.php").read_bytes() == (FIXTURE / "source/service.php").read_bytes()
    assert trials[0]["expected"] == {}
    assert set(trials[1]["expected"]) == {"OMIT-ERROR", "OMIT-EMPTY"}
    assert set(trials[2]["expected"]) == {"WRONG-RESPONSE", "WRONG-EFFECT"}
    toolchain = json.loads((cases / "toolchain.json").read_text())
    assert toolchain["language"] == "php" and toolchain["behavior_hashes"]["behavior_tree.py"]
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
        params = json.loads(call.args[call.args.index("--params") + 1])
        assert params["source_path"] == "service.php" and params["max_packets"] == 1
    outcomes = []
    for trial in trials:
        directory = cases / trial["id"]
        packet = AuditPreparation.model_validate_json((directory / "preparation.json").read_text()).packets[0]
        verdicts = AuditVerdicts(
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
    source = cases / "control/witness/service.php"
    source.write_text(source.read_text().replace('"sent"', '"queued"'))
    with pytest.raises(ValueError, match="stale prepared evidence"):
        task.score(run)
