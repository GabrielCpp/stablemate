"""Version-2 QA plan parsing and fail-closed semantic validation."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ostler import checks
from ostler import path as path_mod
from ostler.model import load as load_graph
from ostler.qa.compile import book_digest
from ostler.qa.context import book_files, story_file_record
from ostler.qa.harness_host import default_interpreter, describe, load_harness_module
from ostler.untyped import is_mapping
from ostler.vet import placement

_BOOK_DRIFT_NAME_LIMIT = 20

_plan_harness = load_harness_module("ostler_qa")
COMPUTED: str = _plan_harness.COMPUTED
DRIVERS: frozenset[str] = frozenset(_plan_harness.DRIVER_NAMES)
UI_DRIVERS: tuple[str, ...] = tuple(_plan_harness.UI_DRIVER_NAMES)

RETIRED_YAML = (
    "the YAML QA plan is retired — write the plan as `qa_plan.py` in the same spec directory "
    "(one `@scenario`-decorated function per scenario) and delete the .yml"
)

MECHANISMS = {"live", "fixture"}
LOCATOR_KEYS = {"role", "name", "label", "test_id", "text", "css", "id"}


@dataclass
class PlanDocument:
    path: Path
    spec_dir: Path
    root: Path
    data: dict[str, Any]
    context: dict[str, Any]

    @property
    def run_id(self) -> str:
        return str(self.data["run_id"])

    @property
    def story(self) -> str:
        return str(self.data["story"])


def resolve_spec_dir(plan_file: Path, spec_dir: Path | None, root: Path) -> Path:
    plan_file = plan_file if plan_file.is_absolute() else root / plan_file
    if spec_dir is not None:
        return (spec_dir if spec_dir.is_absolute() else root / spec_dir).resolve()
    return plan_file.parent.resolve()


def load_plan(plan_file: Path, spec_dir: Path, root: Path) -> tuple[PlanDocument | None, list[str]]:
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return None, [f"plan file not found: {resolved_plan}"]
    root, spec_dir = root.resolve(), spec_dir.resolve()
    resolved_plan = resolved_plan.resolve()
    if resolved_plan.suffix != ".py":
        return None, [RETIRED_YAML]
    data, problems = _describe_python_plan(resolved_plan, root)
    if data is None:
        return None, problems
    context_path = spec_dir / "qa-okf-context.json"
    context: dict[str, Any] = {}
    if context_path.is_file():
        try:
            loaded = json.loads(context_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                context = loaded
        except json.JSONDecodeError as exc:
            return None, [f"qa-okf-context.json is invalid JSON: {exc}"]
    data["obligationDocuments"] = _obligation_documents(context)
    return PlanDocument(resolved_plan, spec_dir, root, data, context), problems


def _obligation_documents(context: dict[str, Any]) -> dict[str, list[str]]:
    """Which documents each packet obligation occupies, keyed by its id."""
    return {
        str(obligation["id"]): list(obligation.get("occurrenceDocuments") or [])
        for obligation in context.get("obligations", [])
        if is_mapping(obligation) and obligation.get("id")
    }


def _describe_python_plan(plan_file: Path, root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read a `qa_plan.py` by importing it in the harness and taking what it declared."""
    data, problems = describe(plan_file, root)
    if data is None:
        return None, problems
    interpreter = default_interpreter(root)
    targets = data.get("targets")
    if isinstance(targets, dict):
        for target in targets.values():
            if isinstance(target, dict):
                target.setdefault("module", str(plan_file))
                target.setdefault("interpreter", str(interpreter))
    return data, problems


def _book_drift_problems(context: dict[str, Any], root: Path) -> list[str]:
    """`stale-context:` problems for a packet whose recorded `bookFiles` disagree with the tree."""
    recorded = context.get("bookFiles")
    if recorded is None:
        return [
            "stale-context: qa-okf-context.json predates the book-drift guard "
            "(no bookFiles) — run `ostler qa context` to regenerate the packet"
        ]
    if not isinstance(recorded, list):
        return ["stale-context: qa-okf-context.json 'bookFiles' must be a list"]
    recorded_by_path = {
        str(entry["path"]): str(entry["sha256"])
        for entry in recorded
        if is_mapping(entry) and "path" in entry and "sha256" in entry
    }
    features_root = path_mod.resolve_features_root(context.get("featuresRoot"), root)
    current_by_path = {entry["path"]: entry["sha256"] for entry in book_files(root, features_root)}
    changed = sorted(
        path
        for path in recorded_by_path.keys() & current_by_path.keys()
        if recorded_by_path[path] != current_by_path[path]
    )
    removed = sorted(recorded_by_path.keys() - current_by_path.keys())
    added = sorted(current_by_path.keys() - recorded_by_path.keys())
    if not changed and not removed and not added:
        return []

    def _named(label: str, paths: list[str]) -> str:
        shown = paths[:_BOOK_DRIFT_NAME_LIMIT]
        names = ", ".join(shown)
        remainder = len(paths) - len(shown)
        if remainder > 0:
            names += f" (+{remainder} more)"
        return f"{label}: {names}"

    parts = [
        _named(label, paths)
        for label, paths in (("changed", changed), ("removed", removed), ("added", added))
        if paths
    ]
    return [
        "stale-context: the book has changed since this packet was generated — "
        + "; ".join(parts)
        + " — run `ostler qa context` to regenerate the packet"
    ]


def _story_drift_problems(context: dict[str, Any], root: Path) -> list[str]:
    """`stale-context:` problems for a packet whose recorded `storyFile` disagrees with the tree."""
    if "storyFile" not in context:
        return [
            "stale-context: qa-okf-context.json predates the story-drift guard "
            "(no storyFile) — run `ostler qa context` to regenerate the packet"
        ]
    recorded = context["storyFile"]
    if recorded is None:
        return []
    if not is_mapping(recorded) or "path" not in recorded or "sha256" not in recorded:
        return [
            "stale-context: qa-okf-context.json 'storyFile' must be a mapping with "
            "'path' and 'sha256'"
        ]
    recorded_path = str(recorded["path"])
    recorded_sha256 = str(recorded["sha256"])
    story_path = Path(recorded_path)
    resolved = story_path if story_path.is_absolute() else root / recorded_path
    current = story_file_record(root, resolved)
    if current is None:
        return [
            f"stale-context: the story file this packet was generated from is gone "
            f"({recorded_path}) — run `ostler qa context` to regenerate the packet"
        ]
    if current["sha256"] != recorded_sha256:
        return [
            f"stale-context: the story file has changed since this packet was generated "
            f"({recorded_path}) — run `ostler qa context` to regenerate the packet"
        ]
    return []


def validate_v2(document: PlanDocument) -> list[str]:  # noqa: C901
    plan, spec_dir = document.data, document.spec_dir
    problems: list[str] = []
    if not document.context:
        problems.append("qa-okf-context.json is required")
    elif document.context.get("version") != 1:
        problems.append("qa-okf-context.json version must be 1")
    for finding in document.context.get("healthFindings", []):
        if isinstance(finding, dict) and finding.get("severity") == "error":
            problems.append(
                f"OKF health finding blocks execution: {finding.get('kind', 'unknown')} "
                f"{finding.get('path', '')}".rstrip()
            )
    if plan.get("version") != 3:
        problems.append("'version' must be 3")
    for field in ("run_id", "story"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            problems.append(f"'{field}' is required and must be non-empty")
    book = plan.get("book")
    if isinstance(book, str) and book and document.context:
        current = book_digest(document.context)
        if book != current:
            problems.append(
                "stale-plan: this plan was compiled from a different book "
                f"(book={book[:12]}, current book={current[:12]}) — recompile it"
            )
    if document.context:
        problems.extend(_book_drift_problems(document.context, document.root))
        problems.extend(_story_drift_problems(document.context, document.root))

    name = document.path.name
    try:
        document.path.relative_to(spec_dir)
    except ValueError:
        problems.append(f"{name} must remain under the spec directory")
    if document.path.is_relative_to(spec_dir / "qa"):
        problems.append(f"{name} cannot live under disposable qa/")

    inputs = plan.get("inputs", {})
    if not isinstance(inputs, dict):
        problems.append("'inputs' must be a mapping")
        inputs = {}
    for name, raw_path in inputs.items():
        path = _contained_path(spec_dir, raw_path)
        if path is None:
            problems.append(f"input '{name}' escapes the spec directory")
        elif path.is_relative_to(spec_dir / "qa"):
            problems.append(f"input '{name}' is under disposable qa/")
        elif not path.is_file():
            problems.append(f"input '{name}' does not exist: {raw_path}")

    secrets = plan.get("secrets", {})
    if not isinstance(secrets, dict):
        problems.append("'secrets' must be a mapping")
        secrets = {}
    for name, declaration in secrets.items():
        problems.extend(_validate_secret(name, declaration, document.root, spec_dir))

    problems.extend(_validate_tool_env(plan.get("tool_env", []), secrets))

    targets = plan.get("targets")
    if not isinstance(targets, dict) or not targets:
        problems.append("'targets' must be a non-empty mapping")
        targets = {}
    for name, target in targets.items():
        if not isinstance(target, dict):
            problems.append(f"target '{name}' must be a mapping")
            continue
        driver = target.get("driver")
        if driver not in DRIVERS:
            problems.append(f"target '{name}' has unknown driver {driver!r}")
            continue
        if driver in {"playwright", "maestro"}:
            recording = target.get("recording", {"required": True})
            if not isinstance(recording, dict):
                problems.append(f"target '{name}'.recording must be a mapping")
            elif recording.get("required", True) is not True:
                if name not in _recording_exemptions(document.root):
                    problems.append(f"target '{name}' may disable recording only by repository policy")
        if driver == "playwright" and not target.get("base_url"):
            problems.append(f"target '{name}' requires base_url")
        permissions = target.get("permissions")
        if permissions is not None and (
            not isinstance(permissions, list) or not all(isinstance(entry, str) for entry in permissions)
        ):
            problems.append(f"target '{name}'.permissions must be a list of browser permission names")
        if driver == "maestro" and not target.get("app_id"):
            problems.append(f"target '{name}' requires app_id")

    problems.extend(_validate_background(plan.get("background", []), root=document.root))

    scenario_problems, asserted_coverage = _validate_python_scenarios(document, targets)
    problems.extend(scenario_problems)
    problems.extend(_validate_instances(document))

    for obligation in document.context.get("obligations", []):
        if not isinstance(obligation, dict) or not obligation.get("id"):
            continue
        if obligation.get("required", True) is False:
            continue
        if isinstance(obligation.get("deferred"), dict):
            continue
        if obligation["id"] not in asserted_coverage:
            problems.append(f"required OKF obligation '{obligation['id']}' is not covered by an asserted scenario")
    problems.extend(_validate_declared_checks(document, asserted_coverage))
    required_acs = document.context.get("acceptanceCriteria", [])
    for criterion in required_acs if isinstance(required_acs, list) else []:
        criterion_id = criterion.get("id") if isinstance(criterion, dict) else criterion
        if criterion_id and criterion_id not in asserted_coverage:
            problems.append(f"required acceptance criterion '{criterion_id}' is not covered by an asserted scenario")
    problems.extend(_overplanning_problems(document))
    return problems



def _invoked_checks(document: PlanDocument) -> tuple[dict[str, dict[str, checks.CheckCall]], list[str]]:
    """Every named check the plan invokes, keyed by the obligation the invocation binds."""
    invoked: dict[str, dict[str, checks.CheckCall]] = {}
    problems: list[str] = []
    for scenario in document.data.get("scenarios", []):
        if not is_mapping(scenario):
            continue
        scenario_id = str(scenario.get("id") or "?")
        for call in scenario.get("check_calls", []) or []:
            if not is_mapping(call):
                continue
            bound = checks.bind(str(call.get("check", "")), call.get("args") or {})
            if isinstance(bound, checks.Refusal):
                problems.append(
                    f"scenario '{scenario_id}' calls qa.verify with {bound.message}")
                continue
            for obligation_id in call.get("covers") or []:
                invoked.setdefault(str(obligation_id), {})[bound.text()] = bound
    return invoked, problems


def _argument_diff(declared: checks.CheckCall, written: checks.CheckCall) -> tuple[int, int, str]:
    """How many arguments agree, how many differ, and the sentence naming the differences."""
    spec = checks.CHECK_BY_NAME[declared.name]
    agreeing, differing = 0, []
    for param in spec.params:
        want, got = declared.args.get(param.name), written.args.get(param.name)
        if want == got:
            agreeing += want is not None
            continue
        shown_want = checks.literal(want) if want is not None else "nothing"
        shown_got = checks.literal(got) if got is not None else "nothing"
        differing.append(f"`{param.name}` (declared {shown_want}, invoked {shown_got})")
    return agreeing, len(differing), ", ".join(differing)


def _near_miss(
    call: str,
    obligation_ids: list[str],
    invoked: dict[str, dict[str, checks.CheckCall]],
) -> str:
    """The call the plan wrote *instead*, when it wrote one that all but matches."""
    elsewhere = sorted(
        obligation_id for obligation_id, calls in invoked.items() if call in calls
    )
    if elsewhere:
        others = f" and {len(elsewhere) - 1} other(s)" if len(elsewhere) > 1 else ""
        return (
            f" The plan already invokes that exact call, bound to '{elsewhere[0]}'{others} "
            f"— widen that call's covers= instead of writing a second one."
        )
    declared = checks.parse_check(call)
    if isinstance(declared, checks.Refusal):
        return ""
    closest: tuple[int, str, str] | None = None
    for obligation_id in obligation_ids:
        for text, written in (invoked.get(obligation_id) or {}).items():
            if written.name != declared.name:
                continue
            agreeing, count, difference = _argument_diff(declared, written)
            if not difference or not agreeing:
                continue
            if closest is None or count < closest[0]:
                closest = (count, text, difference)
    if closest is None:
        return ""
    return (
        f" The plan invokes `{closest[1]}` against this obligation, differing in "
        f"{closest[2]} — the declared arguments are the claim, so reshape what the scenario "
        f"observes until they hold, rather than restating the call to match the observation."
    )


def _validate_declared_checks(document: PlanDocument, asserted: set[str]) -> list[str]:
    """Hold each claimed obligation to the observation its `verify:` bullets declare."""
    invoked, problems = _invoked_checks(document)
    missing: dict[str, list[str]] = {}
    named: dict[str, str] = {}
    for obligation in document.context.get("obligations", []):
        if not is_mapping(obligation) or not obligation.get("id"):
            continue
        obligation_id = str(obligation["id"])
        if obligation_id not in asserted:
            continue
        for declared in obligation.get("checksDeclared") or []:
            if not is_mapping(declared) or not declared.get("call"):
                continue
            call = str(declared["call"])
            if call in invoked.get(obligation_id, {}):
                continue
            missing.setdefault(call, []).append(obligation_id)
            named.setdefault(call, str(declared.get("name", "")))
    for call, obligation_ids in missing.items():
        spec = checks.CHECK_BY_NAME.get(named[call])
        excludes = f" It excludes {spec.excludes}." if spec else ""
        covers = ", ".join(f"'{obligation_id}'" for obligation_id in obligation_ids)
        near = _near_miss(call, obligation_ids, invoked)
        if len(obligation_ids) == 1:
            problems.append(
                f"obligation {covers} declares `{call}` in its `verify:` bullet, and "
                f"no assertion invokes it — call qa.verify with that name and those arguments, "
                f"bound with covers=[{covers}].{near}{excludes}"
            )
            continue
        problems.append(
            f"{len(obligation_ids)} obligations declare `{call}` in their `verify:` bullets, "
            f"and no assertion invokes it — one qa.verify with that name and those arguments, "
            f"bound with covers=[{covers}], satisfies all of them.{near}{excludes}"
        )
    return problems


def _documented_locators(document: PlanDocument) -> dict[str, dict[str, Any]]:
    """The `role`/`name`/`selector`/`route` the book gives for each obligation in the packet."""
    return {
        obligation["id"]: obligation.get("locators") or {}
        for obligation in document.context.get("obligations", [])
        if is_mapping(obligation) and obligation.get("id")
    }


def _validate_python_scenarios(
    document: PlanDocument, targets: dict[str, Any]
) -> tuple[list[str], set[str]]:
    """Check what a `qa_plan.py` declared, and which coverage its assertions can carry."""
    problems: list[str] = []
    asserted_coverage: set[str] = set()
    scenarios = document.data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [
            "the plan declares no scenario — decorate at least one function with @scenario"
        ], asserted_coverage
    all_coverage = _known_coverage(document.context)
    documented = _documented_locators(document)
    seen: set[str] = set()
    for index, scenario in enumerate(scenarios):
        if not is_mapping(scenario):
            problems.append(f"scenarios[{index}] must be a mapping")
            continue
        scenario_id = str(scenario.get("id") or f"scenarios[{index}]")
        if scenario_id in seen:
            problems.append(f"duplicate scenario id '{scenario_id}'")
        seen.add(scenario_id)
        if scenario.get("target") not in targets:
            problems.append(
                f"scenario '{scenario_id}' references unknown target {scenario.get('target')!r}"
            )
            continue
        mechanism = scenario.get("mechanism")
        if mechanism == "synthetic":
            problems.append(
                f"scenario '{scenario_id}' declares mechanism 'synthetic', which is retired — "
                "evidence is the running product, so drive it (`live`) or drive it from a canned "
                "input (`fixture`)"
            )
        elif mechanism not in MECHANISMS:
            problems.append(
                f"scenario '{scenario_id}' mechanism must be one of {sorted(MECHANISMS)}"
            )
        covers = scenario.get("covers") or []
        if not isinstance(covers, list) or not all(isinstance(item, str) for item in covers):
            problems.append(f"scenario '{scenario_id}'.covers must be a list of IDs")
            covers = []
        for cover in covers:
            if cover not in all_coverage:
                problems.append(
                    f"scenario '{scenario_id}' "
                    f"{_uncoverable(cover, document.context, all_coverage)}"
                )
        checks = scenario.get("checks")
        claimed = scenario.get("check_covers")
        claimed_ids: set[str] = set()
        if isinstance(claimed, list):
            claimed_ids = {item for item in claimed if isinstance(item, str)}
        if not isinstance(checks, int):
            problems.append(f"scenario '{scenario_id}' is missing its static assertion count")
        elif covers and checks == 0:
            problems.append(
                f"scenario '{scenario_id}' claims coverage of {sorted(covers)} but its body "
                "calls no qa.check() — assert something the behaviour produced, on the line "
                "that produced it, with qa.check()/qa.require() or their retrying forms "
                "qa.eventually()/qa.require_eventually(). The count is static: it follows "
                "the helpers this module defines and the scenario calls, but nothing it "
                "imports or reaches through an object, so a check in one of those does not "
                "count; inline it here or move the helper into this module"
            )
        else:
            unclaimed = sorted(set(covers) - claimed_ids)
            if unclaimed:
                problems.append(
                    f"scenario '{scenario_id}' declares coverage of {unclaimed} but no "
                    "qa.check()/qa.require()/qa.eventually() in its body claims it. Bind the "
                    "assertion that proves each obligation — qa.check(label, condition, "
                    "covers=[...]) — with "
                    "the ids written literally — the binding is read statically, so a "
                    "computed list claims nothing. The scenario-level covers is a promise "
                    "about the function; the per-check covers is what the evidence gate "
                    "counts. Without this, deleting the assertion that proves an obligation "
                    "leaves the obligation credited to whatever unrelated check still passes"
                )
            asserted_coverage.update(claimed_ids & set(covers))
        if "restart" in scenario:
            problems.extend(_validate_restart(scenario_id, scenario["restart"], document))
        driver = targets[scenario["target"]].get("driver")
        if driver == "playwright":
            found = scenario.get("locators")
            problems.extend(
                _validate_book_locators(
                    scenario_id, list(covers), found if isinstance(found, list) else [], documented
                )
            )
        if driver in UI_DRIVERS:
            vetted = scenario.get("vets")
            documented_screens = _documented_screens(document)
            if not any(cover.startswith("okf:") for cover in covers):
                documented_screens |= _book_screens(document)
            problems.extend(
                _validate_vets(
                    scenario_id,
                    vetted if isinstance(vetted, list) else [],
                    documented_screens,
                )
            )
    return problems, asserted_coverage


def _validate_instances(document: PlanDocument) -> list[str]:
    """Hold every scenario covering a repeated obligation to concrete, named instances."""
    repeats: dict[str, dict[str, Any]] = {}
    for obligation in document.context.get("obligations", []):
        if is_mapping(obligation) and obligation.get("id") and is_mapping(obligation.get("repeat")):
            repeats[str(obligation["id"])] = dict(obligation["repeat"])
    problems: list[str] = []
    scenarios = document.data.get("scenarios")
    if not repeats or not isinstance(scenarios, list):
        return problems
    for index, scenario in enumerate(scenarios):
        if not is_mapping(scenario):
            continue
        scenario_id = str(scenario.get("id") or f"scenarios[{index}]")
        raw_covers = scenario.get("covers")
        covers = (
            [item for item in raw_covers if isinstance(item, str)]
            if isinstance(raw_covers, list)
            else []
        )
        raw_instances = scenario.get("instances")
        declared = raw_instances if isinstance(raw_instances, list) else []
        by_obligation: dict[str, list[dict[str, Any]]] = {}
        for instance in declared:
            if not is_mapping(instance):
                continue
            obligation_id = str(instance.get("obligation") or COMPUTED)
            repeat = repeats.get(obligation_id)
            if repeat is None:
                problems.append(
                    f"scenario '{scenario_id}' declares qa.instance for '{obligation_id}', "
                    "which is not a repeated obligation in this packet — the id must be "
                    "written literally and name an obligation whose node declares `one-per:`"
                )
                continue
            if obligation_id not in covers:
                problems.append(
                    f"scenario '{scenario_id}' declares qa.instance for '{obligation_id}' "
                    "without covering it — an instance narrows a coverage claim, so add the "
                    "obligation to the scenario's covers or drop the declaration"
                )
                continue
            bindings = instance.get("bindings")
            if not is_mapping(bindings):
                problems.append(
                    f"scenario '{scenario_id}' declares an unreadable qa.instance for "
                    f"'{obligation_id}' — write the bindings as a literal dict of written "
                    "strings; a computed mapping declares nothing validation can check"
                )
                continue
            binds = [bind for bind in repeat.get("binds") or [] if isinstance(bind, str)]
            variants = repeat.get("variants") if is_mapping(repeat.get("variants")) else None
            allowed = set(binds) | ({str(variants["path"])} if variants else set())
            for key in sorted(set(binds) - set(bindings)):
                problems.append(
                    f"scenario '{scenario_id}' instance for '{obligation_id}' does not bind "
                    f"'{key}' — the template interpolates it, so a concrete instance must say "
                    "what it holds"
                )
            for key in sorted(set(map(str, bindings)) - allowed):
                problems.append(
                    f"scenario '{scenario_id}' instance for '{obligation_id}' binds unknown "
                    f"key '{key}' — the family defines {sorted(allowed) or '(nothing bindable)'}"
                )
            for key in sorted(map(str, bindings)):
                if bindings[key] == COMPUTED:
                    problems.append(
                        f"scenario '{scenario_id}' instance for '{obligation_id}' binds "
                        f"'{key}' to a computed value — write the string literally, so the "
                        "declared instance and the driven one are the same one"
                    )
            by_obligation.setdefault(obligation_id, []).append(dict(bindings))
        for obligation_id in covers:
            repeat = repeats.get(obligation_id)
            if repeat is None:
                continue
            binds = repeat.get("binds") or []
            variants = repeat.get("variants") if is_mapping(repeat.get("variants")) else None
            if not binds and not variants:
                continue
            instances = by_obligation.get(obligation_id, [])
            if not instances:
                problems.append(
                    f"scenario '{scenario_id}' covers repeated obligation '{obligation_id}' "
                    "but declares no qa.instance(...) — a family is only proven through a "
                    "named member, so declare which one this scenario drives"
                )
                continue
            if variants:
                path = str(variants["path"])
                sampled = {str(bound[path]) for bound in instances if path in bound}
                for value in variants.get("values") or []:
                    if str(value) not in sampled:
                        problems.append(
                            f"scenario '{scenario_id}' covers '{obligation_id}' but no "
                            f"instance samples variant `{path} = {value}` — the book "
                            "enumerates the axis, so every value needs an instance (or the "
                            "book's `variants:` bullet is wrong)"
                        )
    return problems


def _documented_screens(document: PlanDocument) -> set[str]:
    """Every document the story's packet puts an obligation on."""
    return {
        str(obligation["source"])
        for obligation in document.context.get("obligations", [])
        if is_mapping(obligation) and obligation.get("source")
    }


def _book_screens(document: PlanDocument) -> set[str]:
    """Every screen the book can vet, for acceptance-criteria-only UI scenarios."""
    try:
        return set(placement.screen_components(load_graph(document.root)))
    except Exception:
        return set()


def _validate_vets(scenario_id: str, vetted: list[Any], documented: set[str]) -> list[str]:
    """A UI scenario proves what its screens looked like, against a screen the packet names."""
    if not vetted:
        return [
            f"scenario '{scenario_id}' drives a UI and vets no screen — call "
            "qa.vet('<screen doc path>') on each documented state it reaches, so what "
            "rendered is registered against where the book places it"
        ]
    problems: list[str] = []
    for screen in vetted:
        if screen == COMPUTED:
            problems.append(
                f"scenario '{scenario_id}' vets a computed screen path; write the document "
                "literally so validation can check it before the run"
            )
        elif screen not in documented:
            problems.append(
                f"scenario '{scenario_id}' vets '{screen}', which this story's OKF packet "
                f"does not name — vetted screens come from {sorted(documented)}"
            )
    return problems


def _validate_restart(scenario_id: str, restart: Any, document: PlanDocument) -> list[str]:
    """`@scenario(restart=[...])` names daemons the plan declared, or it names nothing."""
    if not isinstance(restart, list) or not all(
        isinstance(name, str) and name.strip() for name in restart
    ):
        return [f"scenario '{scenario_id}'.restart must be a list of background daemon names"]
    background = document.data.get("background")
    declared = (
        [str(daemon.get("name")) for daemon in background if is_mapping(daemon)]
        if isinstance(background, list)
        else []
    )
    if restart and not declared:
        return [
            f"scenario '{scenario_id}' restarts {restart} but the plan declares no "
            "background daemon — declare the process with background(...) so the runner "
            "owns the PID it is asked to restart"
        ]
    problems: list[str] = []
    seen: set[str] = set()
    for name in restart:
        if name not in declared:
            problems.append(
                f"scenario '{scenario_id}' restarts unknown daemon '{name}' — declared: "
                f"{sorted(declared)}"
            )
        elif name in seen:
            problems.append(f"scenario '{scenario_id}' restarts '{name}' twice")
        seen.add(name)
    return problems


def _validate_background(background: Any, *, root: Path | None = None) -> list[str]:
    """Check the daemons a plan starts before its scenarios run."""
    problems: list[str] = []
    if not isinstance(background, list):
        return ["'background' must be a list"]
    seen: set[str] = set()
    for index, daemon in enumerate(background):
        label = f"background[{index}]"
        if not is_mapping(daemon):
            problems.append(f"{label} must be a mapping")
            continue
        name = daemon.get("name")
        if not isinstance(name, str) or not name.strip():
            problems.append(f"{label}.name is required")
        elif name in seen:
            problems.append(f"duplicate background daemon '{name}'")
        else:
            seen.add(name)
        label = f"background daemon '{name}'" if isinstance(name, str) and name else label
        problems.extend(_validate_daemon_argv(label, daemon))
        reset_paths = daemon.get("reset_paths", [])
        if not isinstance(reset_paths, list) or any(
            not isinstance(path, str) or not path.strip() for path in reset_paths
        ):
            problems.append(f"{label}.reset_paths must be a list of non-empty strings")
        timeout = daemon.get("timeout")
        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
            problems.append(f"{label}.timeout must be positive")
        problems.extend(_validate_daemon_cwd(label, daemon.get("cwd"), root))
        problems.extend(_validate_ready_check(label, daemon.get("ready_check")))
    return problems


def _validate_secret(name: str, declaration: Any, root: Path, spec_dir: Path) -> list[str]:
    """One source per secret: the variable the runner reads, or the file the trial wrote."""
    if not isinstance(declaration, dict) or not set(declaration) <= {"from_env", "from_file"}:
        return [f"secret '{name}' must contain only 'from_env' or 'from_file'"]
    if len(declaration) != 1:
        return [f"secret '{name}' needs exactly one of 'from_env' or 'from_file'"]
    (source, raw), = declaration.items()
    if not isinstance(raw, str) or not raw:
        return [f"secret '{name}'.{source} must be non-empty"]
    if source == "from_file":
        path = _contained_path(root, raw)
        if path is None:
            return [f"secret '{name}'.from_file escapes the repo root: {raw}"]
        if path.is_relative_to((spec_dir / "qa").resolve()):
            return [f"secret '{name}'.from_file is under disposable qa/: {raw}"]
    return []


_TOOL_ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def _validate_tool_env(declared: Any, secrets: Mapping[str, Any]) -> list[str]:
    """The names a scenario may set on `qa.tool(name).run(env=...)`."""
    if not isinstance(declared, list):
        return ["'tool_env' must be a list of environment variable names"]
    problems: list[str] = []
    seen: set[str] = set()
    secret_envs = {
        str(declaration["from_env"])
        for declaration in secrets.values()
        if isinstance(declaration, Mapping) and "from_env" in declaration
    }
    for name in declared:
        if not isinstance(name, str) or not _TOOL_ENV_NAME.match(name):
            problems.append(f"tool_env name {name!r} must match [A-Z_][A-Z0-9_]*")
            continue
        if name in seen:
            problems.append(f"duplicate tool_env name '{name}'")
        seen.add(name)
        if name.startswith("QA_"):
            problems.append(f"tool_env name '{name}' is in the runner's QA_ namespace")
        if name in secret_envs:
            problems.append(f"tool_env name '{name}' is a secret's from_env; reach it through secret()")
    return problems


def _validate_daemon_cwd(label: str, cwd: Any, root: Path | None) -> list[str]:
    """Where the daemon starts, when the plan says somewhere other than the repo root."""
    if cwd is None:
        return []
    if not isinstance(cwd, str) or not cwd.strip():
        return [f"{label}.cwd must be a non-empty string"]
    if root is not None and "{{" not in cwd and _contained_path(root, cwd) is None:
        return [f"{label}.cwd must stay inside the repo root ({cwd})"]
    return []


def _validate_daemon_argv(label: str, daemon: Mapping[str, Any]) -> list[str]:
    """The daemon's program and its arguments, as a list nothing expands."""
    if "cmd" in daemon:
        return [
            f"{label}.cmd is retired — a daemon command line ran through a shell, which "
            "made a unit suite a legal daemon; declare `argv` as a list instead, e.g. "
            'argv=["go", "run", "./cmd/server"]'
        ]
    argv = daemon.get("argv")
    if not isinstance(argv, list) or not argv:
        return [f"{label}.argv is required and must be a non-empty list"]
    if any(not isinstance(part, str) or not part.strip() for part in argv):
        return [f"{label}.argv must be a list of non-empty strings, got {argv!r}"]
    return []


def _validate_ready_check(label: str, check: Any) -> list[str]:
    """The readiness probe: a URL, or a URL with the method and status that mean "up"."""
    if check is None:
        return []
    if isinstance(check, str):
        if not check.startswith(("http://", "https://")):
            return [
                f"{label}.ready_check as a string must be an http(s) URL; "
                "use a {url, method, status} mapping for anything but a GET expecting 200"
            ]
        return []
    if not is_mapping(check):
        return [
            f"{label}.ready_check must be a URL string or a {{url, method, status}} mapping"
        ]
    problems: list[str] = []
    if "cmd" in check:
        problems.append(
            f"{label}.ready_check.cmd is retired — the command probe was a `curl` wearing "
            "an `assert_contains`; declare the URL, and the method and status if they are "
            'not GET and 200, e.g. {"url": …, "method": "POST", "status": 201}'
        )
    unknown = set(check) - {"url", "method", "status", "timeout", "cmd"}
    if unknown:
        problems.append(
            f"{label}.ready_check has unknown keys {sorted(unknown)}; "
            "supported: url, method, status, timeout"
        )
    url = check.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        problems.append(f"{label}.ready_check mapping requires an http(s) 'url'")
    status = check.get("status")
    if status is not None and (not isinstance(status, int) or isinstance(status, bool)):
        problems.append(f"{label}.ready_check status must be an integer")
    check_timeout = check.get("timeout")
    if check_timeout is not None and (
        not isinstance(check_timeout, (int, float)) or check_timeout <= 0
    ):
        problems.append(f"{label}.ready_check timeout must be positive")
    return problems


def check_runtime_requirements(
    document: PlanDocument,
    *,
    targets: set[str] | None = None,
) -> list[str]:
    """What this machine must have before the run starts, for the targets it will use."""
    problems: list[str] = []
    for name, target in document.data.get("targets", {}).items():
        if targets is not None and name not in targets:
            continue
        driver = target.get("driver")
        recording = target.get("recording", {"required": True})
        required = recording.get("required", True)
        mode = recording.get("mode", "viewport" if driver == "playwright" else "device")
        if driver == "playwright":
            try:
                import playwright.sync_api  # noqa: F401
            except ImportError:
                problems.append(f"target '{name}' requires the Playwright Python package")
            if required and shutil.which("ffmpeg") is None:
                problems.append(f"target '{name}' requires ffmpeg to record and check evidence")
            if required and mode == "window" and sys.platform != "linux":
                problems.append(
                    f"target '{name}' asks for `recording.mode: window`, which films an X "
                    f"display and is Linux-only; this is {sys.platform} — use the default "
                    "`viewport` mode"
                )
            if (
                required
                and mode == "window"
                and not recording.get("display")
                and shutil.which("Xvfb") is None
            ):
                problems.append(f"target '{name}' requires Xvfb for window recording")
            if required and shutil.which("ffprobe") is None:
                problems.append(f"target '{name}' requires ffprobe to validate recording metadata")
        elif driver == "maestro":
            if shutil.which("maestro") is None:
                problems.append(f"target '{name}' requires the maestro CLI")
            device = target.get("device", "android")
            recorder = "adb" if device == "android" else "xcrun"
            if required and shutil.which(recorder) is None:
                problems.append(f"target '{name}' requires {recorder} for device recording")
            if required and shutil.which("ffprobe") is None:
                problems.append(f"target '{name}' requires ffprobe to validate recording metadata")
    for name, declaration in document.data.get("secrets", {}).items():
        if "from_file" in declaration:
            path = document.root / str(declaration["from_file"])
            if not path.is_file() or path.stat().st_size == 0:
                problems.append(
                    f"secret '{name}' requires a non-empty file {declaration['from_file']} under the repo root"
                )
            continue
        env_name = declaration.get("from_env", "")
        if env_name not in os.environ:
            problems.append(f"secret '{name}' requires environment variable {env_name}")
    return problems


def _known_coverage(context: dict[str, Any]) -> set[str]:
    known = {
        str(item["id"])
        for item in context.get("obligations", [])
        if isinstance(item, dict) and item.get("id")
    }
    for item in context.get("acceptanceCriteria", []):
        value = item.get("id") if isinstance(item, dict) else item
        if value:
            known.add(str(value))
    return known


def _scenario_allowance(budget: int) -> int:
    """How many scenarios a plan may declare for *budget* coverable ids."""
    return budget + max(1, budget // 2)


def _overplanning_problems(document: PlanDocument) -> list[str]:
    """Reject a plan that verifies more than this change owes."""
    coverable = _known_coverage(document.context)
    if not coverable:
        return []
    scenarios = document.data.get("scenarios")
    if not isinstance(scenarios, list):
        return []
    problems = []
    for index, scenario in enumerate(scenarios):
        if not is_mapping(scenario):
            continue
        covers = scenario.get("covers")
        claimed = [item for item in covers if isinstance(item, str)] if isinstance(covers, list) else []
        if any(item in coverable for item in claimed):
            continue
        scenario_id = str(scenario.get("id") or f"scenarios[{index}]")
        problems.append(
            f"scenario '{scenario_id}' covers no obligation and no acceptance criterion of "
            "this change — delete it, or point its `covers=` at what the change owes. Every "
            "scenario is re-validated, dry-run, run, fixed and audited on every lap, so one "
            "that proves nothing this story is responsible for is paid for on all of them"
        )
    budget = len(coverable)
    allowance = _scenario_allowance(budget)
    if len(scenarios) > allowance:
        problems.append(
            f"the plan declares {len(scenarios)} scenarios for {budget} coverable "
            f"obligation(s) and acceptance criterion(s) — at most {allowance} may be planned. "
            "Merge the scenarios that prove the same requirement into one, and keep a second "
            "only where a distinct branch of that requirement needs its own run"
        )
    return problems


def _uncoverable(cover: str, context: dict[str, Any], known: set[str]) -> str:
    """Say *why* `covers: [cover]` is not coverable, and what to write instead."""
    node = cover.split(":", 2)[1] if cover.startswith("okf:") else ""
    documented = {
        *(str(item) for item in context.get("contracts", [])),
        *(str(item) for item in context.get("journeyNodes", [])),
        *(str(item.get("node", "")) for item in context.get("directNodes", [])
          if isinstance(item, dict)),
    }
    coverable = ", ".join(sorted(known)[:12]) or "(none — this change carries no obligations)"
    if node and node in documented:
        return (
            f"covers '{cover}', which is a documented node but not an obligation of this "
            f"change — nothing in the diff is owned by it, so there is no requirement here "
            f"to verify. Drop the scenario, or point it at what this change does owe: "
            f"{coverable}"
        )
    return (
        f"covers unknown ID '{cover}' — it is neither an obligation of this change nor one "
        f"of its acceptance criteria. Coverable here: {coverable}"
    )


def _contained_path(base: Path, raw: Any) -> Path | None:
    candidate = Path(str(raw))
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved


_BULLET_TOKEN_RE = re.compile(r"^[\s`\"']*([^\s—,;(`\"']+)")

_ABSENT_BULLET = frozenset({"n/a", "na", "none", "-", "—"})


def _bullet_tokens(values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values if isinstance(values, list) else [values]:
        match = _BULLET_TOKEN_RE.match(str(value or ""))
        token = match.group(1).strip().lower() if match else ""
        if token and token not in _ABSENT_BULLET:
            tokens.add(token)
    return tokens


def _route_matches(route: str, url: str) -> bool:
    """Whether a planned `goto` lands on a route the book documents."""
    planned = urlsplit(url).path or "/"
    documented = urlsplit(route).path or "/"
    left = [part for part in planned.strip("/").split("/") if part]
    right = [part for part in documented.strip("/").split("/") if part]
    if len(left) != len(right):
        return False
    return all(
        part.startswith((":", "{")) or other.startswith((":", "{")) or part == other
        for part, other in zip(left, right, strict=True)
    )


def _validate_book_locators(
    scenario_id: str,
    covers: list[str],
    actions: list[Any],
    documented: dict[str, dict[str, Any]],
) -> list[str]:
    """A browser scenario is addressed the way the book says, or it does not validate."""
    roles: set[str] = set()
    named_roles: set[str] = set()
    routes: set[str] = set()
    addressable = bool(covers)
    for cover in covers:
        locators = documented.get(cover) or {}
        node_roles = _bullet_tokens(locators.get("role"))
        addressable = addressable and bool(node_roles or _bullet_tokens(locators.get("selector")))
        roles |= node_roles
        if node_roles and (("name" not in locators) or _bullet_tokens(locators.get("name"))):
            named_roles |= node_roles
        routes |= {route for route in _bullet_tokens(locators.get("route")) if route.startswith("/")}

    used_roles: set[str] = set()
    text_actions: list[str] = []
    goto_urls: list[str] = []
    for index, action in enumerate(actions):
        if not is_mapping(action):
            continue
        locator = action.get("locator")
        if is_mapping(locator):
            if "role" in locator:
                used_roles |= _bullet_tokens(locator.get("role"))
            if "text" in locator:
                text_actions.append(f"action {index + 1}")
        if action.get("do") == "goto" and action.get("url"):
            goto_urls.append(str(action["url"]))

    problems: list[str] = []
    if roles and addressable:
        for where in text_actions:
            problems.append(
                f"scenario '{scenario_id}' {where} uses a text locator while the covered "
                f"OKF node documents role(s) {sorted(roles)} — address it by role and name"
            )
    if named_roles and not used_roles:
        problems.append(
            f"scenario '{scenario_id}' covers OKF node(s) documenting role(s) {sorted(named_roles)} "
            "that no Playwright locator addresses by role"
        )
    for url in goto_urls:
        if routes and not any(_route_matches(route, url) for route in sorted(routes)):
            problems.append(
                f"scenario '{scenario_id}' navigates to {url!r}, which is not a route "
                f"documented by the covered OKF node(s): {sorted(routes)}"
            )
    return problems


def _recording_exemptions(root: Path) -> set[str]:
    for name in ("ostler.yml", "ostler.yaml"):
        path = root / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        qa = data.get("qa", {}) if isinstance(data, dict) else {}
        values = qa.get("recordingExemptTargets", []) if isinstance(qa, dict) else []
        return {str(value) for value in values} if isinstance(values, list) else set()
    return set()
