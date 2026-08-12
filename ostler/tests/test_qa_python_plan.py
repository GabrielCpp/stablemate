"""Loading, validating and running a `qa_plan.py` — the format that replaces the v2 YAML.

The end-to-end case is the one that matters: a plan module goes in and a `qa-evidence.json`
comes out, with the obligation marked covered by an assertion the scenario made in Python.
Everything the shell format needed a hand-written regex to police is either checked by the
interpreter or absent from the format.
"""

from __future__ import annotations

import json
from pathlib import Path

from ostler.qa.plan import load_plan, resolve_spec_dir, validate_v2
from ostler.qa.run import cmd_run, cmd_validate

OBLIGATION = "okf:docs/features/demo/item.md:contract"

PLAN = '''\
import json
from pathlib import Path

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    payload = json.loads(Path(qa.root, "out.json").read_text(encoding="utf-8"))
    qa.check("the item is the one requested", payload["item"]["id"] == "abc",
             actual=payload["item"]["id"], expected="abc")
'''


BROWSER_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

web = target("web", driver="playwright", base_url="http://localhost:5173")


@scenario(target=web, mechanism="live", covers=["{obligation}"])
def item_is_shown(qa: Qa) -> None:
    """The item is on the page."""
    qa.goto("/items")
    {locator}
    qa.check("the item is shown", True)
'''


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "acceptanceCriteria": [],
                "healthFindings": [],
                "obligations": [
                    {
                        "id": OBLIGATION,
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
    return spec


def _plan(spec: Path, source: str = PLAN) -> Path:
    module = spec / "qa_plan.py"
    module.write_text(source.format(obligation=OBLIGATION), encoding="utf-8")
    return module


def test_spec_dir_is_the_module_directory(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    assert resolve_spec_dir(_plan(spec), None, tmp_path) == spec.resolve()


def test_load_stamps_the_module_and_interpreter_on_every_target(tmp_path: Path) -> None:
    # The driver is handed one target dict and nothing else, so resolving either of these
    # a second time at run time is how a validated plan and an executed plan come apart.
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


def test_an_unimportable_plan_fails_validation(tmp_path: Path) -> None:
    # The static check YAML could never offer. A broken import used to surface an hour into
    # a run, as a driver failure against a story that was fine.
    spec = _spec(tmp_path)
    _plan(spec, "import nonexistent_project_module\n")
    outcome = cmd_validate(spec / "qa_plan.py", spec, root=tmp_path)
    assert not outcome.ok
    assert "failed to import" in outcome.message
    assert "nonexistent_project_module" in outcome.message


def test_coverage_without_an_assertion_is_rejected(tmp_path: Path) -> None:
    # The replacement for `_exit_sentinel`, and stronger: `describe` counts the qa.check
    # calls in a parsed tree rather than guessing at a shell string.
    spec = _spec(tmp_path)
    hollow = PLAN[: PLAN.index('    payload = json')] + "    pass\n"
    document, problems = load_plan(_plan(spec, hollow), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any("calls no qa.check()" in item for item in reported)
    # …and the obligation it claimed is not credited to it.
    assert any("is not covered by an asserted scenario" in item for item in reported)


def test_an_unknown_cover_names_what_the_plan_could_cover(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    document, _ = load_plan(
        _plan(spec, PLAN.replace('covers=["{obligation}"]', 'covers=["okf:invented.md:contract"]')),
        spec,
        tmp_path,
    )
    assert document is not None
    assert any("unknown ID" in item for item in validate_v2(document))


def test_running_the_plan_records_the_assertion_as_evidence(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message

    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    item = next(row for row in evidence["obligations"] if row["id"] == OBLIGATION)
    assert item["verdict"] == "Pass"
    # The ledger record is the same shape a command scenario writes, which is why nothing
    # downstream of `qa-run.ndjson` had to change.
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
    row = next(item for item in evidence["obligations"] if item["id"] == OBLIGATION)
    assert row["verdict"] == "Fail"


def _browser_spec(tmp_path: Path, locator: str) -> Path:
    spec = _spec(tmp_path)
    context = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    context["obligations"][0]["locators"] = {"role": "listitem", "route": "/items"}
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    (spec / "qa_plan.py").write_text(
        BROWSER_PLAN.format(obligation=OBLIGATION, locator=locator), encoding="utf-8"
    )
    return spec


def test_a_browser_scenario_is_held_to_the_role_the_book_documents(tmp_path: Path) -> None:
    # The check that survives the format change: `describe` recovers the locators from the
    # parsed body, so validation reads the same structure it read off a YAML action list.
    spec = _browser_spec(tmp_path, 'qa.by_text("Widget")')
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any("uses a text locator" in item for item in reported)
    assert any("no Playwright locator addresses by role" in item for item in reported)


def test_a_browser_scenario_addressed_by_role_validates(tmp_path: Path) -> None:
    spec = _browser_spec(tmp_path, 'qa.by_role("listitem", name="Widget")')
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_a_browser_scenario_may_not_navigate_off_the_documented_route(tmp_path: Path) -> None:
    spec = _browser_spec(tmp_path, 'qa.by_role("listitem")')
    module = spec / "qa_plan.py"
    module.write_text(
        module.read_text(encoding="utf-8").replace('qa.goto("/items")', 'qa.goto("/invented")'),
        encoding="utf-8",
    )
    document, _ = load_plan(module, spec, tmp_path)
    assert document is not None
    assert any("not a route" in item for item in validate_v2(document))


def test_a_raising_scenario_reports_its_traceback(tmp_path: Path) -> None:
    # No `out.json`: the scenario dies on a KeyError-class failure, which is the whole point
    # of the format — a missing field raises instead of matching empty the way `jq` did.
    spec = _spec(tmp_path)
    module = _plan(spec)
    outcome = cmd_run(module, spec, root=tmp_path)
    assert not outcome.ok
    stdout = (spec / "qa" / "steps" / "item-is-emitted-stdout.txt").read_text(encoding="utf-8")
    assert "FileNotFoundError" in stdout
