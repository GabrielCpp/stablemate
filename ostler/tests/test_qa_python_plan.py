"""Loading, validating and running a `qa_plan.py` — the format that replaces the v2 YAML."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ostler.qa.compile import book_digest
from ostler.qa.context import book_files, story_file_record
from ostler.qa.evidence_map import build_evidence_map
from ostler.qa.harness_host import load_harness_module
from ostler.qa.plan import load_plan, resolve_spec_dir, validate_v2
from ostler.qa.run import cmd_run, cmd_validate

OBLIGATION = "okf:docs/features/demo/item.md:contract"

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


AC_BROWSER_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

web = target("web", driver="playwright", base_url="http://localhost:5173")


@scenario(target=web, mechanism="live", covers=["ac:1"])
def reader_is_keyboard_operable(qa: Qa) -> None:
    """The reader route satisfies the story acceptance criterion."""
    qa.goto("/reader")
    qa.vet("docs/features/demo/reader.md", name="reader")
    qa.check("the reader was operable", True, covers=["ac:1"])
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
                "bookFiles": book_files(tmp_path, "docs/features"),
                "storyFile": None,
            }
        ),
        encoding="utf-8",
    )
    return spec


def _ac_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/reader.md").write_text(
        """---
type: screen
title: Reader
---
# Reader

## Components

### reading-region
- selector: `article`
- role: article
- name: Reader content
""",
        encoding="utf-8",
    )
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "acceptanceCriteria": [
                    {"id": "ac:1", "requirement": "The reader is keyboard operable."}
                ],
                "healthFindings": [],
                "obligations": [],
                "bookFiles": book_files(tmp_path, "docs/features"),
                "storyFile": None,
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


def test_a_blank_book_digest_is_not_checked(tmp_path: Path) -> None:
    """A hand-authored plan names no `book=` — nothing here to compare it against, so it is silently exempt rather than refused for omitting a field `ostler qa compile-plan` mints."""
    spec = _spec(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert document.data.get("book", "") == ""
    assert validate_v2(document) == []


def test_a_plan_compiled_from_the_current_book_is_not_stale(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    context = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    source = PLAN.replace(
        'plan(run_id="qa-story-1", story="story-1")',
        f'plan(run_id="qa-story-1", story="story-1", book={book_digest(context)!r})',
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_a_plan_compiled_from_a_different_book_is_stale(tmp_path: Path) -> None:
    """The trap 2w exists for: `compile-plan --out` never overwrites an authored plan, and `qa.vet(...)` re-reads the book at run time while a baked `qa.verify(...)` line does not — so a stale plan can pass its placement checks while asserting against obligations the book no longer states, and nothing said so."""
    spec = _spec(tmp_path)
    source = PLAN.replace(
        'plan(run_id="qa-story-1", story="story-1")',
        'plan(run_id="qa-story-1", story="story-1", book="not-the-real-digest")',
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any(item.startswith("stale-plan:") for item in reported)


def _spec_with_book_file(tmp_path: Path, content: str = "content-1") -> Path:
    """`_spec`, plus a real book file on disk whose digest the packet's `bookFiles` records."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(content, encoding="utf-8")
    return _spec(tmp_path)


def test_a_packet_whose_book_is_unchanged_validates_clean(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_editing_a_book_file_after_the_packet_is_written_is_caught_and_named(
    tmp_path: Path,
) -> None:
    spec = _spec_with_book_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    (tmp_path / "docs/features/demo/item.md").write_text("content-2", encoding="utf-8")
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "changed" in item and "demo/item.md" in item
        for item in reported
    ), reported


def test_adding_a_book_file_after_the_packet_is_written_is_caught(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    (tmp_path / "docs/features/demo/new.md").write_text("new content", encoding="utf-8")
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "added" in item and "demo/new.md" in item
        for item in reported
    ), reported


def test_deleting_a_book_file_after_the_packet_is_written_is_caught(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    (tmp_path / "docs/features/demo/item.md").unlink()
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "removed" in item and "demo/item.md" in item
        for item in reported
    ), reported


def test_a_packet_with_no_book_files_is_refused_as_predating_the_guard(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    del context["bookFiles"]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "predates the book-drift guard" in item
        for item in reported
    ), reported


def _spec_with_story_file(tmp_path: Path, content: str = "# Story 1\n") -> tuple[Path, Path]:
    """`_spec`, plus a real story file on disk whose digest the packet's `storyFile` records."""
    story_file = tmp_path / "docs/specs/story-1/story.md"
    story_file.parent.mkdir(parents=True, exist_ok=True)
    story_file.write_text(content, encoding="utf-8")
    spec = tmp_path / "docs/specs/story-1"
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
                "bookFiles": book_files(tmp_path, "docs/features"),
                "storyFile": story_file_record(tmp_path, story_file),
            }
        ),
        encoding="utf-8",
    )
    return spec, story_file


def test_a_packet_whose_story_file_is_unchanged_validates_clean(tmp_path: Path) -> None:
    spec, _story_file = _spec_with_story_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_editing_the_story_file_after_the_packet_is_written_is_caught_and_named(
    tmp_path: Path,
) -> None:
    spec, story_file = _spec_with_story_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    story_file.write_text("# Story 1 (revised)\n", encoding="utf-8")
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "changed" in item and "story.md" in item
        for item in reported
    ), reported


def test_deleting_the_story_file_after_the_packet_is_written_is_caught(tmp_path: Path) -> None:
    spec, story_file = _spec_with_story_file(tmp_path)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    story_file.unlink()
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "gone" in item and "story.md" in item
        for item in reported
    ), reported


def test_a_packet_whose_story_file_is_none_validates_clean(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["storyFile"] = None
    context_path.write_text(json.dumps(context), encoding="utf-8")
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_a_packet_predating_the_story_drift_guard_is_refused(tmp_path: Path) -> None:
    spec = _spec_with_book_file(tmp_path)
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    del context["storyFile"]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any(
        item.startswith("stale-context:") and "predates the story-drift guard" in item
        for item in reported
    ), reported


def test_a_packet_with_bookfiles_but_no_story_file_key_is_refused_on_story_alone(
    tmp_path: Path,
) -> None:
    """The intermediate-era packet: `bookFiles` was added in an earlier commit than `storyFile`, so a packet generated in between carries a valid `bookFiles` and no `storyFile` key at all."""
    spec = _spec_with_book_file(tmp_path)
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    del context["storyFile"]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert reported == [
        "stale-context: qa-okf-context.json predates the story-drift guard "
        "(no storyFile) — run `ostler qa context` to regenerate the packet"
    ], reported


def test_ac_only_browser_scenario_can_vet_book_screen_outside_packet(
    tmp_path: Path,
) -> None:
    spec = _ac_spec(tmp_path)
    document, problems = load_plan(_plan(spec, AC_BROWSER_PLAN), spec, tmp_path)

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


def test_coverage_without_an_assertion_is_rejected(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    hollow = PLAN[: PLAN.index('    payload = json')] + "    pass\n"
    document, problems = load_plan(_plan(spec, hollow), spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any("calls no qa.check()" in item for item in reported)
    assert any("is not covered by an asserted scenario" in item for item in reported)


def _extra_scenario(name: str, covers: str = "") -> str:
    """One more scenario on the same target, claiming *covers* (nothing when blank)."""
    binding = f", covers=[{covers!r}]" if covers else ""
    return f'''

@scenario(target=api, mechanism="live"{binding})
def {name}(qa: Qa) -> None:
    """Another look at the same behaviour."""
    qa.check("it held", True{binding})
'''


def test_a_scenario_covering_nothing_the_change_owes_is_rejected(tmp_path: Path) -> None:
    """The half of over-planning the coverable fence never saw."""
    spec = _spec(tmp_path)
    source = PLAN + _extra_scenario("free_floating")
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any(
        "scenario 'free-floating' covers no obligation and no acceptance criterion" in item
        for item in reported
    )


def test_a_second_scenario_on_one_obligation_is_within_the_budget(tmp_path: Path) -> None:
    """The branch split the allowance exists for: success in one function, conflict in another."""
    spec = _spec(tmp_path)
    source = PLAN + _extra_scenario("conflict_branch", OBLIGATION)
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    assert validate_v2(document) == []


def test_more_scenarios_than_the_packet_can_justify_are_rejected(tmp_path: Path) -> None:
    """One obligation, three scenarios — every downstream cost is linear in that count."""
    spec = _spec(tmp_path)
    source = PLAN + "".join(
        _extra_scenario(f"again_{index}", OBLIGATION) for index in range(1, 3)
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any(
        "declares 3 scenarios for 1 coverable" in item and "at most 2 may be planned" in item
        for item in reported
    )


def test_an_unmodelled_surface_has_no_budget_to_exceed(tmp_path: Path) -> None:
    """A packet with neither obligations nor criteria bounds nothing."""
    spec = _spec(tmp_path)
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["obligations"] = []
    context_path.write_text(json.dumps(context), encoding="utf-8")
    source = PLAN.replace('covers=["{obligation}"]', "") + _extra_scenario("second")
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

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    payload = json.load((qa.root / "out.json").open(encoding="utf-8"))
    qa.verify("json_path", payload, {args}, covers=["{obligation}"])
'''


def _declaring(spec: Path) -> None:
    """Put the observation the book declares onto the packet's one obligation."""
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["obligations"][0]["checksDeclared"] = [DECLARED]
    context_path.write_text(json.dumps(context), encoding="utf-8")


def test_a_declared_check_the_plan_never_invokes_is_refused(tmp_path: Path) -> None:
    """The reviewer's recurring finding, now a set difference."""
    spec = _spec(tmp_path)
    _declaring(spec)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "declares `json_path" in item]

    assert reported, "an obligation whose declared check nobody invokes must not validate"
    assert "passes on the default the defect also produces" in reported[0]


def test_invoking_the_declared_check_with_its_arguments_binds(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id", equals="abc"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_the_same_check_with_weaker_arguments_is_a_different_call(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert any("declares `json_path" in item for item in validate_v2(document))


def test_a_one_argument_miss_names_the_call_the_plan_wrote_instead(tmp_path: Path) -> None:
    """A set difference cannot say "you wrote this call and got one argument wrong"."""
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="case.item.id", equals="abc"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "declares `json_path" in item]

    assert reported
    assert 'invokes `json_path(path="case.item.id", equals="abc")`' in reported[0]
    assert '`path` (declared "item.id", invoked "case.item.id")' in reported[0]
    assert "`equals`" not in reported[0], "an argument that already agrees is not a finding"


def test_a_call_with_nothing_in_common_is_not_offered_as_the_near_miss(tmp_path: Path) -> None:
    """The same check name with every argument different is a different assertion."""
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="other.field", matches="xyz"')
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "declares `json_path" in item]

    assert reported and "The plan invokes" not in reported[0]


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


def test_the_evidence_map_sees_the_declared_check_the_scenario_actually_ran(
    tmp_path: Path,
) -> None:
    """The bridge between the two processes, which used to drop the check's identity."""
    spec = _spec(tmp_path)
    _declaring(spec)
    source = VERIFY_PLAN.replace("{args}", 'path="item.id", equals="abc"')
    module = _plan(spec, source)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")
    assert cmd_run(module, spec, root=tmp_path).ok

    row = next(
        item
        for item in build_evidence_map(spec)["obligations"]
        if item["id"] == OBLIGATION
    )

    assert row["checksObserved"] == [DECLARED["call"]]
    assert row["checksMissing"] == []
    assert row["status"] == "covered"


def test_running_the_plan_records_the_assertion_as_evidence(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    (tmp_path / "out.json").write_text(json.dumps({"item": {"id": "abc"}}), encoding="utf-8")

    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message

    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    item = next(row for row in evidence["obligations"] if row["id"] == OBLIGATION)
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


def _browser_spec_with_locators(tmp_path: Path, locators: dict[str, str], locator: str) -> Path:
    spec = _spec(tmp_path)
    context = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    context["obligations"][0]["locators"] = locators
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    (spec / "qa_plan.py").write_text(
        BROWSER_PLAN.format(obligation=OBLIGATION, locator=locator), encoding="utf-8"
    )
    return spec


def test_a_role_with_a_truthful_empty_name_validates_by_selector(tmp_path: Path) -> None:
    spec = _browser_spec_with_locators(
        tmp_path,
        {"role": "generic", "name": "none", "selector": "#empty-notice", "route": "/items"},
        'qa.by_css("#empty-notice")',
    )
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_a_role_with_a_real_name_still_rejects_text_addressing(tmp_path: Path) -> None:
    spec = _browser_spec_with_locators(
        tmp_path,
        {"role": "listitem", "name": "Widget", "selector": "#widget", "route": "/items"},
        'qa.by_text("Widget")',
    )
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    reported = validate_v2(document)
    assert any("uses a text locator" in item for item in reported)
    assert any("no Playwright locator addresses by role" in item for item in reported)


def test_a_role_with_a_real_name_still_rejects_a_bare_selector(tmp_path: Path) -> None:
    spec = _browser_spec_with_locators(
        tmp_path,
        {"role": "listitem", "name": "Widget", "selector": "#widget", "route": "/items"},
        'qa.by_css("#widget")',
    )
    document, problems = load_plan(spec / "qa_plan.py", spec, tmp_path)
    assert not problems and document is not None
    assert any("no Playwright locator addresses by role" in item for item in validate_v2(document))


def test_a_browser_scenario_is_held_to_the_role_the_book_documents(tmp_path: Path) -> None:
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


def test_an_obligation_no_check_claims_is_rejected(tmp_path: Path) -> None:
    """The scenario asserts, and asserts about something else entirely."""
    spec = _spec(tmp_path)
    unbound = PLAN.replace('expected="abc", covers=["{obligation}"])', 'expected="abc")')
    document, problems = load_plan(_plan(spec, unbound), spec, tmp_path)
    assert not problems and document is not None

    reported = validate_v2(document)

    assert any("in its body claims it" in item for item in reported)
    assert any("is not covered by an asserted scenario" in item for item in reported)


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
    rebound = f'CLAIM = "{OBLIGATION}"\nCLAIM = "okf:docs/features/demo/item.md:does:1"\n' + PLAN.replace(
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


SIBLING = "okf:docs/features/demo/item.md:returns:1"

TWO_OBLIGATION_PLAN = '''\
import json

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-story-1", story="story-1")

api = target("api")

@scenario(target=api, mechanism="live",
          covers=["okf:docs/features/demo/item.md:contract",
                  "okf:docs/features/demo/item.md:returns:1"])
def item_is_emitted(qa: Qa) -> None:
    """The emitted item carries the id it was asked for."""
    payload = json.load((qa.root / "out.json").open(encoding="utf-8"))
    {assertion}
'''


def _two_declaring(spec: Path) -> None:
    """Two obligations off one node, carrying the same node-level declaration."""
    context_path = spec / "qa-okf-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    first = context["obligations"][0]
    first["checksDeclared"] = [DECLARED]
    context["obligations"].append({**first, "id": SIBLING, "kind": "returns"})
    context_path.write_text(json.dumps(context), encoding="utf-8")


def test_one_missing_call_is_reported_once_for_every_obligation_declaring_it(
    tmp_path: Path,
) -> None:
    """`verify:` sits on the node, so every obligation it mints carries the same call."""
    spec = _spec(tmp_path)
    _two_declaring(spec)
    source = TWO_OBLIGATION_PLAN.replace(
        "{assertion}", 'qa.check("weak", True, covers=["okf:docs/features/demo/item.md:contract", "okf:docs/features/demo/item.md:returns:1"])'
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "json_path" in item]

    assert len(reported) == 1
    assert f"'{OBLIGATION}', '{SIBLING}'" in reported[0]
    assert "satisfies all of them" in reported[0]
    assert "passes on the default the defect also produces" in reported[0]


def test_one_call_covering_both_obligations_binds_both(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    _two_declaring(spec)
    source = TWO_OBLIGATION_PLAN.replace(
        "{assertion}",
        'qa.verify("json_path", payload, path="item.id", equals="abc", covers=["okf:docs/features/demo/item.md:contract", "okf:docs/features/demo/item.md:returns:1"])',
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None
    assert validate_v2(document) == []


def test_the_declared_call_bound_to_the_wrong_obligation_asks_for_a_wider_covers(
    tmp_path: Path,
) -> None:
    """The call exists, spelled exactly right, and names an id that does not need it."""
    spec = _spec(tmp_path)
    _two_declaring(spec)
    source = TWO_OBLIGATION_PLAN.replace(
        "{assertion}",
        'qa.verify("json_path", payload, path="item.id", equals="abc", '
        f'covers=["{SIBLING}"])\n'
        f'    qa.check("weak", True, covers=["{OBLIGATION}"])',
    )
    document, problems = load_plan(_plan(spec, source), spec, tmp_path)
    assert not problems and document is not None

    reported = [item for item in validate_v2(document) if "declares `json_path" in item]

    assert reported
    assert f"already invokes that exact call, bound to '{SIBLING}'" in reported[0]
    assert "widen that call's covers=" in reported[0]



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



REPEAT_OBLIGATION = "okf:docs/features/demo/board.md#stage-row:contract"


def _repeat_spec(tmp_path: Path, **repeat_overrides: Any) -> Path:
    """A packet whose one obligation is a repeated family, as `build_context` lifts it."""
    repeat: dict[str, Any] = {
        "onePer": "stage",
        "binds": ["stage.name"],
        "template": "{stage.name} stage row",
        "iterates": "stage",
        "segments": [
            {"kind": "bind", "path": "stage.name"},
            {"kind": "literal", "text": " stage row"},
        ],
        "uniqueBy": "stage.id",
        "variants": {"path": "stage.kind", "values": ["draft", "active"]},
    }
    repeat.update(repeat_overrides)
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
                        "id": REPEAT_OBLIGATION,
                        "kind": "contract",
                        "node": "stage-row",
                        "source": "docs/features/demo/board.md",
                        "requirement": "one row per stage",
                        "evidenceRequired": "live",
                        "reasons": [],
                        "repeat": repeat,
                    }
                ],
                "bookFiles": book_files(tmp_path, "docs/features"),
                "storyFile": None,
            }
        ),
        encoding="utf-8",
    )
    return spec


def _repeat_plan(spec: Path, body: str) -> Path:
    """A one-scenario plan over the repeated obligation; *body* is the scenario's inside."""
    module = spec / "qa_plan.py"
    module.write_text(
        "from ostler_qa import Qa, plan, scenario, target\n\n"
        'plan(run_id="qa-story-1", story="story-1")\n\n'
        'api = target("api")\n\n'
        f'OB = "{REPEAT_OBLIGATION}"\n\n\n'
        "@scenario(target=api, mechanism='live', covers=[OB])\n"
        "def each_stage_row(qa: Qa) -> None:\n"
        '    """The family is proven through named members."""\n'
        + "".join(f"    {line}\n" for line in body.splitlines()),
        encoding="utf-8",
    )
    return module


def _repeat_problems(tmp_path: Path, spec: Path, body: str) -> list[str]:
    document, problems = load_plan(_repeat_plan(spec, body), spec, tmp_path)
    assert document is not None, problems
    return validate_v2(document)


def test_instances_covering_every_variant_satisfy_the_family(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        'qa.instance(OB, {"stage.name": "Fondations", "stage.kind": "draft"})\n'
        'qa.instance(OB, {"stage.name": "Toiture", "stage.kind": "active"})\n'
        'qa.check("both rows are shown", True, covers=[OB])',
    )
    assert reported == []


def test_covering_a_repeated_obligation_without_instances_is_rejected(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        'qa.check("a row is shown", True, covers=[OB])',
    )
    assert any("declares no qa.instance" in item for item in reported)


def test_an_instance_missing_a_bind_or_inventing_a_key_is_rejected(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        'qa.instance(OB, {"stage.kind": "draft", "bogus": "x"})\n'
        'qa.instance(OB, {"stage.name": "Toiture", "stage.kind": "active"})\n'
        'qa.check("rows are shown", True, covers=[OB])',
    )
    assert any("does not bind 'stage.name'" in item for item in reported)
    assert any("unknown key 'bogus'" in item for item in reported)


def test_an_uncovered_variant_is_surfaced_not_sampled_around(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        'qa.instance(OB, {"stage.name": "Fondations", "stage.kind": "draft"})\n'
        'qa.check("the row is shown", True, covers=[OB])',
    )
    assert any("no instance samples variant `stage.kind = active`" in item for item in reported)


def test_a_computed_binding_or_mapping_declares_nothing(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        "chosen = qa.root.name\n"
        'qa.instance(OB, {"stage.name": chosen, "stage.kind": "draft"})\n'
        "qa.instance(OB, dict(elsewhere for elsewhere in ()))\n"
        'qa.instance(OB, {"stage.name": "Toiture", "stage.kind": "active"})\n'
        'qa.check("rows are shown", True, covers=[OB])',
    )
    assert any("binds 'stage.name' to a computed value" in item for item in reported)
    assert any("unreadable qa.instance" in item for item in reported)


def test_an_instance_for_an_unrepeated_or_uncovered_obligation_is_rejected(tmp_path: Path) -> None:
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path),
        'qa.instance("okf:docs/features/demo/other.md:contract", {"stage.name": "X"})\n'
        'qa.instance(OB, {"stage.name": "Toiture", "stage.kind": "draft"})\n'
        'qa.instance(OB, {"stage.name": "Autre", "stage.kind": "active"})\n'
        'qa.check("rows are shown", True, covers=[OB])',
    )
    assert any("not a repeated obligation" in item for item in reported)


def test_a_family_with_nothing_bindable_and_no_variants_asks_nothing(tmp_path: Path) -> None:
    """The static-template defect belongs to `ostler doctor`, at the source, not to the plan."""
    reported = _repeat_problems(
        tmp_path,
        _repeat_spec(tmp_path, binds=[], variants=None, template=None, segments=None),
        'qa.check("the rows are shown", True, covers=[OB])',
    )
    assert reported == []


def test_qa_instance_writes_the_declaration_into_the_ledger(tmp_path: Path) -> None:
    spec = _repeat_spec(tmp_path)
    module = _repeat_plan(
        spec,
        'qa.instance(OB, {"stage.name": "Fondations", "stage.kind": "draft"})\n'
        'qa.instance(OB, {"stage.name": "Toiture", "stage.kind": "active"})\n'
        'qa.check("both rows are shown", True, covers=[OB])',
    )
    outcome = cmd_run(module, spec, root=tmp_path)
    assert outcome.ok, outcome.message
    records = [r for r in _ledger(spec) if r.get("kind") == "instance"]
    assert {r["obligation"] for r in records} == {REPEAT_OBLIGATION}
    assert {r["bindings"]["stage.name"] for r in records} == {"Fondations", "Toiture"}
