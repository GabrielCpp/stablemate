"""Version-2 QA plan parsing and fail-closed semantic validation."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

MECHANISMS = {"live", "synthetic", "fixture"}
DRIVERS = {"command", "playwright", "maestro"}
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
    try:
        data = yaml.safe_load(resolved_plan.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, [f"YAML parse error: {exc}"]
    if not isinstance(data, dict):
        return None, ["plan must be a YAML mapping"]
    context_path = spec_dir / "qa-okf-context.json"
    context: dict[str, Any] = {}
    if context_path.is_file():
        try:
            loaded = json.loads(context_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                context = loaded
        except json.JSONDecodeError as exc:
            return None, [f"qa-okf-context.json is invalid JSON: {exc}"]
    return PlanDocument(resolved_plan.resolve(), spec_dir.resolve(), root.resolve(), data, context), []


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
    if plan.get("version") != 2:
        problems.append("'version' must be 2")
    for field in ("run_id", "story"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            problems.append(f"'{field}' is required and must be non-empty")

    try:
        document.path.relative_to(spec_dir)
    except ValueError:
        problems.append("qa-plan.yml must remain under the spec directory")
    if document.path.is_relative_to(spec_dir / "qa"):
        problems.append("qa-plan.yml cannot live under disposable qa/")

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
        if driver == "maestro" and not target.get("app_id"):
            problems.append(f"target '{name}' requires app_id")

    scenarios = plan.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        problems.append("'scenarios' must be a non-empty list")
        scenarios = []
    scenario_ids: set[str] = set()
    action_ids: set[str] = set()
    asserted_coverage: set[str] = set()
    all_coverage = _known_coverage(document.context)
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
                problems.append(f"scenario '{scenario_id}' covers unknown ID '{cover}'")

        escape_hatches = int("test_file" in scenario) + int("maestro_flow" in scenario)
        actions = scenario.get("actions")
        if escape_hatches:
            if escape_hatches > 1 or actions is not None:
                problems.append(f"scenario '{scenario_id}' must choose actions or one native test")
            native_key = "test_file" if "test_file" in scenario else "maestro_flow"
            native = _contained_path(document.root, scenario[native_key])
            if native is None or not native.is_file():
                problems.append(f"scenario '{scenario_id}' {native_key} does not exist")
            asserted_coverage.update(covers)
            continue
        if not isinstance(actions, list) or not actions:
            problems.append(f"scenario '{scenario_id}' requires non-empty actions")
            continue
        has_assertion = False
        driver = target.get("driver")
        for action_index, action in enumerate(actions):
            prefix = f"scenario '{scenario_id}' action {action_index + 1}"
            if not isinstance(action, dict):
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
            if kind == "expect":
                has_assertion = True
                if operation not in EXPECTATIONS:
                    problems.append(f"{prefix} has unsupported expectation {operation!r}")
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
        if covers and not has_assertion:
            problems.append(f"scenario '{scenario_id}' lists coverage but has no machine assertion")
        if has_assertion:
            asserted_coverage.update(covers)

    for obligation in document.context.get("obligations", []):
        if not isinstance(obligation, dict) or not obligation.get("id"):
            continue
        if obligation["id"] not in asserted_coverage:
            problems.append(f"required OKF obligation '{obligation['id']}' is not covered by an asserted scenario")
    required_acs = document.context.get("acceptanceCriteria", [])
    for criterion in required_acs if isinstance(required_acs, list) else []:
        criterion_id = criterion.get("id") if isinstance(criterion, dict) else criterion
        if criterion_id and criterion_id not in asserted_coverage:
            problems.append(f"required acceptance criterion '{criterion_id}' is not covered by an asserted scenario")
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
        import os

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


def _contained_path(base: Path, raw: Any) -> Path | None:
    candidate = Path(str(raw))
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved


def _validate_locator(locator: Any, label: str, driver: str) -> list[str]:
    if not isinstance(locator, dict) or not locator:
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
