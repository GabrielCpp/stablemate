"""Execution adapters for command, Playwright, and Maestro QA targets."""

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
from urllib.parse import urljoin

import yaml

from ostler.qa.session import QaSession, _expand


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


class CommandDriver(QaDriver):
    def run(self, scenario: dict[str, Any]) -> ScenarioResult:
        assertions = failures = 0
        covers = list(scenario.get("covers", []))
        scenario_id = str(scenario["id"])
        for index, action in enumerate(scenario["actions"], start=1):
            command = str(action.get("cmd", ""))
            record = self.session.run_step(
                str(action.get("id") or f"{scenario_id}-{index}"),
                str(action.get("label") or command),
                str(scenario["mechanism"]),
                command,
                captures=list((action.get("capture") or {}).items()),
                out_path=str(action["out"]) if action.get("out") else None,
                allow_fail=True,
                timeout=float(action.get("timeout_seconds", action.get("timeout", 60))),
                cwd=self.root,
                variables=self.variables,
                scenario=scenario_id,
                driver="command",
                action=index,
                covers=covers,
            )
            if record["exit_code"] != 0:
                failures += 1
            for check, expected in _command_assertions(action):
                assertions += 1
                expected = self.session.expand(str(expected), self.variables)
                passed, params = _command_verdict(check, expected, record)
                checked, _ = self.session.run_assert(
                    f"{scenario_id}-{index}-{check}",
                    f"{check} == {expected!r}",
                    "field_equal",
                    params,
                    root=self.root,
                    scenario=scenario_id,
                    driver="command",
                    action=index,
                    covers=covers,
                )
                if not passed or not checked:
                    failures += 1
            if action.get("cloudwatch_confirm"):
                assertions += 1
                params = dict(action["cloudwatch_confirm"])
                params["filter"] = _expand(
                    str(params.get("filter", "")),
                    self.session.captures,
                    self.session.env,
                    variables=self.variables,
                )
                passed, _ = self.session.run_assert(
                    f"{scenario_id}-{index}-cloudwatch",
                    "CloudWatch confirmation",
                    "cloudwatch_filter",
                    params,
                    root=self.root,
                    scenario=scenario_id,
                    driver="command",
                    action=index,
                    covers=covers,
                )
                if not passed:
                    failures += 1
        return ScenarioResult(
            status="failed" if failures else "passed",
            assertions=assertions,
            failures=failures,
        )


class PlaywrightDriver(QaDriver):  # noqa: C901
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._playwright: Any = None
        self._browser: Any = None
        self._window_recorder: DisplayRecorder | None = None

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DriverBlocked("Playwright Python package is not installed") from exc
        recording = self.target.get("recording", {"required": True})
        mode = recording.get("mode", "window")
        launch_env = None
        if recording.get("required", True) and mode == "window":
            viewport = self.target.get("viewport", {"width": 1440, "height": 900})
            self._window_recorder = DisplayRecorder(
                self.session,
                self.target_id,
                width=int(viewport.get("width", 1440)),
                height=int(viewport.get("height", 900)),
                fps=int(recording.get("fps", 30)),
            )
            launch_env = self._window_recorder.start()
        self._playwright = sync_playwright().start()
        browser_name = str(self.target.get("browser", "chromium"))
        browser_type = getattr(self._playwright, browser_name, None)
        if browser_type is None:
            raise DriverBlocked(f"unknown Playwright browser '{browser_name}'")
        launch = {
            "headless": not recording.get("required", True) or mode != "window"
        }
        if launch_env:
            launch["env"] = launch_env
        try:
            self._browser = browser_type.launch(**launch)
        except Exception as exc:  # noqa: BLE001
            raise DriverBlocked(f"could not launch Playwright {browser_name}: {exc}") from exc

    def run(self, scenario: dict[str, Any]) -> ScenarioResult:  # noqa: C901
        scenario_id = str(scenario["id"])
        covers = list(scenario.get("covers", []))
        qa_dir = self.session.qa_dir
        recording = self.target.get("recording", {"required": True})
        mode = recording.get("mode", "window")
        video_dir = qa_dir / "videos" / scenario_id
        context_options: dict[str, Any] = {
            "viewport": self.target.get("viewport", {"width": 1440, "height": 900}),
        }
        if recording.get("required", True) and mode == "viewport":
            video_dir.mkdir(parents=True, exist_ok=True)
            context_options["record_video_dir"] = str(video_dir)
        context = self._browser.new_context(**context_options)
        scenario_start_offset = self.session.offset_ms()
        page = context.new_page()
        console_errors: list[str] = []
        failed_requests: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("requestfailed", lambda request: failed_requests.append(request.url))
        trace_path = qa_dir / "traces" / f"{scenario_id}.zip"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        assertions = failures = 0
        artifacts: list[str] = []
        try:
            if scenario.get("test_file"):
                return self._run_native(scenario)
            for index, action in enumerate(scenario["actions"], start=1):
                started = time.monotonic()
                operation = action.get("do") or action.get("expect") or action.get("capture")
                kind = "assert" if "expect" in action else "action"
                record: dict[str, Any] = {
                    "kind": kind,
                    "scenario": scenario_id,
                    "target": self.target_id,
                    "driver": "playwright",
                    "action": index,
                    "operation": operation,
                    "covers": covers,
                }
                try:
                    if "do" in action:
                        self._do(page, action)
                        record["result"] = "PASS"
                    elif "expect" in action:
                        assertions += 1
                        self._expect(page, action)
                        record["check"] = operation
                        record["locator"] = action.get("locator")
                        record["result"] = "PASS"
                    else:
                        path = self._capture(page, action, scenario_id, index)
                        entry = self.session.register_artifact(
                            path,
                            kind=str(operation),
                            scenario=scenario_id,
                            target=self.target_id,
                        )
                        artifacts.append(entry["path"])
                        record["result"] = "PASS"
                        record["artifacts"] = [entry["path"]]
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    if "expect" in action:
                        assertions += 0
                    record["result"] = "FAIL"
                    record["error"] = str(exc)
                    failure_path = qa_dir / "screenshots" / f"{scenario_id}-failure-{index}.png"
                    failure_path.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(failure_path), full_page=True)
                    entry = self.session.register_artifact(
                        failure_path,
                        kind="failure-screenshot",
                        scenario=scenario_id,
                        target=self.target_id,
                    )
                    artifacts.append(entry["path"])
                    record["artifacts"] = [entry["path"]]
                record["duration_ms"] = round((time.monotonic() - started) * 1000)
                self.session.append(record)
                if failures:
                    break
        finally:
            context.tracing.stop(path=str(trace_path))
            context.close()
            if trace_path.is_file():
                entry = self.session.register_artifact(
                    trace_path,
                    kind="playwright-trace",
                    scenario=scenario_id,
                    target=self.target_id,
                )
                artifacts.append(entry["path"])
            if video_dir.is_dir():
                video_count = 0
                for video in sorted(video_dir.glob("*")):
                    if video.is_file() and video.stat().st_size:
                        video_count += 1
                        metadata = {
                            "mode": "viewport",
                            "actionStartOffsetMs": scenario_start_offset,
                            "actionEndOffsetMs": self.session.offset_ms(),
                            **_probe_media(video),
                        }
                        viewport = self.target.get("viewport", {})
                        if viewport and (
                            metadata["width"] != int(viewport.get("width", metadata["width"]))
                            or metadata["height"] != int(viewport.get("height", metadata["height"]))
                        ):
                            raise RuntimeError("Playwright recording dimensions do not match the target")
                        expected_fps = float(recording.get("fps", metadata["fps"]))
                        if abs(float(metadata["fps"]) - expected_fps) > 2:
                            raise RuntimeError("Playwright recording frame rate does not match the target")
                        entry = self.session.register_artifact(
                            video,
                            kind="video",
                            scenario=scenario_id,
                            target=self.target_id,
                            metadata=metadata,
                        )
                        artifacts.append(entry["path"])
                if recording.get("required", True) and mode == "viewport" and video_count == 0:
                    raise RuntimeError("required Playwright viewport recording was not finalized")
            diagnostics = qa_dir / "traces" / f"{scenario_id}-diagnostics.json"
            diagnostics.write_text(
                json.dumps({"consoleErrors": console_errors, "failedRequests": failed_requests}, indent=2)
                + "\n",
                encoding="utf-8",
            )
            entry = self.session.register_artifact(
                diagnostics,
                kind="browser-diagnostics",
                scenario=scenario_id,
                target=self.target_id,
            )
            artifacts.append(entry["path"])
        return ScenarioResult(
            status="failed" if failures else "passed",
            assertions=assertions,
            failures=failures,
            artifacts=artifacts,
        )

    def stop(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
            if self._playwright is not None:
                self._playwright.stop()
        finally:
            if self._window_recorder is not None:
                self._window_recorder.stop()

    def _locator(self, page: Any, locator: dict[str, Any]) -> Any:
        if "role" in locator:
            return page.get_by_role(locator["role"], name=locator.get("name"))
        if "label" in locator:
            return page.get_by_label(locator["label"])
        if "test_id" in locator:
            return page.get_by_test_id(locator["test_id"])
        if "text" in locator:
            return page.get_by_text(locator["text"], exact=True)
        return page.locator(locator["css"])

    def _do(self, page: Any, action: dict[str, Any]) -> None:
        op = action["do"]
        timeout = float(action.get("timeout", 30)) * 1000
        locator = self._locator(page, action["locator"]) if action.get("locator") else None
        if op == "goto":
            url = self.session.expand(str(action["url"]), self.variables)
            page.goto(urljoin(str(self.target["base_url"]).rstrip("/") + "/", url.lstrip("/")), timeout=timeout)
        elif op == "reload":
            page.reload(timeout=timeout)
        elif op == "back":
            page.go_back(timeout=timeout)
        elif op in {"click", "tap"}:
            locator.click(timeout=timeout)
        elif op == "fill":
            value = self.session.expand(str(action.get("value", "")), self.variables)
            locator.fill(value, timeout=timeout)
        elif op == "select":
            value = self.session.expand(str(action.get("value", "")), self.variables)
            locator.select_option(value, timeout=timeout)
        elif op == "press":
            locator.press(str(action["key"]), timeout=timeout)
        elif op == "clear":
            locator.clear(timeout=timeout)
        elif op in {"wait_for", "wait_for_response"}:
            if op == "wait_for_response":
                expected_url = str(action["url"])
                page.wait_for_event(
                    "response",
                    predicate=lambda response: expected_url in response.url,
                    timeout=timeout,
                )
            else:
                locator.wait_for(state=str(action.get("state", "visible")), timeout=timeout)
        elif op == "wait_for_idle":
            page.wait_for_load_state("networkidle", timeout=timeout)
        else:
            raise ValueError(f"unsupported Playwright action: {op}")

    def _expect(self, page: Any, action: dict[str, Any]) -> None:
        from playwright.sync_api import expect

        op = action["expect"]
        timeout = float(action.get("timeout", 30)) * 1000
        value = self.session.expand(str(action.get("value", "")), self.variables)
        if op == "url":
            expect(page).to_have_url(value, timeout=timeout)
            return
        locator = self._locator(page, action["locator"])
        calls = {
            "visible": lambda: expect(locator).to_be_visible(timeout=timeout),
            "hidden": lambda: expect(locator).to_be_hidden(timeout=timeout),
            "enabled": lambda: expect(locator).to_be_enabled(timeout=timeout),
            "disabled": lambda: expect(locator).to_be_disabled(timeout=timeout),
            "selected": lambda: expect(locator).to_be_checked(timeout=timeout),
            "checked": lambda: expect(locator).to_be_checked(timeout=timeout),
            "text": lambda: expect(locator).to_have_text(value, timeout=timeout),
            "value": lambda: expect(locator).to_have_value(value, timeout=timeout),
            "count": lambda: expect(locator).to_have_count(int(value), timeout=timeout),
        }
        calls[op]()

    def _capture(self, page: Any, action: dict[str, Any], scenario: str, index: int) -> Path:
        op = action["capture"]
        name = str(action.get("name") or f"{scenario}-{index}")
        if op == "screenshot":
            path = self.session.qa_dir / "screenshots" / f"{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=bool(action.get("full_page", True)))
        elif op == "body_text":
            path = self.session.qa_dir / "traces" / f"{name}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(page.locator("body").inner_text(), encoding="utf-8")
        elif op == "accessibility_snapshot":
            path = self.session.qa_dir / "traces" / f"{name}-accessibility.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = page.accessibility.snapshot()
            path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
        else:
            raise ValueError(f"capture '{op}' is produced automatically or unsupported")
        return path

    def _run_native(self, scenario: dict[str, Any]) -> ScenarioResult:
        scenario_id = str(scenario["id"])
        output = self.session.qa_dir / "traces" / f"{scenario_id}-native.txt"
        output.parent.mkdir(parents=True, exist_ok=True)
        command = ["npx", "playwright", "test", str(scenario["test_file"])]
        if scenario.get("test_name"):
            command.extend(["--grep", str(scenario["test_name"])])
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, timeout=600)
        output.write_text(result.stdout + result.stderr, encoding="utf-8")
        self.session.register_artifact(output, kind="native-test-output", scenario=scenario_id, target=self.target_id)
        self.session.append({
            "kind": "assert",
            "scenario": scenario_id,
            "driver": "playwright",
            "check": "native-test",
            "action": 1,
            "result": "PASS" if result.returncode == 0 else "FAIL",
            "covers": scenario.get("covers", []),
        })
        return ScenarioResult(status="passed" if result.returncode == 0 else "failed", assertions=1, failures=int(result.returncode != 0))


class MaestroDriver(QaDriver):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._recorder: DeviceRecorder | None = None

    def start(self) -> None:
        if shutil.which("maestro") is None:
            raise DriverBlocked("maestro CLI is not installed")
        device = self.target.get("device", "android")
        if device == "android" and shutil.which("adb"):
            app = subprocess.run(
                ["adb", "shell", "pm", "path", str(self.target["app_id"])],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if app.returncode or not app.stdout.strip():
                raise DriverBlocked(f"app {self.target['app_id']} is not installed on Android")
        elif device != "android" and shutil.which("xcrun"):
            app = subprocess.run(
                [
                    "xcrun",
                    "simctl",
                    "get_app_container",
                    "booted",
                    str(self.target["app_id"]),
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if app.returncode:
                raise DriverBlocked(f"app {self.target['app_id']} is unavailable on iOS simulator")
        recording = self.target.get("recording", {"required": True})
        if recording.get("required", True):
            self._recorder = DeviceRecorder(self.session, self.target_id, self.target)
            self._recorder.start()

    def run(self, scenario: dict[str, Any]) -> ScenarioResult:
        scenario_id = str(scenario["id"])
        generated = self.session.qa_dir / "generated" / f"{scenario_id}.yaml"
        generated.parent.mkdir(parents=True, exist_ok=True)
        if scenario.get("maestro_flow"):
            flow = (self.root / str(scenario["maestro_flow"])).resolve()
        else:
            flow = generated
            compiled_scenario = _map_strings(
                scenario,
                lambda value: self.session.symbolic_driver_value(value, self.variables),
            )
            flow.write_text(
                _compile_maestro(self.target, compiled_scenario), encoding="utf-8"
            )
            self.session.register_artifact(flow, kind="generated-maestro-flow", scenario=scenario_id, target=self.target_id)
        junit = self.session.qa_dir / "traces" / f"{scenario_id}-junit.xml"
        output = self.session.qa_dir / "traces" / f"{scenario_id}-maestro.txt"
        test_output = self.session.qa_dir / "generated" / f"{scenario_id}-maestro-output"
        test_output.mkdir(parents=True, exist_ok=True)
        junit.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "maestro",
            "test",
            "--format",
            "junit",
            "--output",
            str(junit),
            "--test-output-dir",
            str(test_output),
            str(flow),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=float(scenario.get("timeout", 600)),
                env={**os.environ, **self.session.driver_secret_env()},
            )
            combined = f"{result.stdout}\n{result.stderr}".lower()
            blocked = any(
                marker in combined
                for marker in (
                    "no device",
                    "device unavailable",
                    "unable to launch app",
                    "app is not installed",
                    "connection refused",
                )
            )
        except subprocess.TimeoutExpired as exc:
            result = subprocess.CompletedProcess(command, 124, exc.stdout or "", exc.stderr or "")
            blocked = False
        output.write_text(str(result.stdout) + str(result.stderr), encoding="utf-8")
        self.session.register_artifact(output, kind="maestro-output", scenario=scenario_id, target=self.target_id)
        if junit.is_file():
            self.session.register_artifact(junit, kind="junit", scenario=scenario_id, target=self.target_id)
        status = "blocked" if blocked else ("passed" if result.returncode == 0 else "failed")
        for index, action in enumerate(scenario.get("actions", []), start=1):
            self.session.append(
                {
                    "kind": "action",
                    "scenario": scenario_id,
                    "target": self.target_id,
                    "driver": "maestro",
                    "action": index,
                    "operation": action.get("do") or action.get("expect") or action.get("capture"),
                    "translated": action,
                    "result": "PASS" if status == "passed" else "FAIL",
                }
            )
        for artifact in sorted(test_output.rglob("*")):
            if not artifact.is_file() or not artifact.stat().st_size:
                continue
            kind = "maestro-screenshot" if artifact.suffix.lower() == ".png" else "maestro-diagnostic"
            self.session.register_artifact(
                artifact,
                kind=kind,
                scenario=scenario_id,
                target=self.target_id,
            )
        self.session.append({
            "kind": "assert",
            "scenario": scenario_id,
            "target": self.target_id,
            "driver": "maestro",
            "check": "maestro-flow",
            "action": 1,
            "result": "PASS" if status == "passed" else "FAIL",
            "covers": scenario.get("covers", []),
        })
        return ScenarioResult(status=status, assertions=1, failures=int(status != "passed"))

    def stop(self) -> None:
        if self._recorder is not None:
            self._recorder.stop()


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
            [
                "ffmpeg", "-y", "-f", "x11grab", "-video_size", f"{self.width}x{self.height}",
                "-framerate", str(self.fps), "-i", f"{self.display}.0", "-c:v", "libx264",
                "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(self.path),
            ],
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
    classes = {"command": CommandDriver, "playwright": PlaywrightDriver, "maestro": MaestroDriver}
    return classes[target["driver"]](session, target_id, target, root=root, variables=variables)


def _command_assertions(action: dict[str, Any]) -> list[tuple[str, Any]]:
    return [(key, action[key]) for key in ("assert_contains", "expect_http", "assert_count") if key in action]


def _command_verdict(check: str, expected: Any, record: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    stdout = str(record.get("_stdout_actual", record.get("_stdout", "")))
    if check == "assert_contains":
        passed = str(expected) in stdout
    elif check == "expect_http":
        passed = record.get("http_status") == int(expected)
    else:
        try:
            value = json.loads(stdout)
            passed = isinstance(value, list) and len(value) == int(expected)
        except (json.JSONDecodeError, ValueError):
            passed = False
    return passed, {"a": "PASS" if passed else "FAIL", "b": "PASS"}


def _compile_maestro(target: dict[str, Any], scenario: dict[str, Any]) -> str:
    commands: list[dict[str, Any] | str] = []
    for action in scenario["actions"]:
        op = action.get("do") or action.get("expect") or action.get("capture")
        locator = action.get("locator", {})
        selector = {"id": locator["id"]} if "id" in locator else {"text": locator.get("text", "")}
        if "do" in action:
            if op == "launch":
                commands.append({"launchApp": {"clearState": bool(action.get("clear_state", False))}})
            elif op in {"tap", "click"}:
                commands.append({"tapOn": selector})
            elif op == "fill":
                commands.extend([{"tapOn": selector}, {"inputText": str(action.get("value", ""))}])
            elif op == "clear":
                commands.extend([{"tapOn": selector}, "eraseText"])
            elif op == "back":
                commands.append("back")
            elif op == "reload":
                commands.append("stopApp")
                commands.append("launchApp")
            elif op == "wait_for":
                commands.append({"extendedWaitUntil": {"visible": selector, "timeout": int(float(action.get("timeout", 30)) * 1000)}})
            elif op == "wait_for_idle":
                commands.append("waitForAnimationToEnd")
            else:
                raise ValueError(f"unsupported Maestro action: {op}")
        elif "expect" in action:
            if op == "visible":
                commands.append({"assertVisible": selector})
            elif op == "hidden":
                commands.append({"assertNotVisible": selector})
            elif op in {"text", "value"}:
                commands.append({"assertVisible": {**selector, "text": str(action["value"])}})
            else:
                raise ValueError(f"unsupported Maestro expectation: {op}")
        elif op == "screenshot":
            commands.append({"takeScreenshot": str(action.get("name", scenario["id"]))})
        else:
            raise ValueError(f"unsupported Maestro capture: {op}")
    header = yaml.safe_dump({"appId": target["app_id"]}, sort_keys=False)
    body = yaml.safe_dump(commands, sort_keys=False)
    return f"{header}---\n{body}"


def _map_strings(value: Any, transform: Any) -> Any:
    if isinstance(value, str):
        return transform(value)
    if isinstance(value, dict):
        return {key: _map_strings(item, transform) for key, item in value.items()}
    if isinstance(value, list):
        return [_map_strings(item, transform) for item in value]
    return value


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
