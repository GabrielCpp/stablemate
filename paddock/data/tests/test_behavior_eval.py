"""The evaluator must detect semantic receipts, not citations or seeded keywords."""
from __future__ import annotations

import importlib.util
import json
import logging
import runpy
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from groom import sidecar
from ostler.behavior import AuditVerdicts, CandidateVerdict, ClaimVerdict, validate_verdicts
from ostler import checks
from ostler.qa.harness_host import load_harness_module
from paddock import loader
from paddock.pointer import Pointer
from paddock.runner import Run
from workhorse import testing
from workhorse.templates import render
import workhorse_workflows
from workhorse_workflows.okf_builder.shared.audit import AuditScope, preparation
from workhorse_workflows.okf_builder.shared.vocabulary import check_vocabulary
from workhorse_workflows.coder.shared.review import check_feedback

DATA = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("behavior_eval", DATA / "tasks/_behavior_eval.py")
assert spec is not None and spec.loader is not None
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
evaluation.Case.model_rebuild(_types_namespace=vars(evaluation))
evaluation.Slice.model_rebuild(_types_namespace=vars(evaluation))
evaluation.RepairedSlice.model_rebuild(_types_namespace=vars(evaluation))


def test_wrong_or_unrelated_ids_do_not_get_detection_credit() -> None:
    result = evaluation.exact_score({"DEFECT-A": {"claim:a"}}, {"claim:ab", "candidate:z"})
    assert result["caught"] == []
    assert result["missed"] == ["DEFECT-A"]
    assert result["unmatched_adverse"] == ["candidate:z", "claim:ab"]


def test_duplicate_aliases_count_as_one_defect_and_control_flags_false_alarms() -> None:
    result = evaluation.exact_score({"DEFECT-A": {"claim:a", "candidate:b"}}, {"claim:a", "candidate:b"})
    assert result["caught"] == ["DEFECT-A"]
    assert result["missed"] == []
    assert result["unmatched_adverse"] == []
    assert evaluation.exact_score({}, {"claim:a"})["unmatched_adverse"] == ["claim:a"]


def test_mutants_retain_resolving_citations_and_change_only_intended_claims() -> None:
    book = (DATA / "fixtures/okf-behavior/source/docs/features/dispatch/dispatch.md").read_text()
    omitted = evaluation.variant_book(book, "omissions")
    wrong = evaluation.variant_book(book, "incorrect")
    assert "- raises:" not in omitted
    assert "For empty input" not in omitted
    assert "exactly three" in wrong
    assert "Replaces" in wrong
    assert "status `queued`" in wrong
    for text in (book, omitted, wrong):
        assert "- code: service.py::dispatch" in text
    with pytest.raises(ValueError, match="unknown case"):
        evaluation.variant_book(book, "typo")


def test_witness_hash_reads_each_case_source_not_live_checkout(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "source.py").write_text("return_value = 1\n")
    (second / "source.py").write_text("return_value = 2\n")
    assert evaluation.file_hashes(first)["source.py"] != evaluation.file_hashes(second)["source.py"]


def test_adjudication_cannot_silently_drop_an_alarm_or_apply_to_another_run() -> None:
    record = evaluation.Adjudication(packet_digest="current", false_positive_repairs=["claim:a"], explanation="Verified source")
    assert evaluation.adjudicate(record, "current", {"claim:a"})["false_positive_repairs"] == ["claim:a"]
    with pytest.raises(ValueError, match="every unmatched"):
        evaluation.adjudicate(record, "current", {"claim:a", "claim:b"})
    with pytest.raises(ValueError, match="stale"):
        evaluation.adjudicate(record, "other", {"claim:a"})


def test_absent_usage_is_unknown_not_zero_cost(tmp_path: Path) -> None:
    result = evaluation.usage(tmp_path)
    assert result["input_tokens"] is None
    assert result["reported_cost_usd"] is None
    assert result["estimated_cost_usd"] is None


def test_fixture_execution_independently_confirms_error_default_response_and_effect() -> None:
    dispatch = runpy.run_path(str(DATA / "fixtures/okf-behavior/source/service.py"))["dispatch"]
    sent = ["existing"]
    assert dispatch(["a", "b", "c"], sent) == {"status": "sent", "count": 2}
    assert sent == ["existing", "a", "b"]
    assert dispatch([], sent) == {"status": "empty", "count": 0}
    assert sent == ["existing", "a", "b"]
    with pytest.raises(ValueError, match="limit must be nonnegative"):
        dispatch(["d"], sent, -1)
    assert sent == ["existing", "a", "b"]
    assert dispatch(["a"], sent, 0) == {"status": "sent", "count": 0}
    assert sent == ["existing", "a", "b"]


@pytest.mark.parametrize(("support_context", "book_state"), [(False, "baseline"), (True, "baseline"), (True, "repaired")])
def test_real_task_composition_keeps_truth_out_of_witness_and_rejects_stale_source(
    tmp_path: Path, support_context: bool, book_state: str,
) -> None:
    task = loader.load_named(DATA, "okf-behavior-audit")
    stage = tmp_path / "stage"
    repo = stage / "repo"
    shutil.copytree(DATA / "fixtures/okf-behavior/source", repo)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    run = Run(task=task, label="test", stage=stage, repo=repo, scratch=scratch,
              config=DATA / task.config, data_dir=DATA, store=tmp_path,
              seed=Pointer.load(DATA / "configs/seeds/okf-behavior.toml"),
              project=DATA.parents[1], params={
                  "cases": ("stablemate-groom,stablemate-workflows" if book_state == "repaired"
                            else "control,omissions,incorrect,stablemate-groom,stablemate-workflows"),
                  "book_state": book_state,
                  **({"support_context": "true"} if support_context else {}),
              })
    task.steps[0].fn(run)
    task.steps[1].fn(run)
    cases = stage / "artifacts/cases"
    trials = json.loads((cases / "trials.json").read_text())
    selections = {item["id"]: item for item in json.loads(
        (DATA / "fixtures/okf-behavior/stablemate-slices.json").read_text())}
    with patch.object(Run, "cli", return_value=subprocess.CompletedProcess([], 0)) as cli, \
            patch("groom.store.run_profile", return_value={}):
        task.steps[2].fn(run)
    assert cli.call_count == len(trials)
    for call, trial in zip(cli.call_args_list, trials, strict=True):
        params = json.loads(call.args[call.args.index("--params") + 1])
        expected_context = selections[trial["id"]]["context"] if support_context and trial["id"] in selections else []
        assert trial["context_paths"] == params["context_paths"] == expected_context
    assert json.loads((cases / "toolchain.json").read_text())["support_context"] is support_context
    outcomes = []
    for trial in trials:
        name = trial["id"]
        directory = cases / name
        assert not list((directory / "witness").rglob("*truth*"))
        assert not list((directory / "witness").rglob("repaired-slices.json"))
        prepared = evaluation.prepare(directory / "witness", trial["source"], context_paths=trial["context_paths"])
        assert json.loads(prepared.model_dump_json()) == json.loads((directory / "preparation.json").read_text())
        assert prepared == preparation(AuditScope(
            docs_path=str(directory / "witness"), source_path=trial["source"],
            service=trial["service"], context_paths=tuple(trial["context_paths"]),
        ))
        caller_only = evaluation.prepare(directory / "witness", trial["source"])
        assert prepared.inventory.candidates == caller_only.inventory.candidates
        for relative in trial["context_paths"]:
            helper = directory / "witness" / relative
            assert helper.read_bytes() == (run.project / relative).read_bytes()
            assert helper.read_text() in [context.text for packet in prepared.packets for context in packet.support_context]
        packet = prepared.packets[0]
        if book_state == "repaired":
            assert trial["expected"] == {}
            assert (directory / "repair.json").is_file()
            assert "fixed_defect_ids" not in packet.model_dump_json()
        verdicts = AuditVerdicts(packet_digest=packet.digest,
                                 claims=tuple(ClaimVerdict(id=item.id, status="unresolved", explanation="Test abstention")
                                              for item in packet.claims),
                                 candidates=tuple(CandidateVerdict(id=item.id, status="missing" if book_state == "repaired" else "unresolved", explanation="Synthetic receipt")
                                                  for item in packet.candidates))
        report = validate_verdicts(packet, verdicts)
        output = directory / "review.json"
        output.write_text(json.dumps({"status": "partial", "reports": [report.model_dump(mode="json")]}))
        outcomes.append({"id": name, "returncode": 0, "seconds": 1, "unchanged": True,
                         "report": str(output.relative_to(stage)), "model_turns": 1})
    (cases / "outcomes.json").write_text(json.dumps(outcomes))
    assert task.score is not None
    result = task.score(run)
    if book_state == "repaired":
        for row in result.data["cases"]:
            assert row["caught"] == row["missed"] == []
            assert row["unmatched_adverse"] == row["adverse"]
            assert row["unmatched_adverse"]
            assert row["unresolved"]
        return
    assert result.data["cases"][1]["caught"] == []
    assert result.data["cases"][1]["missed"] == ["OMIT-EMPTY", "OMIT-ERROR"]
    assert result.data["cases"][0]["unmatched_adverse"] == []
    if support_context:
        for name in ("stablemate-groom", "stablemate-workflows"):
            for relative in selections[name]["context"]:
                helper = cases / name / "witness" / relative
                original = helper.read_bytes()
                helper.write_bytes(original + b"\n# Helper evidence changed.\n")
                with pytest.raises(ValueError, match=f"{name}: stale prepared evidence"):
                    task.score(run)
                helper.write_bytes(original)
        return
    (cases / "omissions/witness/service.py").write_text("def dispatch():\n    return None\n")
    with pytest.raises(ValueError, match="stale prepared evidence"):
        task.score(run)


@pytest.mark.parametrize("context_path", ["missing.py", "../outside.py"])
def test_prepare_rejects_unavailable_or_unbound_support(tmp_path: Path, context_path: str) -> None:
    shutil.copytree(DATA / "fixtures/okf-behavior/source", tmp_path, dirs_exist_ok=True)
    with pytest.raises(ValueError, match="missing.py|inside root"):
        evaluation.prepare(tmp_path, "service.py", context_paths=(context_path,))


@pytest.mark.parametrize("case_id", ["stablemate-groom", "stablemate-workflows"])
@pytest.mark.parametrize("state", ["unrepaired", "mixed", "missing", "wrong-section", "repaired"])
def test_repaired_truth_requires_actual_replacement(tmp_path: Path, case_id: str, state: str) -> None:
    selection = next(evaluation.Slice.model_validate(item) for item in json.loads(
        (DATA / "fixtures/okf-behavior/stablemate-slices.json").read_text()) if item["id"] == case_id)
    repair = next(evaluation.RepairedSlice.model_validate(item) for item in json.loads(
        (DATA / "fixtures/okf-behavior/repaired-slices.json").read_text()) if item["id"] == case_id)
    replacement = repair.replacements[0]
    text = {"unrepaired": replacement.before, "mixed": replacement.before + "\n" + replacement.after,
            "missing": "", "wrong-section": "### other\n" + replacement.after,
            "repaired": replacement.after}[state]
    book = tmp_path / selection.book
    book.parent.mkdir(parents=True)
    book.write_text(selection.heading + "\n\n" + text)
    if state != "repaired":
        with pytest.raises(ValueError, match=case_id):
            evaluation.repaired_truth(tmp_path, selection, repair)
        return
    assert evaluation.repaired_truth(tmp_path, selection, repair).defects == []
    selection.defects.append(evaluation.Defect(id="OTHER-DEFECT", explanation="Not repaired"))
    with pytest.raises(ValueError, match="baseline defect IDs"):
        evaluation.repaired_truth(tmp_path, selection, repair)


@pytest.mark.parametrize("params", [
    {"book_state": "typo"},
    {"book_state": "repaired", "cases": "control"},
    {"book_state": "repaired", "cases": "stablemate-workhorse"},
    {"book_state": "repaired", "replay_stage": "unused"},
])
def test_repaired_arm_cannot_clear_unselected_truth_or_relabel_replay(tmp_path: Path, params: dict[str, str]) -> None:
    task = loader.load_named(DATA, "okf-behavior-audit")
    run = Run(task=task, label="reject", stage=tmp_path, repo=tmp_path, scratch=tmp_path,
              config=DATA / task.config, data_dir=DATA, store=tmp_path,
              seed=Pointer.load(DATA / "configs/seeds/okf-behavior.toml"),
              project=DATA.parents[1], params=params)
    with pytest.raises(ValueError, match="book_state"):
        task.steps[0].fn(run)


@pytest.mark.parametrize("text", ["[]", '"node"', "1", "true", "null"])
def test_corrected_nonobject_claim_matches_actual_sidecar_boundary(tmp_path: Path, text: str) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "checkpoint.json").write_text(text)
    with patch.object(sidecar, "RUNS_DIR", tmp_path):
        assert sidecar._current_node() == ""


def test_corrected_feedback_claim_matches_returned_schema() -> None:
    with patch("workhorse_workflows.coder.shared.review.poll_run_inbox", return_value=("operator note", "epic")):
        result = check_feedback(logging.getLogger(__name__), run_dir="unused")
    assert result.model_dump() == {"present": True, "content": "operator note"}


def test_postrepair_unmatched_decoding_failure_is_real(tmp_path: Path) -> None:
    """Adjudicate the v5 raises:1 alarm without changing its truth or repairing another claim."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "checkpoint.json").write_bytes(b"\xff")
    with patch.object(sidecar, "RUNS_DIR", tmp_path), pytest.raises(UnicodeDecodeError):
        sidecar._current_node()


def test_current_node_book_distinguishes_normalized_io_from_decoding_failure() -> None:
    """Reject the uniform unreadable-input promise, including its prose duplicates."""
    book = (DATA.parents[1] / "docs/features/groom/concepts/sidecar-snapshot.md").read_text()
    method = book.split("### method-_current_node\n", 1)[1].split("### method-_terminal", 1)[0]
    claims = [" ".join(part.split("\n- ", 1)[0].split()) for part in method.split("- raises: ")[1:]]
    assert len(claims) == 3, "Declare decoding failure separately from the two normalization claims"
    assert "OSError" in claims[0] and "unreadable" not in claims[0]
    assert "UnicodeDecodeError" in claims[2] and "propagates" in claims[2]
    for section in (book.split("## Contract\n", 1)[1].split("## Algorithm", 1)[0], method):
        assert "unreadable checkpoints" not in section
        assert "checkpoint cannot be read" not in section
        assert "UnicodeDecodeError" in section


def test_current_node_normalizes_checkpoint_read_oserror(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    checkpoint = run / "checkpoint.json"
    checkpoint.write_text('{"current_id": "write_story"}')
    with patch.object(sidecar, "RUNS_DIR", tmp_path):
        assert sidecar._current_node() == "write_story"
        with patch.object(Path, "read_text", side_effect=OSError("checkpoint read failed")) as read:
            assert sidecar._current_node() == ""
        read.assert_called_once_with()


@pytest.mark.parametrize("case", ["missing", "wrong-content", "noop", "wrong-exception",
                                 "verifier-assertion", "verifier-value-error"])
def test_repair_capture_example_records_real_helper_evidence(tmp_path: Path, case: str) -> None:
    """The rendered scenario must reject a no-op, not manufacture its expected exception."""
    workflow_dir = Path(workhorse_workflows.__file__).parent / "okf_builder"
    rendered = render("main/prompts/repair.md", {
        "item_code": "undeclared-obligation", "check_vocabulary": check_vocabulary(),
    }, workflow_dir)
    example = rendered.split("```python\n", 1)[1].split("```", 1)[0]
    declaration = rendered.split("```markdown\n- verify: ", 1)[1].split("\n", 1)[0]
    call = checks.parse_check(declaration)
    assert not isinstance(call, str), call
    assert call.name == "json_path"
    assert dict(call.args) == {"path": "exception.type", "equals": "AssertionError"}

    harness = load_harness_module("ostler_qa")
    covers = ["okf:docs/features/acme/testing.md#contains:does:1"]
    ledger = tmp_path / "records.jsonl"
    rel, text = "sample.txt", "required text"
    expected_message = (
        "Expected file 'sample.txt' to exist in sandbox, but it does not" if case == "missing"
        else "Expected 'sample.txt' to contain 'required text'\nActual content:\ndifferent content\n"
    )
    if case != "missing":
        (tmp_path / rel).write_text("different content\n", encoding="utf-8")
    with ledger.open("w") as sink:
        qa = harness.Qa(scenario_id="helper-capture", target=harness.Target("python"),
                        root=tmp_path, spec_dir=tmp_path, qa_dir=tmp_path,
                        covers=covers, recorder=harness._Recorder(fd=sink.fileno()))
        namespace = {"qa": qa, "sandbox": tmp_path, "rel": rel, "text": text, "covers": covers}
        code = compile(example, "repair.md:scenario-example", "exec")
        if case == "noop":
            with patch.object(testing, "assert_file_contains", return_value=None):
                exec(code, namespace)
        elif case == "wrong-exception":
            with patch.object(testing, "assert_file_contains", side_effect=TypeError("wrong product error")), \
                    pytest.raises(TypeError, match="wrong product error"):
                exec(code, namespace)
        elif case.startswith("verifier-"):
            error = AssertionError if case == "verifier-assertion" else ValueError

            def reject_verification(*args: object) -> None:
                raise error("verifier error")

            with patch.dict(harness.VERIFIERS, {"json_path": reject_verification}), \
                    pytest.raises(error, match="verifier error"):
                exec(code, namespace)
        else:
            exec(code, namespace)
            qa.verify("json_path", namespace["observed"], path="exception.message",
                      equals=expected_message, covers=covers)

    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    if case in {"wrong-exception", "verifier-assertion", "verifier-value-error"}:
        assert records == []
        assert qa.assertions == qa.failures == 0
        return
    assert len(records) == (1 if case == "noop" else 2)
    assert all(record["type"] == "assert" and record["check"] == "json_path"
               and record["covers"] == covers for record in records)
    assert records[0]["check_args"] == dict(call.args)
    assert records[0]["passed"] is (case != "noop")
    if case == "noop":
        assert namespace["observed"] == {"exception": {}}
        assert records[0]["actual"] == {"present": False}
        assert records[0]["expected"] == {"path": "exception.type"}
        assert qa.assertions == qa.failures == 1
    else:
        assert records[0]["actual"] == records[0]["expected"] == "AssertionError"
        assert records[1]["passed"] is True
        assert records[1]["actual"] == records[1]["expected"] == expected_message
        assert records[1]["check_args"] == {"path": "exception.message", "equals": expected_message}
        assert qa.assertions == 2 and qa.failures == 0
