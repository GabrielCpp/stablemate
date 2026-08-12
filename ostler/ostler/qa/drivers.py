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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from ostler.qa.harness_host import (
    DEFAULT_SCENARIO_TIMEOUT,
    default_interpreter,
    harness_argv,
    harness_env,
)
from ostler.qa.session import QaSession, _redact_bytes


@dataclass
class ScenarioResult:
    status: str
    assertions: int = 0
    failures: int = 0
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The two recorders that cannot move into the scenario process, because both film
        # something *around* it: ffmpeg grabs the X display the browser is drawn on, and
        # simctl/adb film a device that outlives any one scenario.
        self._window_recorder: DisplayRecorder | None = None
        self._device_recorder: DeviceRecorder | None = None
        self._launch_env: dict[str, str] = {}

    def start(self) -> None:
        self._start_interpreter()
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
        self._window_recorder = DisplayRecorder(
            self.session,
            self.target_id,
            width=int(viewport.get("width", 1440)),
            height=int(viewport.get("height", 900)),
            fps=int(recording.get("fps", 30)),
        )
        # The whole environment, including the DISPLAY the browser must be launched onto —
        # which is the one thing the scenario process cannot work out for itself.
        self._launch_env = self._window_recorder.start()

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

    def _start_interpreter(self) -> None:
        interpreter = self.interpreter()
        if not interpreter.exists():
            # Blocked, not failed: an interpreter that is not there says nothing about the
            # product, and a run that reports it as a product failure sends the workflow to
            # repair a plan that is fine.
            raise DriverBlocked(
                f"target '{self.target_id}' names interpreter '{interpreter}', which does not "
                "exist — create the project venv, or drop `interpreter=` to use ostler's own"
            )

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
        }
        read_fd, write_fd = os.pipe()
        env = harness_env(self.session.command_env())
        env["OSTLER_QA_RECORD_FD"] = str(write_fd)
        if self._launch_env.get("DISPLAY"):
            env["DISPLAY"] = self._launch_env["DISPLAY"]
        process = subprocess.Popen(  # noqa: S603 — agent-authored plan, explicit user intent
            harness_argv(
                self.interpreter(),
                "run",
                str(self.module_path()),
                scenario_id,
                json.dumps(context),
            ),
            cwd=self.root,
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
        safe = _redact_bytes(output_raw or b"", self.session.secret_values.values())
        return records, safe.decode("utf-8", errors="replace"), process.returncode, timed_out

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
                    covers=list(record.get("covers") or covers),
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
                f"scenario '{scenario_id}' produced no result (exit {exit_code}): "
                + output.strip()[-500:]
            )
        elif terminal.get("error"):
            message = str(terminal["error"]).strip()[-2000:]
        if problems:
            message = "; ".join([part for part in [message, *problems] if part])

        status = "passed"
        if (
            timed_out
            or terminal is None
            or failures
            or problems
            or (terminal or {}).get("status") != "passed"
        ):
            status = "failed"
            failures = max(failures, 1)
        return ScenarioResult(
            status=status, assertions=assertions, failures=failures, message=message
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
        self.session.register_artifact(
            path,
            kind=kind,
            scenario=scenario_id,
            target=self.target_id,
            **({"metadata": metadata} if metadata else {}),
        )
        return problems


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
