"""The Android pieces the QA harness and a mobile book share: the adb command line, the device state and the
screen recording that `adb screenrecord` writes in segments."""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

SEGMENT_SECONDS = 170


def adb(serial: str = "") -> list[str]:
    """The adb command line, aimed at one device when `serial` names it."""
    return ["adb", *(["-s", serial] if serial else [])]


def device_state(serial: str = "", timeout: float = 15) -> str:
    """What `adb get-state` prints for the device, or "" when adb says there is none."""
    done = subprocess.run([*adb(serial), "get-state"], capture_output=True, text=True, timeout=timeout, check=False)
    return "" if done.returncode else done.stdout.strip()


def ready(serial: str = "") -> bool:
    return shutil.which("adb") is not None and device_state(serial) == "device"


class ScreenRecording:
    """Records the screen into segments of at most `SEGMENT_SECONDS` until `stop_event` is set, then pulls them.
    `clock` says where the run is in milliseconds, so each segment carries the span it covers."""

    def __init__(self, directory: Path, stem: str, token: str, clock: Callable[[], int], serial: str = "") -> None:
        self.directory = directory
        self.stem = stem
        self.token = token
        self.clock = clock
        self.serial = serial
        self.process: subprocess.Popen[bytes] | None = None
        self.stop_event = threading.Event()
        self.started_event = threading.Event()
        self.error = ""
        self.remote_segments: list[tuple[str, Path, int, int]] = []
        self.segments: list[tuple[Path, int, int]] = []
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        self.started_event.wait(timeout=10)

    def await_release(self, remote: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            held = subprocess.run([*adb(self.serial), "shell", "pgrep", "-f", remote], capture_output=True, timeout=10)
            if held.returncode:
                return
            time.sleep(0.2)

    def loop(self) -> None:
        index = 0
        try:
            while not self.stop_event.is_set():
                index += 1
                remote = f"/sdcard/ostler-{self.token}-{index:03d}.mp4"
                path = self.directory / f"{self.stem}-{index:03d}.mp4"
                start = self.clock()
                self.process = subprocess.Popen(
                    [*adb(self.serial), "shell", "screenrecord", "--time-limit", str(SEGMENT_SECONDS), remote],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.started_event.set()
                while self.process.poll() is None and not self.stop_event.wait(0.2):
                    pass
                if self.process.poll() is None:
                    subprocess.run([*adb(self.serial), "shell", "pkill", "-INT", "-f", remote], capture_output=True, timeout=10)
                try:
                    self.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
                self.await_release(remote)
                self.remote_segments.append((remote, path, start, self.clock()))
            for remote, path, start, end in self.remote_segments:
                pull = subprocess.run([*adb(self.serial), "pull", remote, str(path)], capture_output=True, timeout=30)
                subprocess.run([*adb(self.serial), "shell", "rm", remote], capture_output=True, timeout=10)
                if pull.returncode or not path.is_file() or not path.stat().st_size:
                    raise RuntimeError("could not pull Android recording segment")
                self.segments.append((path, start, end))
        except Exception as exc:  # noqa: BLE001
            self.error = str(exc)
            self.started_event.set()
