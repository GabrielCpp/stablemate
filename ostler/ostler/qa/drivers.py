"""Execution adapter for a QA target: run its scenarios as Python, and keep the ledger."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from ostler import path as path_mod
from ostler.model import load as load_graph
from ostler.routes import arrived_at, literal_route, screen_routes
from ostler.qa import book_fixtures as qa_book_fixtures
from ostler.qa import fixtures as qa_fixtures
from ostler.qa import tools as qa_tools
from ostler.qa.harness_host import (
    DEFAULT_SCENARIO_TIMEOUT,
    default_interpreter,
    harness_argv,
    harness_env,
)
from ostler.qa.session import QaSession, _redact_bytes
from ostler.vet import placement
from ostler.vet.regions import RegionList


def _declared(record: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    """The check a scenario's `qa.verify()` named, or `None` for a bare `qa.check`."""
    name = record.get("check")
    if not isinstance(name, str) or not name:
        return None
    args = record.get("check_args")
    return name, args if isinstance(args, Mapping) else {}


def _document(item_id: str) -> str:
    """The book file an id names, or `""` for an id that names no document."""
    head = item_id.split("#", 1)[0].removeprefix("okf:")
    return head if "#" in item_id and head.endswith(".md") else ""


def _covers_in(
    covers: list[str], node_id: str, obligation_documents: Mapping[str, list[str]]
) -> list[str]:
    """The entries of `covers` a placement verdict about `node_id` can speak to."""
    document = _document(node_id)
    kept = []
    for item in covers:
        if _document(item) == "":
            kept.append(item)
            continue
        documents = obligation_documents.get(item)
        if documents is None:
            raise DriverBlocked(
                f"'{item}' in scenario covers has no occurrenceDocuments entry in the "
                "compiled plan — qa-okf-context.json is stale or missing; re-run `ostler qa "
                "context` and re-plan"
            )
        if document in documents:
            kept.append(item)
    return kept


DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


@dataclass
class ScenarioResult:
    status: str
    assertions: int = 0
    failures: int = 0
    aborted: bool = False
    artifacts: list[str] = field(default_factory=list)
    message: str = ""


class DriverBlocked(RuntimeError):
    pass


class QaDriver:
    def __init__(
        self,
        session: QaSession,
        target_id: str,
        target: dict[str, Any],
        *,
        root: Path,
        variables: dict[str, str],
        obligation_documents: Mapping[str, list[str]] | None = None,
    ) -> None:
        self.session = session
        self.target_id = target_id
        self.target = target
        self.root = root
        self.variables = variables
        self.obligation_documents: Mapping[str, list[str]] = obligation_documents or {}

    def start(self) -> None:
        return None

    def run(self, scenario: dict[str, Any]) -> ScenarioResult:
        raise NotImplementedError

    def stop(self) -> None:
        return None


class PythonDriver(QaDriver):
    """Run one scenario as a Python function in a subprocess, and record what it claims."""

    def __init__(self, *args: Any, launcher: "Launcher | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.launcher: Launcher = launcher or LocalLauncher()
        self._window_recorder: DisplayRecorder | None = None
        self._device_recorder: DeviceRecorder | None = None
        self.launch_env: dict[str, str] = {}
        self._screens: dict[str, list[placement.VettedComponent]] | None = None
        self._routes: dict[str, str] = {}
        self._book_problem: str | None = None
        self._book_fixtures_cache: dict[str, dict[str, Any]] | None = None

    def start(self) -> None:
        self.launcher.preflight(self)
        problems = [
            *qa_tools.preflight_errors(self.root),
            *qa_fixtures.preflight_errors(self.root),
        ]
        try:
            self._resolved_book_fixtures()
        except DriverBlocked as exc:
            problems.append(str(exc))
        if problems:
            raise DriverBlocked("; ".join(problems))
        driver = str(self.target.get("driver", "python"))
        recording = self.target.get("recording", {"required": True})
        if driver == "playwright":
            self._start_window_recorder(recording)
        elif driver == "maestro":
            self._start_device(recording)

    def _start_window_recorder(self, recording: dict[str, Any]) -> None:
        """Only for `mode: window` — the opt-in one."""
        if not recording.get("required", True) or recording.get("mode", "viewport") != "window":
            return
        if sys.platform != "linux":
            raise DriverBlocked(
                f"`recording.mode: window` films an X display and is Linux-only; this is "
                f"{sys.platform}. Use the default `viewport` mode, which records the page "
                "through Playwright on every platform."
            )
        viewport = self.target.get("viewport", DEFAULT_VIEWPORT)
        self._window_recorder = self.launcher.window_recorder(
            self,
            width=int(viewport.get("width", DEFAULT_VIEWPORT["width"])),
            height=int(viewport.get("height", DEFAULT_VIEWPORT["height"])),
            fps=int(recording.get("fps", 30)),
            display=str(recording.get("display", "")),
        )
        self.launch_env = self._window_recorder.start()

    def _start_device(self, recording: dict[str, Any]) -> None:
        """Refuse a mobile target whose device is not there — blocked, not failed."""
        if shutil.which("maestro") is None:
            raise DriverBlocked("maestro CLI is not installed")
        app_id = str(self.target.get("app_id", ""))
        device = self.target.get("device", "android")
        if device == "android" and shutil.which("adb"):
            probe = subprocess.run(  # noqa: S603 — fixed argv
                ["adb", "shell", "pm", "path", app_id],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if probe.returncode or not probe.stdout.strip():
                raise DriverBlocked(f"app {app_id} is not installed on Android")
        elif device != "android" and shutil.which("xcrun"):
            probe = subprocess.run(  # noqa: S603 — fixed argv
                ["xcrun", "simctl", "get_app_container", "booted", app_id],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if probe.returncode:
                raise DriverBlocked(f"app {app_id} is unavailable on iOS simulator")
        if recording.get("required", True):
            self._device_recorder = DeviceRecorder(self.session, self.target_id, self.target)
            self._device_recorder.start()

    def stop(self) -> None:
        try:
            if self._device_recorder is not None:
                self._device_recorder.stop()
        finally:
            if self._window_recorder is not None:
                self._window_recorder.stop()

    def _resolved_book_fixtures(self) -> dict[str, dict[str, Any]]:
        if self._book_fixtures_cache is None:
            features_root, problem = self._packet_features_root()
            if problem is not None:
                raise DriverBlocked(problem)
            self._book_fixtures_cache = qa_book_fixtures.resolved(
                load_graph(self.root, root_overrides={"features": features_root})
            )
        return self._book_fixtures_cache

    def interpreter(self) -> Path:
        declared = self.target.get("interpreter")
        if not declared:
            return default_interpreter(self.root)
        path = Path(str(declared))
        return path if path.is_absolute() else (self.root / path)

    def module_path(self) -> Path:
        module = Path(str(self.target["module"]))
        return module if module.is_absolute() else (self.root / module)

    def run(self, scenario: dict[str, Any]) -> ScenarioResult:
        scenario_id = str(scenario["id"])
        covers = list(scenario.get("covers", []))
        timeout = float(scenario.get("timeout") or DEFAULT_SCENARIO_TIMEOUT)
        records, output, exit_code, timed_out = self._execute(scenario_id, timeout)
        self._write_output(scenario_id, output)
        return self._grade(
            scenario_id, covers, records, output, exit_code, timed_out=timed_out
        )


    def _execute(
        self, scenario_id: str, timeout: float
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        context = {
            "root": str(self.root),
            "spec_dir": str(self.session.spec_dir),
            "qa_dir": str(self.session.qa_dir),
            "offset_ms": self.session.offset_ms(),
            "tools": qa_tools.resolved_commands(self.root),
            "fixtures": qa_fixtures.resolved(self.root),
            "book_fixtures": self._resolved_book_fixtures(),
        }
        return self.launcher.execute(self, scenario_id, timeout, context)

    def _write_output(self, scenario_id: str, output: str) -> None:
        """Keep the scenario's own stdout — this is where a traceback lands."""
        if not output.strip():
            return
        path = self.session.qa_dir / "steps" / f"{scenario_id}-stdout.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        self.session.register_artifact(
            path, kind="command-output", scenario=scenario_id, target=self.target_id
        )


    def _grade(
        self,
        scenario_id: str,
        covers: list[str],
        records: list[dict[str, Any]],
        output: str,
        exit_code: int,
        *,
        timed_out: bool,
    ) -> ScenarioResult:
        assertions = failures = 0
        action = 0
        terminal: dict[str, Any] | None = None
        problems: list[str] = []
        open_steps: list[tuple[str, str]] = []
        step_started: dict[str, int] = {}
        painted = self._scenario_painted(records)
        for record in records:
            kind = record.get("type")
            step = open_steps[-1] if open_steps else None
            if kind == "assert":
                action += 1
                assertions += 1
                passed, _ = self.session.run_assert(
                    str(record.get("id") or f"{scenario_id}-{action}"),
                    str(record.get("label", "")),
                    "scenario_check",
                    {
                        "passed": bool(record.get("passed")),
                        "actual": record.get("actual"),
                        "expected": record.get("expected"),
                    },
                    root=self.root,
                    scenario=scenario_id,
                    driver="python",
                    action=action,
                    covers=list(record.get("covers") or []),
                    declared=_declared(record),
                    step=step,
                )
                if not passed:
                    failures += 1
            elif kind == "step_start":
                step_id = str(record.get("id", ""))
                open_steps.append((step_id, str(record.get("label", ""))))
                if record.get("offset_ms") is not None:
                    step_started[step_id] = int(record["offset_ms"])
            elif kind == "step_end":
                step_id = str(record.get("id", ""))
                open_steps[:] = [entry for entry in open_steps if entry[0] != step_id]
                self._step_record(
                    scenario_id,
                    step_id,
                    str(record.get("label", "")),
                    failed=bool(record.get("failed")),
                    error=record.get("error"),
                    started_offset_ms=step_started.get(step_id),
                    ended_offset_ms=(
                        int(record["offset_ms"]) if record.get("offset_ms") is not None else None
                    ),
                )
            elif kind == "capture":
                self.session.set_capture(str(record["key"]), str(record["value"]))
            elif kind == "instance":
                self.session.append(
                    {
                        "kind": "instance",
                        "scenario": scenario_id,
                        "obligation": str(record.get("obligation", "")),
                        "bindings": record.get("bindings") or {},
                    }
                )
            elif kind == "artifact":
                problems.extend(self._register(scenario_id, record, step=step, painted=painted))
            elif kind == "vet":
                try:
                    verdicts, trouble = self._vet(scenario_id, record, step=step)
                except ValueError as exc:
                    verdicts, trouble = [], [f"scenario '{scenario_id}' vet failed: {exc}"]
                problems.extend(trouble)
                for verdict in verdicts:
                    action += 1
                    assertions += 1
                    passed, _ = self.session.run_assert(
                        f"{scenario_id}-{action}",
                        verdict.sentence(),
                        "scenario_check",
                        {
                            "passed": verdict.ok,
                            "actual": verdict.observed(),
                            "expected": verdict.expected,
                        },
                        root=self.root,
                        scenario=scenario_id,
                        driver="python",
                        action=action,
                        covers=_covers_in(covers, verdict.node_id, self.obligation_documents),
                        step=step,
                    )
                    if not passed:
                        failures += 1
            elif kind == "scenario":
                terminal = record

        for step_id, label in reversed(open_steps):
            self._step_record(
                scenario_id,
                step_id,
                label,
                failed=True,
                unfinished=True,
                started_offset_ms=step_started.get(step_id),
            )

        message = ""
        if timed_out:
            message = f"scenario '{scenario_id}' exceeded its timeout and was killed"
        elif terminal is None:
            message = (
                f"scenario '{scenario_id}' produced no result (exit {exit_code})"
                f"{self.launcher.no_result_hint()}: " + output.strip()[-500:]
            )
        elif terminal.get("error"):
            message = str(terminal["error"]).strip()[-2000:] + self.launcher.no_result_hint()
        if problems:
            message = "; ".join([part for part in [message, *problems] if part])

        terminal_status = (terminal or {}).get("status")
        aborted = bool(
            timed_out
            or terminal is None
            or problems
            or terminal_status == "errored"
            or (terminal_status != "passed" and not failures)
        )
        if aborted and covers:
            action += 1
            assertions += 1
            self.session.run_assert(
                f"{scenario_id}-completed",
                "the scenario runs to completion, so what it claims is what it observed",
                "scenario_check",
                {
                    "passed": False,
                    "actual": message or f"scenario '{scenario_id}' did not finish",
                    "expected": "every step runs and the scenario grades itself as passed",
                },
                root=self.root,
                scenario=scenario_id,
                driver="python",
                action=action,
                covers=covers,
                sentinel=True,
            )
            failures += 1
        status = "passed"
        if aborted or failures:
            status = "failed"
            failures = max(failures, 1)
        return ScenarioResult(
            status=status,
            assertions=assertions,
            failures=failures,
            message=message,
            aborted=aborted,
        )

    def _step_record(
        self,
        scenario_id: str,
        step_id: str,
        label: str,
        *,
        failed: bool,
        unfinished: bool = False,
        error: object = None,
        started_offset_ms: int | None = None,
        ended_offset_ms: int | None = None,
    ) -> None:
        record: dict[str, Any] = {
            "kind": "step",
            "id": step_id,
            "label": label,
            "cmd": "",
            "exit_code": 1 if failed else 0,
            "driver": "python",
            "scenario": scenario_id,
        }
        if unfinished:
            record["unfinished"] = True
        if error:
            record["error"] = str(error)
        if started_offset_ms is not None:
            record["started_offset_ms"] = started_offset_ms
        if ended_offset_ms is not None:
            record["ended_offset_ms"] = ended_offset_ms
        self.session.append(record)

    def _scenario_painted(self, records: list[dict[str, Any]]) -> bool:
        """Whether any of this scenario's `vet` records scanned a region with real extent."""
        for vet_record in records:
            if vet_record.get("type") != "vet":
                continue
            regions_path = Path(str(vet_record.get("regions", "")))
            if not regions_path.is_file():
                continue
            try:
                regions = RegionList.validate_json(regions_path.read_bytes())
            except ValueError:
                continue
            if any(region.bbox.area > 0 for region in regions):
                return True
        return False

    def _register(
        self,
        scenario_id: str,
        record: dict[str, Any],
        *,
        step: tuple[str, str] | None = None,
        painted: bool = False,
    ) -> list[str]:
        """File one artifact the scenario produced, holding a recording to the target's shape."""
        path = Path(str(record["path"]))
        kind = str(record.get("kind", "evidence"))
        metadata = record.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        if step:
            metadata["step"], metadata["step_label"] = step
        problems: list[str] = []
        if path.is_dir():
            files = sorted(child for child in path.rglob("*") if child.is_file())
            if not files:
                return [f"scenario '{scenario_id}' artifact directory is empty: {path}"]
            for child in files:
                problems.extend(
                    self._file(
                        scenario_id,
                        child,
                        kind=kind,
                        metadata={**metadata, "directory": str(path)},
                    )
                )
            return problems
        if kind == "video" and path.is_file():
            measured = _probe_media(path)
            metadata.update(measured)
            viewport = self.target.get("viewport", DEFAULT_VIEWPORT)
            width = int(viewport.get("width", DEFAULT_VIEWPORT["width"]))
            height = int(viewport.get("height", DEFAULT_VIEWPORT["height"]))
            if measured.get("width") and (
                measured.get("width") != width or measured.get("height") != height
            ):
                problems.append(
                    f"scenario '{scenario_id}' recording is "
                    f"{measured.get('width')}x{measured.get('height')}, "
                    f"not the target's {width}x{height}"
                )
            if _is_static(path, measured.get("durationSeconds", 0)) and not painted:
                problems.append(
                    f"scenario '{scenario_id}' recording never changes — the page under test "
                    "painted nothing for the whole recording"
                )
        problems.extend(self._file(scenario_id, path, kind=kind, metadata=metadata))
        return problems

    def _file(
        self, scenario_id: str, path: Path, *, kind: str, metadata: dict[str, Any]
    ) -> list[str]:
        """One manifest row, or the reason the file could not be one."""
        try:
            self.session.register_artifact(
                path,
                kind=kind,
                scenario=scenario_id,
                target=self.target_id,
                **({"metadata": metadata} if metadata else {}),
            )
        except ValueError as exc:
            return [f"scenario '{scenario_id}' produced an unusable artifact: {exc}"]
        return []


    def _packet_features_root(self) -> tuple[str, str | None]:
        """The frame a `qa.vet` argument is spelled in — the packet's `featuresRoot` — or the reason there is none."""
        packet = self.session.spec_dir / "qa-okf-context.json"
        if not packet.is_file():
            return "", (
                f"no QA context packet at {packet} — a compiled plan's `qa.vet` arguments "
                "are spelled against the book the packet's `featuresRoot` names, and with "
                "no packet there is no root to resolve them against; run `ostler qa "
                "context` for this spec before `qa run`, or pass `--spec` at a directory "
                "it wrote"
            )
        try:
            data = json.loads(packet.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return "", f"QA context packet at {packet} is unreadable: {exc}"
        features_root = path_mod.resolve_features_root(data.get("featuresRoot"), self.root)
        return features_root, None

    def _book(self) -> dict[str, list[placement.VettedComponent]]:
        """The documented screens, read once per target and kept, keyed the way a compiled plan spells its `qa.vet` arguments — see `_packet_features_root`."""
        if self._screens is None:
            self._screens = {}
            features_root, self._book_problem = self._packet_features_root()
            if self._book_problem is None:
                graph = load_graph(self.root, root_overrides={"features": features_root})
                self._screens = placement.screen_components(graph)
                self._routes = screen_routes(graph)
        return self._screens

    def _arrival(self, scenario_id: str, screen: str, record: dict[str, Any]) -> str | None:
        """Why this photograph is not of *screen*, or None when it is."""
        self._book()
        route = self._routes.get(screen, "")
        url = str(record.get("url", ""))
        if not url or not literal_route(route):
            return None
        if arrived_at(url, route):
            return None
        return (
            f"scenario '{scenario_id}' vets '{screen}', documented at route '{route}', but "
            f"the page it photographed was at '{url}' — the walk did not arrive, so every "
            "placement verdict would be about a screen the book does not describe"
        )

    def _vet(
        self, scenario_id: str, record: dict[str, Any], *, step: tuple[str, str] | None = None
    ) -> tuple[list[placement.ComponentVerdict], list[str]]:
        """Register one photographed screen against the screen the book documents."""
        screen = str(record.get("screen", ""))
        shot = Path(str(record.get("screenshot", "")))
        regions_path = Path(str(record.get("regions", "")))
        layout_path = shot.with_suffix(".layout.json")
        components = self._book().get(screen)
        if self._book_problem is not None:
            return [], [self._book_problem]
        if components is None:
            return [], [
                f"scenario '{scenario_id}' vets '{screen}', which the book does not document "
                "as a screen with components — name the screen file the state belongs to"
            ]
        if not regions_path.is_file() or not layout_path.is_file():
            return [], [
                f"scenario '{scenario_id}' vetted '{screen}' but produced no scan beside "
                f"{shot.name} — the page was gone by the time it was measured"
            ]
        elsewhere = self._arrival(scenario_id, screen, record)
        if elsewhere is not None:
            return [], [elsewhere]
        requested = record.get("components", [])
        if requested:
            components = [
                component
                for component in components
                if component.node_id.rsplit("#", 1)[-1] in requested
            ]
            missing = sorted(set(requested) - {component.node_id.rsplit("#", 1)[-1] for component in components})
            if missing:
                return [], [
                    f"scenario '{scenario_id}' vetted '{screen}' with undocumented component(s): {missing}"
                ]
        frame = json.loads(layout_path.read_text(encoding="utf-8"))["viewport"]
        viewport = placement.Viewport(width=frame["width"], height=frame["height"])
        regions = RegionList.validate_json(regions_path.read_bytes())
        verdicts = placement.check(components, regions, viewport)

        report = {
            "schema": "vet-placement/1",
            "screen": screen,
            "state": str(record.get("state", "")),
            "screenshot": shot.name,
            "viewport": {"width": viewport.width, "height": viewport.height},
            "regionCount": len(regions),
            "arrival": (
                "confirmed"
                if record.get("url") and literal_route(self._routes.get(screen, ""))
                else ("unobserved" if not record.get("url") else "unstated")
            ),
            "url": str(record.get("url", "")),
            "verdicts": [verdict.model_dump(mode="json") for verdict in verdicts],
        }
        report_path = shot.with_suffix(".vet.json")
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.session.register_artifact(
            report_path,
            kind="vet",
            scenario=scenario_id,
            target=self.target_id,
            **({"metadata": {"step": step[0], "step_label": step[1]}} if step else {}),
        )
        return verdicts, []


class Launcher:
    """Where a scenario process runs, and what films it."""

    def preflight(self, driver: PythonDriver) -> None:
        """Refuse a target whose runtime is absent."""
        return None

    def window_recorder(
        self, driver: PythonDriver, *, width: int, height: int, fps: int, display: str = ""
    ) -> DisplayRecorder:
        raise NotImplementedError

    def execute(
        self, driver: PythonDriver, scenario_id: str, timeout: float, context: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        raise NotImplementedError

    def no_result_hint(self) -> str:
        """What to add when a scenario dies before grading itself."""
        return ""


class LocalLauncher(Launcher):
    """A subprocess on this machine, under the project's own interpreter."""

    def preflight(self, driver: PythonDriver) -> None:
        interpreter = driver.interpreter()
        if not interpreter.exists():
            raise DriverBlocked(
                f"target '{driver.target_id}' names interpreter '{interpreter}', which does not "
                "exist — create the project venv, or drop `interpreter=` to use ostler's own"
            )

    def window_recorder(
        self, driver: PythonDriver, *, width: int, height: int, fps: int, display: str = ""
    ) -> DisplayRecorder:
        return DisplayRecorder(
            driver.session,
            driver.target_id,
            width=width,
            height=height,
            fps=fps,
            display=display,
        )

    def execute(
        self, driver: PythonDriver, scenario_id: str, timeout: float, context: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        read_fd, write_fd = os.pipe()
        env = harness_env(driver.session.command_env())
        env["OSTLER_QA_RECORD_FD"] = str(write_fd)
        if driver.launch_env.get("DISPLAY"):
            env["DISPLAY"] = driver.launch_env["DISPLAY"]
        process = subprocess.Popen(  # noqa: S603 — agent-authored plan, explicit user intent
            harness_argv(
                driver.interpreter(),
                "run",
                str(driver.module_path()),
                scenario_id,
                json.dumps(context),
            ),
            cwd=driver.root,
            env=env,
            pass_fds=(write_fd,),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        os.close(write_fd)
        records: list[dict[str, Any]] = []
        reader = threading.Thread(target=_drain, args=(read_fd, records), daemon=True)
        reader.start()
        timed_out = False
        try:
            output_raw, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            output_raw, _ = process.communicate()
            timed_out = True
        reader.join(timeout=5)
        safe = _redact_bytes(output_raw or b"", driver.session.secret_values.values())
        return records, safe.decode("utf-8", errors="replace"), process.returncode, timed_out


def _drain(read_fd: int, records: list[dict[str, Any]]) -> None:
    """Read the record stream to EOF, keeping whatever parsed."""
    with os.fdopen(read_fd, "r", encoding="utf-8") as stream:
        for line in stream:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    """SIGKILL the whole process group: a scenario's own children outlive it otherwise."""
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()


class DisplayRecorder:
    """Film the X display the browser is drawn on — one this recorder owns."""

    def __init__(
        self,
        session: QaSession,
        target: str,
        *,
        width: int,
        height: int,
        fps: int,
        display: str = "",
    ) -> None:
        self.session = session
        self.target = target
        self.width = width
        self.height = height
        self.fps = fps
        self.display = display
        self._xvfb: subprocess.Popen[bytes] | None = None
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self.path = session.qa_dir / "videos" / f"{target}.mp4"
        self.started = 0.0
        self.start_offset = 0

    def argv(self) -> list[str]:
        return [
            "ffmpeg", "-y", "-f", "x11grab", "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(self.fps), "-i", f"{self.display}.0", "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(self.path),
        ]

    def start(self) -> dict[str, str]:
        if shutil.which("ffmpeg") is None:
            raise DriverBlocked("ffmpeg is required for browser-window recording")
        env = dict(os.environ)
        if not self.display:
            if shutil.which("Xvfb") is None:
                raise DriverBlocked(
                    "window recording requires Xvfb — it films a display of its own rather "
                    "than whatever screen $DISPLAY happens to name; declare "
                    "`recording.display` on the target to point it at an existing one"
                )
            self.display = f":{90 + os.getpid() % 100}"
            self._xvfb = subprocess.Popen(
                ["Xvfb", self.display, "-screen", "0", f"{self.width}x{self.height}x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
        env["DISPLAY"] = self.display
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ffmpeg = subprocess.Popen(
            self.argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        time.sleep(0.5)
        if self._ffmpeg.poll() is not None:
            raise DriverBlocked("ffmpeg browser-window recorder failed to start")
        self.started = time.monotonic()
        self.start_offset = self.session.offset_ms()
        self.session.append({"kind": "video_start", "target": self.target, "driver": "playwright", "mode": "window"})
        return env

    def stop(self) -> None:
        try:
            if self._ffmpeg is not None and self._ffmpeg.poll() is None:
                if self._ffmpeg.stdin:
                    self._ffmpeg.stdin.write(b"q\n")
                    self._ffmpeg.stdin.flush()
                self._ffmpeg.wait(timeout=10)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            if self._ffmpeg is not None:
                self._ffmpeg.kill()
                self._ffmpeg.wait()
        finally:
            if self._xvfb is not None:
                self._xvfb.terminate()
                self._xvfb.wait(timeout=5)
        self._finalize()

    def _finalize(self) -> None:
        """Measure the finished file and file it — the half that does not care where ffmpeg ran."""
        if not self.started:
            return
        if not self.path.is_file() or not self.path.stat().st_size:
            raise RuntimeError("browser-window recording could not be finalized")
        duration = time.monotonic() - self.started
        metadata = _probe_media(self.path)
        if metadata.get("durationSeconds", 0) + 2 < duration:
            raise RuntimeError("browser-window recording does not cover the logged target interval")
        if metadata.get("width") != self.width or metadata.get("height") != self.height:
            raise RuntimeError("browser-window recording dimensions do not match the target")
        if abs(float(metadata.get("fps", 0)) - self.fps) > 2:
            raise RuntimeError("browser-window recording frame rate does not match the target")
        if _is_static(self.path, metadata.get("durationSeconds", 0)):
            raise RuntimeError(
                "browser-window recording never changes — the display was filmed but nothing "
                "was drawn on it; the browser did not open headed onto it"
            )
        entry = self.session.register_artifact(
            self.path,
            kind="video",
            target=self.target,
            metadata={
                "mode": "window",
                "actionStartOffsetMs": self.start_offset,
                "actionEndOffsetMs": self.session.offset_ms(),
                **metadata,
            },
        )
        self.session.append({"kind": "video_stop", "target": self.target, "driver": "playwright", "artifact": entry["path"]})


class DeviceRecorder:
    def __init__(self, session: QaSession, target_id: str, target: dict[str, Any]) -> None:
        self.session = session
        self.target_id = target_id
        self.target = target
        self.process: subprocess.Popen[bytes] | None = None
        self.started = False
        self.start_offset = 0
        self.path = session.qa_dir / "videos" / f"{target_id}.mp4"
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_error = ""
        self._segments: list[tuple[Path, int, int]] = []
        self._remote_segments: list[tuple[str, Path, int, int]] = []

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.target.get("device", "android") == "android":
            if shutil.which("adb") is None:
                raise DriverBlocked("adb is required for Android recording")
            state = subprocess.run(
                ["adb", "get-state"], capture_output=True, text=True, timeout=10
            )
            if state.returncode or state.stdout.strip() != "device":
                raise DriverBlocked("no available Android device for recording")
            self._thread = threading.Thread(target=self._android_loop, daemon=True)
            self._thread.start()
            self._started_event.wait(timeout=10)
        else:
            if shutil.which("xcrun") is None:
                raise DriverBlocked("xcrun is required for iOS simulator recording")
            self.process = subprocess.Popen(["xcrun", "simctl", "io", "booted", "recordVideo", str(self.path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        if self._thread_error or self.process is None or self.process.poll() is not None:
            raise DriverBlocked("device recorder failed to start")
        self.started = True
        self.start_offset = self.session.offset_ms()
        self.session.append({"kind": "video_start", "target": self.target_id, "driver": "maestro", "mode": "device"})

    def stop(self) -> None:
        self._stop_event.set()
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
        if self._thread is not None:
            self._thread.join(timeout=45 * max(1, len(self._remote_segments) + 1))
            if self._thread.is_alive():
                raise RuntimeError("device recorder did not stop cleanly")
        elif self.process is not None and self.process.poll() is None:
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if not self.started:
            return
        if self._thread_error:
            raise RuntimeError(f"device recorder failed: {self._thread_error}")
        if self.target.get("device", "android") != "android":
            self._segments = [(self.path, self.start_offset, self.session.offset_ms())]
        entries: list[dict[str, Any]] = []
        for order, (path, start, end) in enumerate(self._segments, start=1):
            if not path.is_file() or not path.stat().st_size:
                raise RuntimeError("device recording segment could not be finalized")
            entry = self.session.register_artifact(
                path,
                kind="video",
                target=self.target_id,
                metadata={
                    "mode": "device",
                    "segment": order,
                    "actionStartOffsetMs": start,
                    "actionEndOffsetMs": end,
                    **_probe_media(path),
                },
            )
            entries.append(entry)
            self.session.append(
                {
                    "kind": "video_segment",
                    "target": self.target_id,
                    "driver": "maestro",
                    "segment": order,
                    "start_offset_ms": start,
                    "end_offset_ms": end,
                    "artifact": entry["path"],
                }
            )
        if not entries:
            raise RuntimeError("device recording could not be finalized")
        self.session.append(
            {
                "kind": "video_stop",
                "target": self.target_id,
                "driver": "maestro",
                "artifacts": [entry["path"] for entry in entries],
            }
        )

    def _android_loop(self) -> None:
        index = 0
        try:
            while not self._stop_event.is_set():
                index += 1
                remote = f"/sdcard/ostler-{self.session.run_id}-{index:03d}.mp4"
                path = self.session.qa_dir / "videos" / f"{self.target_id}-{index:03d}.mp4"
                start = self.session.offset_ms()
                self.process = subprocess.Popen(
                    [
                        "adb",
                        "shell",
                        "screenrecord",
                        "--time-limit",
                        "170",
                        remote,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self._started_event.set()
                while self.process.poll() is None and not self._stop_event.wait(0.2):
                    pass
                if self.process.poll() is None:
                    self.process.send_signal(signal.SIGINT)
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                self._remote_segments.append(
                    (remote, path, start, self.session.offset_ms())
                )
            for remote, path, start, end in self._remote_segments:
                pull = subprocess.run(
                    ["adb", "pull", remote, str(path)], capture_output=True, timeout=30
                )
                subprocess.run(
                    ["adb", "shell", "rm", remote], capture_output=True, timeout=10
                )
                if pull.returncode or not path.is_file() or not path.stat().st_size:
                    raise RuntimeError("could not pull Android recording segment")
                self._segments.append((path, start, end))
        except Exception as exc:  # noqa: BLE001
            self._thread_error = str(exc)
            self._started_event.set()


def create_driver(
    session: QaSession,
    target_id: str,
    target: dict[str, Any],
    *,
    root: Path,
    variables: dict[str, str],
    obligation_documents: Mapping[str, list[str]] | None = None,
) -> QaDriver:
    """Build the one driver there is."""
    return PythonDriver(
        session,
        target_id,
        target,
        root=root,
        variables=variables,
        obligation_documents=obligation_documents,
    )


def _is_static(path: Path, duration: float) -> bool:
    """Is the whole recording one unchanging frame?"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to check a recording is not one frozen frame")
    if duration <= 0:
        return False
    probe = subprocess.run(  # noqa: S603 — fixed argv
        [
            "ffmpeg", "-v", "info", "-nostats", "-i", str(path),
            "-vf", f"freezedetect=n=-70dB:d={max(duration - 0.5, 0.5):.3f}",
            "-map", "0:v", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return "freeze_start" in probe.stderr


def _probe_media(path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is required to validate recording metadata")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"recording metadata is not parseable: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError("recording has no video stream")
    stream = streams[0]
    numerator, _, denominator = str(stream.get("avg_frame_rate", "0/1")).partition("/")
    fps = float(numerator) / float(denominator or 1)
    return {
        "durationSeconds": float(data.get("format", {}).get("duration", 0)),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "fps": round(fps, 3),
    }
