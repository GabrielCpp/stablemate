"""Loading, validating and running a `qa_plan.py` — the format that replaces the v2 YAML."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ostler.qa.harness_host import load_harness_module
from ostler.qa.plan import load_plan, resolve_spec_dir, validate_v2
from ostler.qa.run import cmd_run, cmd_validate

OBLIGATION = "ac-1"

PLAN = '''\
import json

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    payload = json.load((qa.root / "out.json").open(encoding="utf-8"))
    qa.check("the item is the one requested", qa.field(payload, "item.id") == "abc",
             actual=qa.field(payload, "item.id"), expected="abc", covers=["{obligation}"])
'''


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    return spec


def _plan(spec: Path, source: str = PLAN) -> Path:
    module = spec / "qa_plan.py"
    module.write_text(source.format(obligation=OBLIGATION), encoding="utf-8")
    return module


def test_spec_dir_is_the_module_directory(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    assert resolve_spec_dir(_plan(spec), None, tmp_path) == spec.resolve()


def test_importing_a_plan_leaves_no_bytecode_beside_the_documentation(tmp_path: Path) -> None:
    """A spec directory is documentation under version control, not a package directory."""
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    assert cmd_validate(module, spec, root=tmp_path).ok
    assert cmd_run(module, spec, root=tmp_path).ok
    assert not (spec / "__pycache__").exists(), "bytecode was written into the spec directory"


def test_load_stamps_the_module_and_interpreter_on_every_target(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    document, problems = load_plan(module, spec, tmp_path)
    assert not problems and document is not None
    assert document.data["version"] == 3
    assert document.data["targets"]["api"]["module"] == str(module.resolve())
    assert Path(document.data["targets"]["api"]["interpreter"]).exists()


def test_a_valid_plan_has_no_problems(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_a_synthetic_mechanism_is_refused_and_named(tmp_path: Path) -> None:
    """`synthetic` named the one thing a QA run must never accept: a suite standing in for the product."""
    spec = _spec(tmp_path)
    source = PLAN.replace('mechanism="live"', 'mechanism="synthetic"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert document is None
    assert any("mechanism must be one of" in item for item in problems)

    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    document.data["scenarios"][0]["mechanism"] = "synthetic"
    reported = validate_v2(document)
    assert any("retired" in item and "fixture" in item for item in reported)


def test_an_unimportable_plan_fails_validation(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _plan(spec, "from ostler_qa import nonexistent_project_name\n")
    outcome = cmd_validate(spec / "qa_plan.py", spec, root=tmp_path)
    assert not outcome.ok
    assert "failed to import" in outcome.message
    assert "nonexistent_project_name" in outcome.message


def _extra_scenario(name: str, covers: str = "") -> str:
    """One more scenario on the same target, claiming *covers* (nothing when blank)."""
    binding = f", covers=[{covers!r}]" if covers else ""
    return f'''

@scenario(target=api, mechanism="live"{binding})
def {name}(qa: Qa) -> None:
    """Another look at the same behaviour."""
    qa.check("it held", True{binding})
'''


def test_a_second_scenario_on_one_obligation_is_within_the_budget(tmp_path: Path) -> None:
    """The branch split the allowance exists for: success in one function, conflict in another."""
    spec = _spec(tmp_path)
    source = PLAN + _extra_scenario("conflict_branch", OBLIGATION)
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    assert validate_v2(document) == []


def test_the_finding_says_which_helpers_checks_do_not_count(tmp_path: Path) -> None:
    """A helper this module does not define is where the static read genuinely stops."""
    spec = _spec(tmp_path)
    hollow = PLAN[: PLAN.index('    payload = json')] + "    _assert_it(qa)\n"
    document, problems = load_plan(_plan(spec, hollow), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "calls no qa.check()" in item]

    assert reported, "a scenario whose only checks live off this module still counts as zero"
    assert "helper" in reported[0] and "inline it here" in reported[0]


def test_a_module_helper_s_checks_count_for_the_scenario_that_calls_it(tmp_path: Path) -> None:
    """A scenario that calls `verify_created(qa, …)` asserts what the helper asserts."""
    spec = _spec(tmp_path)
    factored = PLAN.replace(
        '    qa.check("the item is the one requested", qa.field(payload, "item.id") == "abc",\n'
        '             actual=qa.field(payload, "item.id"), expected="abc", covers=["{obligation}"])\n',
        "    _assert_it(qa, payload)\n\n\n"
        "def _assert_it(qa: Qa, payload: dict) -> None:\n"
        '    qa.check("the item is the one requested", qa.field(payload, "item.id") == "abc",\n'
        '             actual=qa.field(payload, "item.id"), expected="abc", covers=["{obligation}"])\n',
    )
    document, problems = load_plan(_plan(spec, factored), spec, tmp_path)
    assert not problems and document is not None

    assert validate_v2(document) == []


def test_running_the_plan_records_the_assertion_as_evidence(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message

    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    item = next(row for row in evidence["criteria"] if row["id"] == OBLIGATION)
    assert item["verdict"] == "Pass"
    records = [
        json.loads(line)
        for line in (spec / "qa" / "qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]
    asserted = next(record for record in records if record.get("kind") == "assert")
    assert asserted["label"] == "the item is the one requested"
    assert asserted["result"] == "PASS"
    assert asserted["covers"] == [OBLIGATION]
    assert asserted["driver"] == "python"
    raw = json.loads((spec / "qa" / "asserts" / "item-is-emitted-1.json").read_text("utf-8"))
    assert raw == {"value": "abc", "expected": "abc"}


def test_a_failing_check_fails_the_run(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "wrong"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert not outcome.ok
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    row = next(item for item in evidence["criteria"] if item["id"] == OBLIGATION)
    assert row["verdict"] == "Fail"


def test_a_raising_scenario_reports_its_traceback(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    outcome = cmd_run(module, spec, root=tmp_path)
    assert not outcome.ok
    stdout = (spec / "qa" / "steps" / "item-is-emitted-stdout.txt").read_text(encoding="utf-8")
    assert "FileNotFoundError" in stdout


def test_by_text_matches_a_substring_and_takes_a_pattern() -> None:
    """`qa.by_text` defers to Playwright's own default rather than pinning `exact=True`."""
    harness = load_harness_module("ostler_qa")
    forwarded: list[tuple[Any, dict[str, Any]]] = []

    class _Page:
        def get_by_text(self, text: Any, **kwargs: Any) -> str:
            forwarded.append((text, kwargs))
            return "locator"

    qa = harness.Qa(
        scenario_id="s",
        target=harness.Target("web", driver="playwright"),
        root=Path("/"),
        spec_dir=Path("/"),
        qa_dir=Path("/"),
        covers=[],
        recorder=harness._Recorder(fd=-1),
    )
    qa.page = _Page()

    qa.by_text("not-a-docx.txt")
    pattern = re.compile("brouillon local", re.IGNORECASE)
    qa.by_text(pattern)
    qa.by_text("Publish", exact=True)

    assert forwarded == [("not-a-docx.txt", {}), (pattern, {}), ("Publish", {"exact": True})]


def test_a_computed_covers_list_claims_nothing(tmp_path: Path) -> None:
    """`extract_check_covers` reads the parsed tree, so only literal ids are recoverable."""
    spec = _spec(tmp_path)
    computed = PLAN.replace(
        'expected="abc", covers=["{obligation}"])',
        'expected="abc", covers=list(qa.covers))',
    )
    document, problems = load_plan(_plan(spec, computed), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any("the ids written literally" in item for item in reported)


def test_a_covers_list_of_module_constants_binds(tmp_path: Path) -> None:
    """A module-level `NAME = "okf:…"` is in the parse tree, so the gate can read it."""
    spec = _spec(tmp_path)
    named = f'CLAIM = "{OBLIGATION}"\n' + PLAN.replace(
        'expected="abc", covers=["{obligation}"])',
        "expected=\"abc\", covers=[CLAIM])",
    )
    document, problems = load_plan(_plan(spec, named), spec, tmp_path)
    assert not problems and document is not None

    assert validate_v2(document) == []


def test_a_rebound_module_constant_claims_nothing(tmp_path: Path) -> None:
    """Which value reached the call is a question the parse genuinely cannot answer."""
    spec = _spec(tmp_path)
    rebound = f'CLAIM = "{OBLIGATION}"\nCLAIM = "okf:docs/services/demo/item.md:does:1"\n' + PLAN.replace(
        'expected="abc", covers=["{obligation}"])',
        "expected=\"abc\", covers=[CLAIM])",
    )
    document, problems = load_plan(_plan(spec, rebound), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any("the ids written literally" in item for item in reported)


def test_an_unbound_check_is_not_credited_to_the_scenario_s_obligations(tmp_path: Path) -> None:
    """A ledger record carries the assertion's own binding, never the scenario's."""
    spec = _spec(tmp_path)
    extra = PLAN + '    qa.check("something else entirely", True)\n'
    module = _plan(spec, extra)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message

    records = [
        json.loads(line)
        for line in (spec / "qa" / "qa-run.ndjson").read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("kind") == "assert"
    ]
    bound = next(record for record in records if "requested" in record["label"])
    unbound = next(record for record in records if "something else" in record["label"])

    assert bound["covers"] == [OBLIGATION]
    assert unbound.get("covers", []) == []


def test_a_scenario_whose_only_assertion_retries_validates_clean(tmp_path: Path) -> None:
    """`eventually` is an assertion, and the gate has to agree — otherwise the doctrine tells an author to hold the sampler and the validator answers that their scenario proves nothing."""
    spec = _spec(tmp_path)
    retrying = PLAN.replace(
        '    qa.check("the item is the one requested", qa.field(payload, "item.id") == "abc",\n'
        '             actual=qa.field(payload, "item.id"), expected="abc", covers=["{obligation}"])\n',
        '    qa.eventually("the item is the one requested",\n'
        '                  lambda: payload["item"]["id"] == "abc",\n'
        '                  expected="abc", covers=["{obligation}"])\n',
    )
    document, problems = load_plan(_plan(spec, retrying), spec, tmp_path)

    assert not problems and document is not None
    assert validate_v2(document) == []


STEPPED_PLAN = '''\
import json

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def item_is_emitted(qa: Qa) -> None:
    """Two steps, one check in each, and a third check outside any step."""
    with qa.step("read the emitted item"):
        payload = json.load((qa.root / "out.json").open(encoding="utf-8"))
        qa.check("the item was read", True, actual=True, expected=True, covers=["{obligation}"])
    with qa.step("compare it to the request"):
        qa.check("the item is the one requested", qa.field(payload, "item.id") == "abc",
                 actual=qa.field(payload, "item.id"), expected="abc", covers=["{obligation}"])
    qa.check("tidy-up", True, actual="ok", expected="ok", covers=["{obligation}"])
'''


def _ledger(spec: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (spec / "qa" / "qa-run.ndjson").read_text(encoding="utf-8").splitlines()
    ]


def test_every_record_inside_a_step_carries_the_step_it_ran_in(tmp_path: Path) -> None:
    """The step record lands when the step closes — after its assertions — so order alone cannot attribute them; the stamp is what the report groups on."""
    spec = _spec(tmp_path)
    module = _plan(spec, STEPPED_PLAN)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message

    records = _ledger(spec)
    asserts = {r["label"]: r for r in records if r.get("kind") == "assert"}
    steps = [r for r in records if r.get("kind") == "step"]
    assert [s["label"] for s in steps] == ["read the emitted item", "compare it to the request"]
    assert all(s["exit_code"] == 0 and "unfinished" not in s for s in steps)
    assert asserts["the item was read"]["step"] == steps[0]["id"]
    assert asserts["the item was read"]["step_label"] == "read the emitted item"
    assert asserts["the item is the one requested"]["step"] == steps[1]["id"]
    assert "step" not in asserts["tidy-up"]
    for step in steps:
        assert isinstance(step["started_offset_ms"], int)
        assert isinstance(step["ended_offset_ms"], int)
        assert 0 <= step["started_offset_ms"] <= step["ended_offset_ms"]
    assert steps[0]["ended_offset_ms"] <= steps[1]["started_offset_ms"]
    assert outcome.data["report"] == "qa-report.md"
    report = (spec / "qa-report.md").read_text(encoding="utf-8")
    assert "<!-- run: qa-story-1 status: passed -->" in report
    assert "1. **read the emitted item** — ok" in report
    assert "   - ✓ the item was read — actual `true` (covers `" + OBLIGATION + "`)" in report
    assert "- _Outside any step_" in report
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["report"] == "qa-report.md"


def test_a_step_the_scenario_raises_inside_is_recorded_failed_with_its_error(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec, STEPPED_PLAN)
    outcome = cmd_run(module, spec, root=tmp_path)
    assert not outcome.ok

    steps = [r for r in _ledger(spec) if r.get("kind") == "step"]
    assert len(steps) == 1
    assert steps[0]["label"] == "read the emitted item"
    assert steps[0]["exit_code"] == 1
    assert "unfinished" not in steps[0]
    assert "FileNotFoundError" in steps[0]["error"]
    report = (spec / "qa-report.md").read_text(encoding="utf-8")
    assert "**read the emitted item** — failed" in report
    assert "FileNotFoundError" in report


def test_a_scenario_that_printed_nothing_leaves_no_stdout_sidecar(tmp_path: Path) -> None:
    """An empty `qa/steps/<scenario>-stdout.txt` told a reviewer nothing and was registered as evidence anyway; a scenario that said nothing now writes nothing."""
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")
    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message
    assert not (spec / "qa" / "steps" / "item-is-emitted-stdout.txt").exists()
    assert not any(r.get("kind") == "command-output" for r in _ledger(spec))


def test_a_stale_report_does_not_outlive_the_run_that_wrote_it(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    (spec / "qa-report.md").write_text("<!-- run: old status: passed -->\n", encoding="utf-8")
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")
    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message
    assert "<!-- run: qa-story-1 status: passed -->" in (spec / "qa-report.md").read_text(encoding="utf-8")


