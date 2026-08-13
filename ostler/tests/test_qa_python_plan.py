"""Loading, validating and running a `qa_plan.py` — the format that replaces the v2 YAML.

The end-to-end case is the one that matters: a plan module goes in and a `qa-evidence.json`
comes out, with the obligation marked covered by an assertion the scenario made in Python.
Everything the shell format needed a hand-written regex to police is either checked by the
interpreter or absent from the format.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ostler.qa.harness_host import load_harness_module
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
             actual=payload["item"]["id"], expected="abc", covers=["{obligation}"])
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
    qa.vet("docs/features/demo/item.md", name="items")
    qa.check("the item is shown", True, covers=["{obligation}"])
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


def test_importing_a_plan_leaves_no_bytecode_beside_the_documentation(tmp_path: Path) -> None:
    """A spec directory is documentation under version control, not a package directory.

    The plan module lives beside `plan.md` and `review.md`, so importing it wrote a
    `__pycache__/` into the docs tree — once per validate, once per describe, once per
    scenario. Nothing cleans it up, and the next `git add docs/specs/<story>` sweeps it in.
    """
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    assert cmd_validate(module, spec, root=tmp_path).ok
    assert cmd_run(module, spec, root=tmp_path).ok
    assert not (spec / "__pycache__").exists(), "bytecode was written into the spec directory"


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


def test_a_synthetic_mechanism_is_refused_and_named(tmp_path: Path) -> None:
    """`synthetic` named the one thing a QA run must never accept: a suite standing in for
    the product. Two gates, because they catch it at different moments and a plan that only
    tripped the second would already have imported. The decorator refuses the declaration
    outright; `validate_v2` keeps its own branch for a document assembled any other way, and
    says what to write instead — an unadorned "must be one of ['fixture', 'live']" leaves the
    author to guess whether their evidence was retired or merely misspelled.
    """
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


def test_the_finding_says_a_helper_s_checks_do_not_count(tmp_path: Path) -> None:
    """Factoring shared assertions into a helper is the ordinary way to write a scenario that
    proves the same thing for two locales, and it reads to this static count as zero checks.
    The refusal is deliberate, but a message naming only the symptom sends the author to read
    `count_checks` to discover the rule — so the rule travels with the finding."""
    spec = _spec(tmp_path)
    hollow = PLAN[: PLAN.index('    payload = json')] + "    _assert_it(qa)\n"
    document, problems = load_plan(_plan(spec, hollow), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "calls no qa.check()" in item]

    assert reported, "a scenario whose only checks live in a helper still counts as zero"
    assert "helper" in reported[0] and "inline it here" in reported[0]


def test_an_unknown_cover_names_what_the_plan_could_cover(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    document, _ = load_plan(
        _plan(spec, PLAN.replace('covers=["{obligation}"]', 'covers=["okf:invented.md:contract"]')),
        spec,
        tmp_path,
    )
    assert document is not None
    assert any("unknown ID" in item for item in validate_v2(document))


DECLARED = {
    "call": 'json_path(path="item.id", equals="abc")',
    "name": "json_path",
    "args": {"path": "item.id", "equals": "abc"},
}

VERIFY_PLAN = '''\
import json
from pathlib import Path

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    payload = json.loads(Path(qa.root, "out.json").read_text(encoding="utf-8"))
    qa.verify("json_path", payload, {args}, covers=["{obligation}"])
'''


def _declaring(spec: Path) -> None:
    """Put the observation the book declares onto the packet's one obligation."""
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["obligations"][0]["checksDeclared"] = [DECLARED]
    context_path.write_text(json.dumps(context), encoding="utf-8")


def test_a_declared_check_the_plan_never_invokes_is_refused(tmp_path: Path) -> None:
    """The reviewer's recurring finding, now a set difference.

    `qa.check` takes an already-collapsed bool, so this plan's assertion could be arbitrarily
    weaker than the claim and still cite it — which is exactly what a person was being paid
    `power=high` to notice, once per story, forever. The book named the observation; either
    the plan makes it or it does not.
    """
    spec = _spec(tmp_path)
    _declaring(spec)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "declares `json_path" in item]

    assert reported, "an obligation whose declared check nobody invokes must not validate"
    # The defect a weaker assertion would let through travels with the refusal: without it
    # the repair reads as ceremony, and the cheapest way to satisfy ceremony is to restate.
    assert "passes on the default the defect also produces" in reported[0]


def test_invoking_the_declared_check_with_its_arguments_binds(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id", equals="abc"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_the_same_check_with_weaker_arguments_is_a_different_call(tmp_path: Path) -> None:
    # `json_path(path=…)` alone asserts the field is *present*, which is what the default the
    # defect produces also satisfies. It is a legal call and the wrong one, and nothing about
    # the difference needs judging: the canonical spellings differ.
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert any("declares `json_path" in item for item in validate_v2(document))


def test_a_verify_call_naming_no_known_check_is_refused_by_name(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace('"json_path"', '"json_pathe"').replace(
        "{args}", 'path="item.id", equals="abc"'
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    reported = [item for item in validate_v2(document) if "qa.verify" in item]
    assert reported and "is not a known check" in reported[0]


def test_the_declared_check_runs_and_lands_in_the_evidence(tmp_path: Path) -> None:
    # The declaration is executable, which is the whole claim: the comparison is the
    # harness's, so the scenario cannot choose a weaker one.
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id", equals="abc"')
    module = _plan(spec, source)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    assert cmd_run(module, spec, root=tmp_path).ok
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert next(row for row in evidence["obligations"] if row["id"] == OBLIGATION)["verdict"] == "Pass"

    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "wrong"}}), encoding="utf-8")
    assert not cmd_run(module, spec, root=tmp_path).ok


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


def test_by_text_matches_a_substring_and_takes_a_pattern() -> None:
    """`qa.by_text` defers to Playwright's own default rather than pinning `exact=True`.

    The pinned form is the defect this guards: a page that renders the text inside a larger
    node — a filename quoted in a rejection sentence, a composite badge string — matched
    nothing, and a locator that *cannot* match reads downstream as a failing product rather
    than as a broken assertion. Taking a `Pattern` belongs to the same fix: without it an
    author who needs a case-insensitive match drops to `qa.page.get_by_text`, which
    `extract_locators` cannot see, and the locator stops being checked against the book.
    """
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


def test_an_obligation_no_check_claims_is_rejected(tmp_path: Path) -> None:
    """The scenario asserts, and asserts about something else entirely.

    This is the hole the per-check binding closes. The old rule was "claims coverage and has
    at least one check", which a scenario satisfies no matter what its checks are about — so
    deleting the two assertions that exercised an obligation left the plan valid, the run
    green, and the evidence row reporting the obligation proven by whatever unrelated check
    still passed. A QA lane scored on failure count finds that move on its own; the gate has
    to be what makes it unavailable.
    """
    spec = _spec(tmp_path)
    unbound = PLAN.replace('expected="abc", covers=["{obligation}"])', 'expected="abc")')
    document, problems = load_plan(_plan(spec, unbound), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any("in its body claims it" in item for item in reported)
    # And it is not quietly credited on the way out either.
    assert any("is not covered by an asserted scenario" in item for item in reported)


def test_a_computed_covers_list_claims_nothing(tmp_path: Path) -> None:
    """`extract_check_covers` reads the parsed tree, so only literal ids are recoverable.

    Degrading to "assume it covers what it says" would reopen the hole through a variable,
    and a binding validation cannot read is one the evidence gate cannot count either — the
    run would then disagree with the plan that passed validation.
    """
    spec = _spec(tmp_path)
    computed = PLAN.replace(
        'expected="abc", covers=["{obligation}"])',
        'expected="abc", covers=list(qa.covers))',
    )
    document, problems = load_plan(_plan(spec, computed), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any("the ids written literally" in item for item in reported)


def test_an_unbound_check_is_not_credited_to_the_scenario_s_obligations(tmp_path: Path) -> None:
    """A ledger record carries the assertion's own binding, never the scenario's.

    The runtime half of the same defect: `run_assert` used to fall back to the scenario's
    `covers` for any record that declared none, so every assertion in the body was stamped
    with every obligation the scenario claimed. One passing check then proved the whole set.
    """
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
    """`eventually` is an assertion, and the gate has to agree — otherwise the doctrine tells
    an author to hold the sampler and the validator answers that their scenario proves
    nothing. Both vacuity rules count it and both bind its `covers=`, because `count_checks`
    and `extract_check_covers` read one shared `CHECK_METHODS` set.
    """
    spec = _spec(tmp_path)
    retrying = PLAN.replace(
        '    qa.check("the item is the one requested", payload["item"]["id"] == "abc",\n'
        '             actual=payload["item"]["id"], expected="abc", covers=["{obligation}"])\n',
        '    qa.eventually("the item is the one requested",\n'
        '                  lambda: payload["item"]["id"] == "abc",\n'
        '                  expected="abc", covers=["{obligation}"])\n',
    )
    document, problems = load_plan(_plan(spec, retrying), spec, tmp_path)

    assert not problems and document is not None
    assert validate_v2(document) == []
