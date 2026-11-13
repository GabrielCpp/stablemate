"""Version-2 QA plan parsing and fail-closed semantic validation."""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler import path as path_mod
from ostler.manifest import read_manifest
from ostler.qa.harness_host import default_interpreter, describe, load_harness_module
from ostler.untyped import is_mapping

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

    @property
    def run_id(self) -> str:
        return str(self.data["run_id"])

    @property
    def story(self) -> str:
        return str(self.data["story"])


def resolve_spec_dir(plan_file: Path, spec_dir: Path | None, root: Path) -> Path:
    plan_file = plan_file if plan_file.is_absolute() else root / plan_file
    if spec_dir is not None:
        return path_mod.resolve_spec_arg(root, spec_dir).resolve()
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
    return PlanDocument(resolved_plan, spec_dir, root, data), problems


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


def validate_v2(document: PlanDocument) -> list[str]:  # noqa: C901
    plan, spec_dir = document.data, document.spec_dir
    problems: list[str] = []
    if plan.get("version") != 3:
        problems.append("'version' must be 3")
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

    problems.extend(_validate_python_scenarios(document, targets))
    return problems



def _validate_python_scenarios(
    document: PlanDocument, targets: dict[str, Any]
) -> list[str]:
    """Check what a `qa_plan.py` declared."""
    problems: list[str] = []
    scenarios = document.data.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [
            "the plan declares no scenario — decorate at least one function with @scenario"
        ]
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
        if "restart" in scenario:
            problems.extend(_validate_restart(scenario_id, scenario["restart"], document))
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


def _contained_path(base: Path, raw: Any) -> Path | None:
    candidate = Path(str(raw))
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError:
        return None
    return resolved


def _recording_exemptions(root: Path) -> set[str]:
    manifest = read_manifest(root)
    return set(manifest.qa.recordingExemptTargets) if manifest is not None else set()
