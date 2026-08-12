"""Version-2 QA plan parsing and fail-closed semantic validation."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ostler.qa.harness_host import default_interpreter, describe
from ostler.untyped import is_mapping

MECHANISMS = {"live", "synthetic", "fixture"}
DRIVERS = {"command", "python", "playwright", "maestro"}
ASSERT_KEYS = {
    "assert_contains",
    "assert_count",
    "expect_http",
    "cloudwatch_confirm",
}
EXPECTATIONS = {
    "visible",
    "hidden",
    "enabled",
    "disabled",
    "selected",
    "checked",
    "text",
    "value",
    "count",
    "url",
}
COMMON_ACTIONS = {
    "goto",
    "launch",
    "reload",
    "back",
    "click",
    "tap",
    "fill",
    "select",
    "press",
    "clear",
    "wait_for",
    "wait_for_response",
    "wait_for_idle",
    "command",
}
CAPTURES = {
    "screenshot",
    "trace",
    "body_text",
    "accessibility_snapshot",
    "view_hierarchy",
}
LOCATOR_KEYS = {"role", "name", "label", "test_id", "text", "css", "id"}
_TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")


@dataclass
class PlanDocument:
    path: Path
    spec_dir: Path
    root: Path
    data: dict[str, Any]
    context: dict[str, Any]
    #: ``"python"`` for a `qa_plan.py` read through the harness's describe pass,
    #: ``"yaml"`` for the retiring v2 document. `data` holds the same shape either way —
    #: that is what lets one validator serve both, and what makes the YAML half deletable.
    kind: str = "yaml"

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
    if plan_file.suffix == ".py":
        # A python plan carries no `spec_dir` escape hatch. Learning one would mean importing
        # the module before knowing where its evidence goes, and the key only ever existed to
        # let a generated YAML file sit somewhere other than the spec it describes.
        return plan_file.parent.resolve()
    try:
        raw = yaml.safe_load(plan_file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    configured = raw.get("spec_dir") if isinstance(raw, dict) else None
    if configured:
        candidate = Path(str(configured))
        return (candidate if candidate.is_absolute() else root / candidate).resolve()
    return plan_file.parent.resolve()


def load_plan(plan_file: Path, spec_dir: Path, root: Path) -> tuple[PlanDocument | None, list[str]]:
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return None, [f"plan file not found: {resolved_plan}"]
    root, spec_dir = root.resolve(), spec_dir.resolve()
    resolved_plan = resolved_plan.resolve()
    if resolved_plan.suffix == ".py":
        data, problems = _describe_python_plan(resolved_plan, root)
        kind = "python"
    else:
        data, problems = _parse_yaml_plan(resolved_plan)
        kind = "yaml"
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
    return PlanDocument(resolved_plan, spec_dir, root, data, context, kind), problems


def _parse_yaml_plan(plan_file: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        data = yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, [f"YAML parse error: {exc}"]
    if not isinstance(data, dict):
        return None, ["plan must be a YAML mapping"]
    return data, []


def _describe_python_plan(plan_file: Path, root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Read a `qa_plan.py` by importing it in the harness and taking what it declared.

    Every target is stamped with the module it came from and the interpreter it will be run
    under, because the driver is handed one target dict and nothing else — resolving either
    of those twice is how the validated plan and the executed plan come apart.
    """
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


def validate_v2(document: PlanDocument) -> list[str]:  # noqa: C901
    plan, spec_dir = document.data, document.spec_dir
    problems: list[str] = []
    if not document.context:
        problems.append("qa-okf-context.json is required for a version-2 plan")
    elif document.context.get("version") != 1:
        problems.append("qa-okf-context.json version must be 1")
    for finding in document.context.get("healthFindings", []):
        if isinstance(finding, dict) and finding.get("severity") == "error":
            problems.append(
                f"OKF health finding blocks execution: {finding.get('kind', 'unknown')} "
                f"{finding.get('path', '')}".rstrip()
            )
    expected_version = 3 if document.kind == "python" else 2
    if plan.get("version") != expected_version:
        problems.append(f"'version' must be {expected_version}")
    for field in ("run_id", "story"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            problems.append(f"'{field}' is required and must be non-empty")

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
        if not isinstance(declaration, dict) or set(declaration) != {"from_env"}:
            problems.append(f"secret '{name}' must contain only 'from_env'")
        elif not isinstance(declaration["from_env"], str) or not declaration["from_env"]:
            problems.append(f"secret '{name}'.from_env must be non-empty")

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

    problems.extend(_validate_background(plan.get("background", [])))

    if document.kind == "python":
        scenario_problems, asserted_coverage = _validate_python_scenarios(document, targets)
    else:
        scenario_problems, asserted_coverage = _validate_yaml_scenarios(
            document, targets, inputs, secrets
        )
    problems.extend(scenario_problems)

    for obligation in document.context.get("obligations", []):
        if not isinstance(obligation, dict) or not obligation.get("id"):
            continue
        # An obligation the context builder marked as context-only names something this
        # story neither built nor touched — an unimplemented endpoint the closure walked to,
        # a screen with no `code:` behind it. Demanding an asserted scenario for it is what
        # sent planners after routes that do not exist. Absent the key, require it: a packet
        # written before the flag existed says nothing about which of its members are real.
        if obligation.get("required", True) is False:
            continue
        if obligation["id"] not in asserted_coverage:
            problems.append(f"required OKF obligation '{obligation['id']}' is not covered by an asserted scenario")
    required_acs = document.context.get("acceptanceCriteria", [])
    for criterion in required_acs if isinstance(required_acs, list) else []:
        criterion_id = criterion.get("id") if isinstance(criterion, dict) else criterion
        if criterion_id and criterion_id not in asserted_coverage:
            problems.append(f"required acceptance criterion '{criterion_id}' is not covered by an asserted scenario")
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
    """Check what a `qa_plan.py` declared, and which coverage its assertions can carry.

    There is no action vocabulary left to police. What a scenario *does* is Python, checked
    by the interpreter that runs it — so all that is left here is the part Python cannot see:
    that the ids are distinct, that the targets exist, and that a scenario claiming an
    obligation actually asserts something. That last one is `describe`'s static count of
    `qa.check`/`qa.require` calls in the body — real analysis of a parsed tree, where the
    v2 format could only pattern-match a shell string and guess.
    """
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
        if scenario.get("mechanism") not in MECHANISMS:
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
        if not isinstance(checks, int):
            problems.append(f"scenario '{scenario_id}' is missing its static assertion count")
        elif covers and checks == 0:
            problems.append(
                f"scenario '{scenario_id}' claims coverage of {sorted(covers)} but its body "
                "calls no qa.check() — assert something the behaviour produced, on the line "
                "that produced it"
            )
        else:
            asserted_coverage.update(covers)
        # `describe` recovers the locators from the parsed body, so the book check reads the
        # same structure it read off a YAML action list — see `extract_locators`.
        if targets[scenario["target"]].get("driver") == "playwright":
            found = scenario.get("locators")
            problems.extend(
                _validate_book_locators(
                    scenario_id, list(covers), found if isinstance(found, list) else [], documented
                )
            )
    return problems, asserted_coverage


def _validate_yaml_scenarios(  # noqa: C901
    document: PlanDocument,
    targets: dict[str, Any],
    inputs: dict[str, Any],
    secrets: dict[str, Any],
) -> tuple[list[str], set[str]]:
    """The v2 shell-action vocabulary, policed by hand because YAML cannot police itself.

    Retiring: every rule below compensates for something a language gives for free, and the
    whole function goes when the last YAML plan does.
    """
    plan, spec_dir = document.data, document.spec_dir
    problems: list[str] = []

    scenarios = plan.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        problems.append("'scenarios' must be a non-empty list")
        scenarios = []
    scenario_ids: set[str] = set()
    action_ids: set[str] = set()
    asserted_coverage: set[str] = set()
    all_coverage = _known_coverage(document.context)
    documented = _documented_locators(document)
    for index, scenario in enumerate(scenarios):
        label = f"scenarios[{index}]"
        if not isinstance(scenario, dict):
            problems.append(f"{label} must be a mapping")
            continue
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            problems.append(f"{label}.id is required")
            scenario_id = label
        elif scenario_id in scenario_ids:
            problems.append(f"duplicate scenario id '{scenario_id}'")
        scenario_ids.add(str(scenario_id))
        target_name = scenario.get("target")
        target = targets.get(target_name)
        if target is None:
            problems.append(f"scenario '{scenario_id}' references unknown target {target_name!r}")
            continue
        mechanism = scenario.get("mechanism")
        if mechanism not in MECHANISMS:
            problems.append(f"scenario '{scenario_id}' mechanism must be one of {sorted(MECHANISMS)}")
        covers = scenario.get("covers", [])
        if not isinstance(covers, list) or not all(isinstance(item, str) for item in covers):
            problems.append(f"scenario '{scenario_id}'.covers must be a list of IDs")
            covers = []
        for cover in covers:
            if cover not in all_coverage:
                problems.append(
                    f"scenario '{scenario_id}' "
                    f"{_uncoverable(cover, document.context, all_coverage)}"
                )

        escape_hatches = int("test_file" in scenario) + int("maestro_flow" in scenario)
        actions = scenario.get("actions")
        if escape_hatches:
            if escape_hatches > 1 or actions is not None:
                problems.append(f"scenario '{scenario_id}' must choose actions or one native test")
            native_key = "test_file" if "test_file" in scenario else "maestro_flow"
            native = _contained_path(document.root, scenario[native_key])
            if native is None or not native.is_file():
                problems.append(f"scenario '{scenario_id}' {native_key} does not exist")
            if covers and native_key == "test_file" and not scenario.get("test_name"):
                problems.append(
                    f"scenario '{scenario_id}' points at the whole of {scenario[native_key]} and claims "
                    f"coverage of {sorted(covers)} — set test_name to the case that proves it, so the "
                    "coverage rides on a named test rather than on the file happening to pass"
                )
            else:
                asserted_coverage.update(covers)
            continue
        if not isinstance(actions, list) or not actions:
            problems.append(f"scenario '{scenario_id}' requires non-empty actions")
            continue
        has_assertion = False
        has_substantive_assertion = False
        hollow: list[str] = []
        driver = target.get("driver")
        for action_index, action in enumerate(actions):
            prefix = f"scenario '{scenario_id}' action {action_index + 1}"
            if not is_mapping(action):
                problems.append(f"{prefix} must be a mapping")
                continue
            action_id = action.get("id")
            if action_id:
                if action_id in action_ids:
                    problems.append(f"duplicate action id '{action_id}'")
                action_ids.add(str(action_id))
            keys = [key for key in ("do", "expect", "capture") if key in action]
            if len(keys) != 1:
                problems.append(f"{prefix} must declare exactly one of do, expect, capture")
                continue
            kind, operation = keys[0], action[keys[0]]
            if not isinstance(operation, str):
                problems.append(
                    f"{prefix} {kind} must name a single operation, not {type(operation).__name__} "
                    f"{operation!r} — write '{kind}: <operation>' with its arguments as sibling keys"
                )
                continue
            if kind == "expect":
                has_assertion = has_substantive_assertion = True
                if operation not in EXPECTATIONS:
                    problems.append(f"{prefix} has unsupported expectation {operation!r}")
                if operation == "url":
                    has_value, has_contains = "value" in action, "contains" in action
                    if has_value == has_contains:
                        problems.append(
                            f"{prefix} expect: url must set exactly one of value (exact match) "
                            "or contains (substring match)"
                        )
                elif "contains" in action:
                    problems.append(
                        f"{prefix} contains is only supported by expect: url — use value for {operation!r}"
                    )
            elif kind == "capture" and operation not in CAPTURES:
                problems.append(f"{prefix} has unsupported capture {operation!r}")
            elif kind == "do":
                if operation not in COMMON_ACTIONS:
                    problems.append(f"{prefix} has unsupported action {operation!r}")
                if operation == "command" and driver != "command":
                    problems.append(f"{prefix} command action requires command driver")
                if operation != "command" and driver == "command":
                    problems.append(f"{prefix} action {operation!r} is not supported by command driver")
                if operation == "command" and any(key in action for key in ASSERT_KEYS):
                    has_assertion = True
                    sentinel = _exit_sentinel(action)
                    if sentinel is None:
                        has_substantive_assertion = True
                    else:
                        hollow.append(f"{prefix} asserts only {sentinel}")
                if operation == "command":
                    problems.extend(_evidence_paths_in_command(action.get("cmd"), prefix))
            locator = action.get("locator")
            if locator is not None:
                problems.extend(_validate_locator(locator, prefix, driver))
            if driver == "playwright" and (
                (kind == "do" and operation not in _PLAYWRIGHT_ACTIONS)
                or (kind == "capture" and operation not in _PLAYWRIGHT_CAPTURES)
            ):
                problems.append(f"{prefix} operation {operation!r} is not supported by Playwright")
            if driver == "maestro" and (
                (kind == "do" and operation not in _MAESTRO_ACTIONS)
                or (kind == "expect" and operation not in _MAESTRO_EXPECTATIONS)
                or (kind == "capture" and operation not in _MAESTRO_CAPTURES)
            ):
                problems.append(f"{prefix} operation {operation!r} is not supported by Maestro")
            timeout = action.get("timeout") or action.get("timeout_seconds")
            if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
                problems.append(f"{prefix} timeout must be positive")
            out = action.get("out")
            if out:
                output = _contained_path(spec_dir, out)
                if output is None:
                    problems.append(f"{prefix} output escapes spec directory")
                elif not output.is_relative_to(spec_dir / "qa"):
                    problems.append(f"{prefix} output must be under qa/")
            problems.extend(_validate_tokens(action, prefix, inputs, secrets))
        if driver == "playwright":
            problems.extend(_validate_book_locators(str(scenario_id), covers, actions, documented))
        if covers and not has_assertion:
            problems.append(f"scenario '{scenario_id}' lists coverage but has no machine assertion")
        elif covers and not has_substantive_assertion:
            problems.append(
                f"scenario '{scenario_id}' claims coverage of {sorted(covers)} but every assertion it "
                f"makes proves only that a process exited ({'; '.join(hollow)}) — assert something the "
                "command prints about the behaviour itself, or drive the surface and expect: on it"
            )
        if has_substantive_assertion:
            asserted_coverage.update(covers)
    return problems, asserted_coverage

#: An `assert_contains` value that proves only that the runner process reached its end. The
#: spelling these plans reach for is `VITEST_EXIT:0` — a wrapper echoes the banner, the scenario
#: re-runs an already-committed test file, and its `covers:` is satisfied without anything the
#: story changed being exercised. Anchored to the whole value: `assert_contains: "exit code 0 for
#: tab 3"` names real output and is not a sentinel.
_EXIT_SENTINEL = re.compile(
    r"^[A-Z0-9_]*(?:EXIT(?:[_-]?CODE)?|RETURN[_-]?CODE)\s*[:=]?\s*0?$",
    re.IGNORECASE,
)


def _exit_sentinel(action: Any) -> str | None:
    """Name the exit sentinel a command action asserts when that is all it asserts, else `None`.

    Deliberately narrow. `expect_http` reads the status the endpoint actually returned and
    `assert_count` counts what the command actually printed, so both are claims about behaviour;
    only a value that *is* the runner's exit banner says nothing. A scenario asserting
    `assert_contains: "exit code 0 for tab 3"` names real output and is not caught, because the
    pattern is anchored to the whole value.
    """
    if any(key in action for key in ("assert_count", "expect_http", "cloudwatch_confirm")):
        return None
    needle = action.get("assert_contains")
    if needle is None:
        return None
    text = str(needle).strip()
    return text if _EXIT_SENTINEL.match(text) else None


#: A bare `qa/steps/…` or `qa/asserts/…` inside a command. Anchored to a shell token boundary so
#: `/abs/qa/steps/x` — the absolute spelling that works — is not the tail of a match, while both
#: `qa/steps/x` and `./qa/steps/x` are.
_BARE_EVIDENCE_PATH = re.compile(
    r"""(?:^|[\s;&|<>()"'`=])(?:\./)?qa/(?:steps|asserts)/""", re.MULTILINE
)

#: The *other* wrong spelling: a path with the ledger dir pinned into it by name —
#: `/repo/docs/specs/01-thing/qa/steps/x` or `docs/specs/01-thing/qa/steps/x`. It resolves,
#: which is why it survived review, but it resolves to the same place regardless of
#: `--out-dir`. `$QA_DIR/steps/x` carries no `qa/` segment and so never matches this.
_PINNED_EVIDENCE_PATH = re.compile(r"""[\w${}.-][\w${}./-]*/qa/(?:steps|asserts)/""")


def _evidence_paths_in_command(cmd: Any, prefix: str) -> list[str]:
    """Reject a command that reaches for the evidence directory by a bare relative path.

    `out:` and `capture:` are resolved against the spec directory, so `out: qa/steps/x.txt`
    lands in the evidence dir and ostler creates its parent. A step's `cmd`, though, runs with
    its cwd at the **repo root** — where `qa/steps/` does not exist. The identical string
    therefore means two different places depending on which key it sits under, and the failure
    is silent in the worst way: the redirect fails, the command dies with empty stdout, and
    every assertion chained off it fails against an implementation that is correct. One run
    lost 38 of 66 assertions to this and reported working code as broken.

    Caught here rather than at run time because the diagnostic can name the action and the fix
    (absolute path, or `capture:` + `{{key}}` instead of a hand-rolled temp file), while the
    runtime symptom is an empty file with no explanation attached.
    """
    if not isinstance(cmd, str):
        return []
    if _PINNED_EVIDENCE_PATH.search(cmd):
        return [
            f"{prefix} command hard-codes a path ending in 'qa/steps/' or 'qa/asserts/'; that "
            f"names the scored ledger whichever directory the run was pointed at, so a dry run "
            f"writes into the evidence the scored run is judged on. Use $QA_DIR/steps/… , which "
            f"ostler sets to this run's own ledger directory"
        ]
    if not _BARE_EVIDENCE_PATH.search(cmd):
        return []
    return [
        f"{prefix} command uses a bare 'qa/steps/' or 'qa/asserts/' path; a cmd runs from the "
        f"repo root, so use $QA_DIR/steps/… or chain values with capture:/{{{{key}}}}"
    ]


def _validate_background(background: Any) -> list[str]:
    """Check the daemons a plan starts before its scenarios run.

    `background` was the one top-level block nobody validated, and it is the block whose
    entries reach a `subprocess` and a readiness poll. An unrunnable shape therefore failed
    at *run* time, where the only route back to the plan agent is a status and a sentence —
    while everything caught here is handed to it as a diagnostic naming the field. That omission
    is not academic: a `ready_check` mapping crashed the runner, and the coder loop spent
    its whole rework budget re-planning a plan that was never wrong.
    """
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
        if not isinstance(daemon.get("cmd"), str) or not daemon["cmd"].strip():
            problems.append(f"{label}.cmd is required and must be non-empty")
        timeout = daemon.get("timeout")
        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
            problems.append(f"{label}.timeout must be positive")
        check = daemon.get("ready_check")
        if check is None:
            continue
        if isinstance(check, str):
            # The string form is polled with `urlopen`, so anything that is not a URL it can
            # open would spend the whole timeout failing to connect for a reason nobody sees.
            if not check.startswith(("http://", "https://")):
                problems.append(
                    f"{label}.ready_check as a string must be an http(s) URL; "
                    "use a {cmd, assert_contains} mapping for a command probe"
                )
        elif is_mapping(check):
            unknown = set(check) - {"cmd", "assert_contains", "timeout"}
            if not isinstance(check.get("cmd"), str) or not check["cmd"].strip():
                problems.append(f"{label}.ready_check mapping requires a non-empty 'cmd'")
            if unknown:
                problems.append(
                    f"{label}.ready_check has unknown keys {sorted(unknown)}; "
                    "supported: cmd, assert_contains, timeout"
                )
            check_timeout = check.get("timeout")
            if check_timeout is not None and (
                not isinstance(check_timeout, (int, float)) or check_timeout <= 0
            ):
                problems.append(f"{label}.ready_check timeout must be positive")
        else:
            problems.append(
                f"{label}.ready_check must be a URL string or a {{cmd, assert_contains}} mapping"
            )
    return problems


def check_runtime_requirements(document: PlanDocument) -> list[str]:
    problems: list[str] = []
    for name, target in document.data.get("targets", {}).items():
        driver = target.get("driver")
        recording = target.get("recording", {"required": True})
        required = recording.get("required", True)
        mode = recording.get("mode", "window" if driver == "playwright" else "device")
        if driver == "playwright":
            try:
                import playwright.sync_api  # noqa: F401
            except ImportError:
                problems.append(f"target '{name}' requires the Playwright Python package")
            if required and mode == "window" and shutil.which("ffmpeg") is None:
                problems.append(f"target '{name}' requires ffmpeg for window recording")
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


def _uncoverable(cover: str, context: dict[str, Any], known: set[str]) -> str:
    """Say *why* `covers: [cover]` is not coverable, and what to write instead.

    "unknown ID" alone is true of two different mistakes with opposite repairs, and it
    describes only the rarer one. An id naming a **documented node that this change does
    not touch** is not unknown — the node is right there in the book, which is where the
    plan author read it. Told it is unknown, the author goes back to the book, finds it,
    and either re-asserts the same id or invents a neighbour; the coverable set is the one
    place the message never sent them. That lap is not free: a coder run spent one of its
    three plan reworks re-submitting `…/api.md#tooling:contract` for a real `#tooling`
    section that simply owned none of the changed files.

    So the two are separated, and the obligations this change *does* carry are named. They
    are bounded — a diff wide enough to have hundreds is one where the list is the answer.
    """
    # `okf:<node>:<key>` for a node-level obligation, `okf:<node>:<key>:<index>` for one
    # value of an enumerated bullet. A node id carries no `:`, so splitting from the left
    # names the node in both shapes — `rsplit` on the whole id does not, and left every
    # value-level id falling through to the worse "unknown ID" wording below.
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


#: A bullet's leading token — `alert` out of `alert`, and out of `alert — a static region`.
#: The book writes a clean ARIA role most of the time and trailing prose the rest of it, and
#: a rule that only fires on the clean spelling is a rule the planner routes around.
_BULLET_TOKEN_RE = re.compile(r"^[\s`\"']*([^\s—,;(`\"']+)")

#: `n/a` on a `role:`/`route:` bullet is the book saying the node has none — a static region
#: with no interactive control, a component that never owns a URL. Not an address.
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
    """Whether a planned `goto` lands on a route the book documents.

    Segment-wise, because a documented route carries parameters (`/docs/:slug`, `/docs/{id}`)
    and so does a planned URL (`/docs/{{slug}}`, filled from a prior step). Either side's
    parameter matches anything; a literal must match a literal.
    """
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
    """A browser scenario is addressed the way the book says, or it does not validate.

    The OKF book already carries `role:`, `name:`, `selector:` and `route:` for every screen
    and component; the packet puts them on the obligation. Left as prompt guidance this was
    ignored outright — every locator written before this gate was a text match on a rendered
    string, which passes today, breaks on the next copy edit, and proves nothing about the
    accessible name the book requires. So it is enforced here instead: a `text:` locator is
    rejected when the book gave an address for everything the scenario covers, a stated role
    must actually be addressed by role, and a `goto` may only reach a documented route.

    Both role rules are deliberately scoped to leave no dead end. A scenario mixing a
    role-documented node with one the book gives no address for still needs text for the
    latter, so the text rejection fires only when *every* covered obligation states a role;
    and a screen node documenting `role: main` should not force a `get_by_role("main")` next
    to the assertion that matters, so one role locator satisfies the addressing rule. A gate
    that demands the impossible is a gate the planner burns its turns against.
    """
    roles: set[str] = set()
    routes: set[str] = set()
    addressable = bool(covers)
    for cover in covers:
        locators = documented.get(cover) or {}
        node_roles = _bullet_tokens(locators.get("role"))
        addressable = addressable and bool(node_roles or _bullet_tokens(locators.get("selector")))
        roles |= node_roles
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
    if roles and not used_roles:
        problems.append(
            f"scenario '{scenario_id}' covers OKF node(s) documenting role(s) {sorted(roles)} "
            "that no Playwright locator addresses by role"
        )
    for url in goto_urls:
        if routes and not any(_route_matches(route, url) for route in sorted(routes)):
            problems.append(
                f"scenario '{scenario_id}' navigates to {url!r}, which is not a route "
                f"documented by the covered OKF node(s): {sorted(routes)}"
            )
    return problems


def _validate_locator(locator: Any, label: str, driver: str) -> list[str]:
    if not is_mapping(locator) or not locator:
        return [f"{label} locator must be a non-empty mapping"]
    unknown = set(locator) - LOCATOR_KEYS
    if unknown:
        return [f"{label} locator has unknown keys: {sorted(unknown)}"]
    if driver == "playwright":
        strategies = sum(key in locator for key in ("role", "label", "test_id", "text", "css"))
        if strategies != 1:
            return [f"{label} Playwright locator must select exactly one strategy"]
        if "name" in locator and "role" not in locator:
            return [f"{label} locator.name is valid only with locator.role"]
    elif driver == "maestro" and sum(key in locator for key in ("id", "text")) != 1:
        return [f"{label} Maestro locator must contain exactly one of id or text"]
    return []


def _validate_tokens(
    action: dict[str, Any],
    label: str,
    inputs: dict[str, Any],
    secrets: dict[str, Any],
) -> list[str]:
    problems: list[str] = []
    raw = json.dumps(action)
    for match in _TOKEN_RE.finditer(raw):
        token = match.group(1).strip()
        if token.startswith("input.") and token[6:] not in inputs:
            problems.append(f"{label} references undefined input '{token[6:]}'")
        elif token.startswith("secret.") and token[7:] not in secrets:
            problems.append(f"{label} references undefined secret '{token[7:]}'")
    return problems


_PLAYWRIGHT_ACTIONS = {
    "goto", "reload", "back", "click", "tap", "fill", "select", "press", "clear",
    "wait_for", "wait_for_response", "wait_for_idle",
}
_PLAYWRIGHT_CAPTURES = {"screenshot", "body_text", "accessibility_snapshot"}
_MAESTRO_ACTIONS = {
    "launch", "reload", "back", "click", "tap", "fill", "clear", "wait_for", "wait_for_idle",
}
_MAESTRO_EXPECTATIONS = {"visible", "hidden", "text", "value"}
_MAESTRO_CAPTURES = {"screenshot"}


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
