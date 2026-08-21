"""Execution adapter for a QA target: run its scenarios as Python, and keep the ledger.

One driver, because there is one plan format. What a target selects is what the scenario
process needs around it — a screen recording for a browser, a device recording for a
simulator — not how its steps are interpreted; the steps are a function body.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from ostler.model import load as load_graph
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


@dataclass
class ScenarioResult:
    status: str
    assertions: int = 0
    failures: int = 0
    #: The scenario stopped short of the end of its body, rather than reaching it and
    #: disagreeing. Everything it claimed to cover is unproven, whatever passed before.
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
    ) -> None:
        self.session = session
        self.target_id = target_id
        self.target = target
        self.root = root
        self.variables = variables

    def start(self) -> None:
        return None

    def run(self, scenario: dict[str, Any]) -> ScenarioResult:
        raise NotImplementedError

    def stop(self) -> None:
        return None


class PythonDriver(QaDriver):
    """Run one scenario as a Python function in a subprocess, and record what it claims.

    The subprocess boundary is what lets the scenario run under the project's own
    interpreter — with the project's HTTP client, its fixtures, its Playwright — while
    ostler keeps the ledger. It talks back over a dedicated pipe rather than stdout, so a
    `print` in a scenario stays debugging output instead of corrupting the protocol.

    Every assertion arrives already decided. That is the point of the format: the scenario
    compared parsed objects on the line that produced them, where a missing key raises
    instead of matching empty.
    """

    def __init__(self, *args: Any, launcher: "Launcher | None" = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # *Where* the scenario process runs, which is the one axis a sandbox changes. The
        # driver keeps everything else — the ledger, the grading, the recorders' contract —
        # so a containerized run and a local one are the same run with a different launcher.
        self.launcher: Launcher = launcher or LocalLauncher()
        # The two recorders that cannot move into the scenario process, because both film
        # something *around* it: ffmpeg grabs the X display the browser is drawn on, and
        # simctl/adb film a device that outlives any one scenario.
        self._window_recorder: DisplayRecorder | None = None
        self._device_recorder: DeviceRecorder | None = None
        self.launch_env: dict[str, str] = {}
        # The documented screens, read on the first `vet` record and kept for the target.
        self._screens: dict[str, list[placement.VettedComponent]] | None = None

    def start(self) -> None:
        self.launcher.preflight(self)
        problems = qa_tools.preflight_errors(self.root)
        if problems:
            raise DriverBlocked("; ".join(problems))
        driver = str(self.target.get("driver", "python"))
        recording = self.target.get("recording", {"required": True})
        if driver == "playwright":
            self._start_window_recorder(recording)
        elif driver == "maestro":
            self._start_device(recording)

    def _start_window_recorder(self, recording: dict[str, Any]) -> None:
        if not recording.get("required", True) or recording.get("mode", "window") != "window":
            return
        viewport = self.target.get("viewport", {"width": 1440, "height": 900})
        # The launcher chooses the recorder because the two have to agree about which
        # machine the browser is drawn on: filming the host's X display while the browser
        # runs in a container yields a valid, empty video, which reads as evidence.
        self._window_recorder = self.launcher.window_recorder(
            self,
            width=int(viewport.get("width", 1440)),
            height=int(viewport.get("height", 900)),
            fps=int(recording.get("fps", 30)),
        )
        # The whole environment, including the DISPLAY the browser must be launched onto —
        # which is the one thing the scenario process cannot work out for itself.
        self.launch_env = self._window_recorder.start()

    def _start_device(self, recording: dict[str, Any]) -> None:
        """Refuse a mobile target whose device is not there — blocked, not failed.

        This has to stay on ostler's side: a scenario that discovers mid-body that no
        simulator is booted reports it as a failed assertion against the product, and the
        workflow spends a lap repairing a plan that was correct.
        """
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

    # -- the subprocess ----------------------------------------------------------------

    def _execute(
        self, scenario_id: str, timeout: float
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        context = {
            "root": str(self.root),
            "spec_dir": str(self.session.spec_dir),
            # Already resolved against --out-dir. Handing the scenario the absolute path is
            # the deletion of a whole defect class: the same relative `qa/steps/x` used to
            # mean the spec dir to ostler and the repo root to the shell it ran, and one run
            # lost 38 of 66 assertions to the disagreement.
            "qa_dir": str(self.session.qa_dir),
            # Where the run's clock is right now. The scenario process has its own monotonic
            # zero, so without this every offset it records — a video's start, a console
            # message's `atMs` — would be measured from a different origin than the ledger's.
            "offset_ms": self.session.offset_ms(),
            # `{name: command}` for every QA tool this repo opted into and ostler resolved
            # to a definition — see `ostler.qa.tools`. `start()` already refused the run if
            # any opted-in tool didn't resolve, so this is always complete by the time a
            # scenario reaches for `qa.tool(...)`.
            "tools": qa_tools.resolved_commands(self.root),
        }
        return self.launcher.execute(self, scenario_id, timeout, context)

    def _write_output(self, scenario_id: str, output: str) -> None:
        """Keep the scenario's own stdout — this is where a traceback lands."""
        path = self.session.qa_dir / "steps" / f"{scenario_id}-stdout.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
        self.session.register_artifact(
            path, kind="command-output", scenario=scenario_id, target=self.target_id
        )

    # -- the ledger --------------------------------------------------------------------

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
        for record in records:
            kind = record.get("type")
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
                    # The assertion's own binding, never the scenario's as a fallback.
                    # Inheriting it credited every obligation in `covers` to every assertion
                    # in the body, so one unrelated passing check reported the whole set
                    # proven — and deleting the assertion that did the proving left the row
                    # green. `validate` now refuses a plan whose obligations are not each
                    # claimed by a check, so an empty binding here is a plan that never ran.
                    covers=list(record.get("covers") or []),
                    # What `qa.verify()` named and with which arguments, when it was a
                    # verify at all. A plain `qa.check` carries neither and stays an
                    # anonymous `scenario_check`; dropping them for a verify made the
                    # evidence map unable to see any declared check as observed, so every
                    # obligation a passing `verify:` bullet proved read `claimed-but-
                    # unasserted` — a whole run's worth of green assertions crediting
                    # nothing.
                    declared=_declared(record),
                )
                if not passed:
                    failures += 1
            elif kind == "step_end":
                self.session.append(
                    {
                        "kind": "step",
                        "id": str(record.get("id", "")),
                        "label": str(record.get("label", "")),
                        "cmd": "",
                        "exit_code": 1 if record.get("failed") else 0,
                        "driver": "python",
                        "scenario": scenario_id,
                    }
                )
            elif kind == "capture":
                self.session.set_capture(str(record["key"]), str(record["value"]))
            elif kind == "artifact":
                problems.extend(self._register(scenario_id, record))
            elif kind == "vet":
                try:
                    verdicts, trouble = self._vet(scenario_id, record)
                except ValueError as exc:
                    # A path the registration cannot place under the spec directory. It used
                    # to propagate to the runner's bare `except`, which turned one bad
                    # screenshot into `status="invalid"` for the whole run — the account of
                    # every scenario that had already passed, thrown away by the last one.
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
                            "actual": "; ".join(verdict.detail) or "as documented",
                            "expected": verdict.expected,
                        },
                        root=self.root,
                        scenario=scenario_id,
                        driver="python",
                        action=action,
                        covers=covers,
                    )
                    if not passed:
                        failures += 1
            elif kind == "scenario":
                terminal = record

        message = ""
        if timed_out:
            message = f"scenario '{scenario_id}' exceeded its timeout and was killed"
        elif terminal is None:
            # No terminal record means the scenario process died before the harness could
            # grade it — an ImportError, a segfault, a `sys.exit` in the body. The stdout
            # tail is the only account of it, so it goes in the message rather than being
            # left for someone to find in the artifact.
            message = (
                f"scenario '{scenario_id}' produced no result (exit {exit_code})"
                f"{self.launcher.no_result_hint()}: " + output.strip()[-500:]
            )
        elif terminal.get("error"):
            # The hint belongs here as much as above. A scenario that raised inside its body
            # graded itself, so the terminal record exists — but under the sandbox the raise
            # is usually a `FileNotFoundError` on a path that plainly *does* exist on the
            # host, and a reader with no idea the repository was taken away reads that as an
            # ostler defect and goes looking for it.
            message = str(terminal["error"]).strip()[-2000:] + self.launcher.no_result_hint()
        if problems:
            message = "; ".join([part for part in [message, *problems] if part])

        # The scenario stopped for a reason it did not itself record as an assertion: it was
        # killed, it raised, it never graded itself, the browser was left unclean, or it
        # reached the end having asserted nothing. That is a different thing from an
        # assertion that ran and disagreed — a failing check *is* the account, and the
        # record it wrote already says which obligation it sank. An abort leaves no such
        # record, and the asserts that ran before it proved a state the steps after them
        # never got to leave.
        terminal_status = (terminal or {}).get("status")
        aborted = bool(
            timed_out
            or terminal is None
            or problems
            or terminal_status == "errored"
            or (terminal_status != "passed" and not failures)
        )
        if aborted and covers:
            # Fail closed, over the whole `covers`. Publishing a scenario's obligations from
            # the green prefix it managed before dying is how a QA lane reported eleven
            # criteria `Pass` under an `overall: Fail` — and how a run whose one browser
            # locator timed out on the assertion that would have exposed the defect went out
            # as a covered obligation. A scenario that did not finish claims nothing, and it
            # says so in the one vocabulary every reader downstream already speaks.
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

    def _register(self, scenario_id: str, record: dict[str, Any]) -> list[str]:
        """File one artifact the scenario produced, holding a recording to the target's shape.

        The scenario knows *when* it filmed and ostler knows *what a recording must be*: the
        offsets come over the wire, the measurement is taken here with `ffprobe`, and the two
        are merged into one artifact entry. Splitting it the other way would put ffprobe in a
        stdlib-only harness and the target's declared dimensions in a process that never
        reads the plan.
        """
        path = Path(str(record["path"]))
        kind = str(record.get("kind", "evidence"))
        metadata = record.get("metadata")
        metadata = dict(metadata) if isinstance(metadata, dict) else {}
        problems: list[str] = []
        if kind == "video" and path.is_file():
            measured = _probe_media(path)
            metadata.update(measured)
            viewport = self.target.get("viewport", {"width": 1440, "height": 900})
            width, height = int(viewport.get("width", 1440)), int(viewport.get("height", 900))
            if measured.get("width") and (
                measured.get("width") != width or measured.get("height") != height
            ):
                problems.append(
                    f"scenario '{scenario_id}' recording is "
                    f"{measured.get('width')}x{measured.get('height')}, "
                    f"not the target's {width}x{height}"
                )
        try:
            self.session.register_artifact(
                path,
                kind=kind,
                scenario=scenario_id,
                target=self.target_id,
                **({"metadata": metadata} if metadata else {}),
            )
        except ValueError as exc:
            problems.append(f"scenario '{scenario_id}' produced an unusable artifact: {exc}")
        return problems

    # -- vetting -----------------------------------------------------------------------

    def _book(self) -> dict[str, list[placement.VettedComponent]]:
        """The documented screens, read once per target and kept.

        The graph is loaded here rather than handed down from the CLI because `qa run` also
        arrives through `ostler.api`, and a table built in only one of the two entry points
        would leave the other's runs silently unvetted — which is the exact failure mode
        this whole change exists to remove.
        """
        if self._screens is None:
            self._screens = placement.screen_components(load_graph(self.root))
        return self._screens

    def _vet(
        self, scenario_id: str, record: dict[str, Any]
    ) -> tuple[list[placement.ComponentVerdict], list[str]]:
        """Register one photographed screen against the screen the book documents.

        Anything that makes the registration vacuous — an unknown screen, a screen with no
        addressable component, a sidecar that is not there — is a *problem*, not an empty
        verdict list. A vacuous vet that reports zero disagreements is indistinguishable from
        a screen that is correct, and that is the shape of evidence this replaces.
        """
        screen = str(record.get("screen", ""))
        shot = Path(str(record.get("screenshot", "")))
        regions_path = Path(str(record.get("regions", "")))
        layout_path = shot.with_suffix(".layout.json")
        components = self._book().get(screen)
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
            "verdicts": [verdict.model_dump(mode="json") for verdict in verdicts],
        }
        report_path = shot.with_suffix(".vet.json")
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.session.register_artifact(
            report_path, kind="vet", scenario=scenario_id, target=self.target_id
        )
        return verdicts, []


class Launcher:
    """Where a scenario process runs, and what films it.

    Three methods, because three things depend on the machine: whether the runtime is
    there at all, how the process is started and killed, and which display the browser is
    drawn on. Everything else about a run — the ledger, the grading, the manifest, the
    vetting — is host-side and identical either way, which is the property that makes a
    sandboxed run comparable to a local one rather than a different kind of evidence.
    """

    def preflight(self, driver: PythonDriver) -> None:
        """Refuse a target whose runtime is absent. Raise `DriverBlocked`, never fail it."""
        return None

    def window_recorder(
        self, driver: PythonDriver, *, width: int, height: int, fps: int
    ) -> DisplayRecorder:
        raise NotImplementedError

    def execute(
        self, driver: PythonDriver, scenario_id: str, timeout: float, context: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], str, int, bool]:
        raise NotImplementedError

    def no_result_hint(self) -> str:
        """What to add when a scenario dies before grading itself.

        The exit code and a stdout tail are all `_grade` has, and on an unusual runtime that
        reads as an ostler defect. A launcher that removed a capability on purpose owes the
        reader that sentence.
        """
        return ""


class LocalLauncher(Launcher):
    """A subprocess on this machine, under the project's own interpreter."""

    def preflight(self, driver: PythonDriver) -> None:
        interpreter = driver.interpreter()
        if not interpreter.exists():
            # Blocked, not failed: an interpreter that is not there says nothing about the
            # product, and a run that reports it as a product failure sends the workflow to
            # repair a plan that is fine.
            raise DriverBlocked(
                f"target '{driver.target_id}' names interpreter '{interpreter}', which does not "
                "exist — create the project venv, or drop `interpreter=` to use ostler's own"
            )

    def window_recorder(
        self, driver: PythonDriver, *, width: int, height: int, fps: int
    ) -> DisplayRecorder:
        return DisplayRecorder(
            driver.session, driver.target_id, width=width, height=height, fps=fps
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
        # Drained on a thread. Both the record pipe and the merged stdout pipe are bounded,
        # so a scenario that fills one while the driver reads only the other deadlocks —
        # and it would do it exactly on the verbose scenarios, the ones already in trouble.
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
    """Read the record stream to EOF, keeping whatever parsed.

    A malformed line is dropped rather than raised on: the pipe is also how a scenario
    reports its own failure, and losing every record because the last write was cut short
    by a kill would throw away the account of what did happen.
    """
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
    def __init__(self, session: QaSession, target: str, *, width: int, height: int, fps: int) -> None:
        self.session = session
        self.target = target
        self.width = width
        self.height = height
        self.fps = fps
        self.display = os.environ.get("DISPLAY", "")
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
            # `moov` last is the mp4 default, and it is the atom a player needs *first*, so
            # the evidence would not play in a browser at all — a reviewer cannot tell that
            # from a recording that never happened.
            "-movflags", "+faststart",
            str(self.path),
        ]

    def start(self) -> dict[str, str]:
        if shutil.which("ffmpeg") is None:
            raise DriverBlocked("ffmpeg is required for browser-window recording")
        env = dict(os.environ)
        if not self.display:
            if shutil.which("Xvfb") is None:
                raise DriverBlocked("window recording requires DISPLAY or Xvfb")
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
        """Measure the finished file and file it — the half that does not care where ffmpeg ran.

        Split out so a recorder that films inside a container reuses these checks verbatim.
        They are the ones that matter: a recording of the wrong display is a valid mp4 of an
        empty desktop, and every guard below is there because that reads as evidence.
        """
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
) -> QaDriver:
    """Build the one driver there is.

    Every target — command, browser, mobile — is a Python module now, so what used to pick
    between four action interpreters picks nothing. The function stays because the runner
    calls it per target and because a second driver is a plausible future; a `driver:` key
    on the target is a label for the report, not a dispatch.
    """
    return PythonDriver(session, target_id, target, root=root, variables=variables)


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
