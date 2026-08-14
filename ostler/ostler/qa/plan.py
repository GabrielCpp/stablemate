"""Version-2 QA plan parsing and fail-closed semantic validation."""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from ostler import checks
from ostler.qa.harness_host import default_interpreter, describe, load_harness_module
from ostler.untyped import is_mapping

#: Read off the harness rather than restated, because `describe` produces these values and
#: this module judges them: a second spelling of either one is a gate that quietly stops
#: firing.
_plan_harness = load_harness_module("ostler_qa")
COMPUTED: str = _plan_harness.COMPUTED
UI_DRIVERS: tuple[str, ...] = tuple(_plan_harness.UI_DRIVERS)

#: What a `qa-plan.yml` gets told now. The YAML plan's content was a shell heredoc, and every
#: silent-failure mode it had — a field lookup reading a missing key as an empty stream, an
#: evidence path meaning two directories depending on which key it sat under, an assertion
#: proving only that a process exited — had to be caught by a regex standing in for a runtime.
#: A `qa_plan.py` gets that runtime: a wrong key raises, and the traceback names the line.
#: The landed `qa-plan.yml` files stay where they are as archived evidence; they do not re-run.
RETIRED_YAML = (
    "the YAML QA plan is retired — write the plan as `qa_plan.py` in the same spec directory "
    "(one `@scenario`-decorated function per scenario) and delete the .yml"
)

#: Evidence provenance. `synthetic` — a test suite standing in for the product — is gone: it
#: named the one thing a QA run must never accept, and a scenario that could declare it could
#: pass by proving its own harness works. `fixture` stays, because it drives the *real* product
#: from a canned input, which is a different claim. Declared in four places that must agree
#: (`qa/plan.py`, `qa/session.py`, `qa/harness/ostler_qa.py`, `cli.py`); a second spelling here
#: is a gate that quietly stops firing.
MECHANISMS = {"live", "fixture"}
DRIVERS = {"command", "python", "playwright", "maestro"}
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
    # A plan carries no `spec_dir` escape hatch. Learning one would mean importing the module
    # before knowing where its evidence goes, and the key only ever existed to let a generated
    # YAML file sit somewhere other than the spec it describes.
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
    return PlanDocument(resolved_plan, spec_dir, root, data, context), problems


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

    scenario_problems, asserted_coverage = _validate_python_scenarios(document, targets)
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
    problems.extend(_validate_declared_checks(document, asserted_coverage))
    required_acs = document.context.get("acceptanceCriteria", [])
    for criterion in required_acs if isinstance(required_acs, list) else []:
        criterion_id = criterion.get("id") if isinstance(criterion, dict) else criterion
        if criterion_id and criterion_id not in asserted_coverage:
            problems.append(f"required acceptance criterion '{criterion_id}' is not covered by an asserted scenario")
    return problems



def _invoked_checks(document: PlanDocument) -> tuple[dict[str, set[str]], list[str]]:
    """Every named check the plan invokes, keyed by the obligation the invocation binds.

    Aggregated across scenarios rather than per scenario: an obligation may be discharged by
    two scenarios — the success path in one, the conflict branch in another — and demanding
    that one function make every declared observation would refuse plans that are correct.
    What is *not* aggregated is the binding: a `qa.verify` with no `covers=` proves something
    about the product, but nothing this join can credit to a claim.
    """
    invoked: dict[str, set[str]] = {}
    problems: list[str] = []
    for scenario in document.data.get("scenarios", []):
        if not is_mapping(scenario):
            continue
        scenario_id = str(scenario.get("id") or "?")
        for call in scenario.get("check_calls", []) or []:
            if not is_mapping(call):
                continue
            bound = checks.bind(str(call.get("check", "")), call.get("args") or {})
            if isinstance(bound, str):
                # An invocation the vocabulary does not admit is worth its own refusal: it
                # would otherwise fail only as an obligation nobody bound, which sends the
                # author looking at the book instead of at the call they mistyped.
                problems.append(f"scenario '{scenario_id}' calls qa.verify with {bound}")
                continue
            for obligation_id in call.get("covers") or []:
                invoked.setdefault(str(obligation_id), set()).add(bound.text())
    return invoked, problems


def _validate_declared_checks(document: PlanDocument, asserted: set[str]) -> list[str]:
    """Hold each claimed obligation to the observation its `verify:` bullets declare.

    This is where oracle strength stops being a judgment. The reviewer's recurring finding —
    *your assertion would still pass under the defect it exists to exclude* — was a person
    reading a scenario and imagining the defect. Here the book names the check and its
    arguments, and the question is whether the plan invokes that call: a set difference, with
    the expected call and the defect it excludes in the message.

    Only for obligations the plan already claims. An obligation nobody covers is reported by
    the coverage loop above, and saying it twice in different words invites a repair that
    closes one wording and leaves the other standing.
    """
    invoked, problems = _invoked_checks(document)
    # Grouped by the call, not by the obligation. `verify:` sits on the node, so every
    # obligation a node mints carries the same declaration (`qa/context.py`'s
    # `checksDeclared`) — a section with four bullets and four normative lines reports the
    # same missing call sixteen times, each message naming one id. One `qa.verify` whose
    # `covers=` lists them all satisfies every one of them (`_invoked_checks` credits the
    # call to each id it names), so a message per id both overstates the work and reads as
    # an instruction to write sixteen near-identical assertions.
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
            if call in invoked.get(obligation_id, set()):
                continue
            missing.setdefault(call, []).append(obligation_id)
            named.setdefault(call, str(declared.get("name", "")))
    for call, obligation_ids in missing.items():
        spec = checks.CHECK_BY_NAME.get(named[call])
        excludes = f" It excludes {spec.excludes}." if spec else ""
        covers = ", ".join(f"'{obligation_id}'" for obligation_id in obligation_ids)
        if len(obligation_ids) == 1:
            problems.append(
                f"obligation {covers} declares `{call}` in its `verify:` bullet, and "
                f"no assertion invokes it — call qa.verify with that name and those arguments, "
                f"bound with covers=[{covers}].{excludes}"
            )
            continue
        problems.append(
            f"{len(obligation_ids)} obligations declare `{call}` in their `verify:` bullets, "
            f"and no assertion invokes it — one qa.verify with that name and those arguments, "
            f"bound with covers=[{covers}], satisfies all of them.{excludes}"
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
                "qa.eventually()/qa.require_eventually(). The count is static and over this "
                "function alone, so a check inside a helper the scenario calls does not "
                "count; inline it here"
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
        # `describe` recovers the locators from the parsed body, so the book check reads the
        # same structure it read off a YAML action list — see `extract_locators`.
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
            problems.extend(
                _validate_vets(
                    scenario_id,
                    vetted if isinstance(vetted, list) else [],
                    _documented_screens(document),
                )
            )
    return problems, asserted_coverage


def _documented_screens(document: PlanDocument) -> set[str]:
    """Every document the story's packet puts an obligation on."""
    return {
        str(obligation["source"])
        for obligation in document.context.get("obligations", [])
        if is_mapping(obligation) and obligation.get("source")
    }


def _validate_vets(scenario_id: str, vetted: list[Any], documented: set[str]) -> list[str]:
    """A UI scenario proves what its screens looked like, against a screen the packet names.

    Not a policy knob and not a warning. Every assertion in the run that motivated this was
    true of a page whose whole content was a column pinned against one margin — presence is
    what a role locator proves, and placement is what it cannot. Refusing the plan is the
    only point at which that costs nothing.
    """
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


def _validate_background(background: Any) -> list[str]:
    """Check the daemons a plan starts before its scenarios run.

    `background` was the one top-level block nobody validated, and it is the block whose
    entries reach a `subprocess` and a readiness poll. An unrunnable shape therefore failed
    at *run* time, where the only route back to the plan agent is a status and a sentence —
    while everything caught here is handed to it as a diagnostic naming the field. That omission
    is not academic: a `ready_check` mapping crashed the runner, and the coder loop spent
    its whole rework budget re-planning a plan that was never wrong.

    Both fields lost their shell here. `argv` is a list because a daemon command line ran
    through `bash -c`, which made `go test ./...` a legal daemon and left the one capability
    the sandbox exists to remove reachable from the host side of it. `ready_check` is HTTP
    because its command form was a `curl` invocation wearing a `assert_contains` — the probe
    was always "does this URL answer with this status", and saying so directly costs nothing
    and reopens nothing.
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
        problems.extend(_validate_daemon_argv(label, daemon))
        timeout = daemon.get("timeout")
        if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
            problems.append(f"{label}.timeout must be positive")
        problems.extend(_validate_ready_check(label, daemon.get("ready_check")))
    return problems


def _validate_daemon_argv(label: str, daemon: Mapping[str, Any]) -> list[str]:
    """The daemon's program and its arguments, as a list nothing expands.

    `cmd` is named explicitly in the refusal because that is the field an author who has
    seen an older plan will write, and "argv is required" would read as a missing field
    rather than as a replaced one.
    """
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
        # Polled with `urlopen`, so anything that is not a URL it can open would spend the
        # whole timeout failing to connect for a reason nobody sees.
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
    sandboxed: bool = False,
) -> list[str]:
    """What this machine must have before the run starts, for the targets it will use.

    ``targets`` is the set the selected scenarios actually name. Without it a `--scenario`
    dry run of one HTTP check was blocked because some *other* target in the same plan
    wanted a mobile toolchain — a requirement that run was never going to reach.

    ``sandboxed`` drops the browser-toolchain probes, which under `--sandbox` are asking the
    wrong machine: playwright and ffmpeg live in the image, and importing playwright into
    ostler's own interpreter says nothing about whether the container has it. ``ffprobe``
    stays required either way, because the measurement of the finished recording is taken
    here regardless of where it was filmed.
    """
    problems: list[str] = []
    for name, target in document.data.get("targets", {}).items():
        if targets is not None and name not in targets:
            continue
        driver = target.get("driver")
        recording = target.get("recording", {"required": True})
        required = recording.get("required", True)
        mode = recording.get("mode", "window" if driver == "playwright" else "device")
        if driver == "playwright":
            if not sandboxed:
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
