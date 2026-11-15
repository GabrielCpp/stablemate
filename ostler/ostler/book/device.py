"""An Android device for the surfaces that are mobile screens. Reads the screen the way the QA harness does, through
the one resident Maestro, and acts on it through adb, so a book never imports either.

Every wait is on a condition: a component present, absent or enabled in a fresh reading of the screen. No wait is
on a clock."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler.book.errors import BookError
from ostler.book.outcome import CannotReach, cut_by_limit
from ostler.book.screen import ROLES, Component, Screen
from ostler.qa import android
from ostler.qa.android import ScreenRecording
from ostler.qa.harness_host import load_harness_module

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
NAMES = ("accessibilityText", "text", "hintText")
TYPED = re.compile(r"[ -~]*")
EDITS = {"field", "textarea", "date"}


CHUNK = 40


@dataclass(frozen=True)
class Node:
    """One drawn element of the screen: what it is called, where it sits and whether it takes input."""

    id: str
    names: tuple[str, ...]
    kind: str
    box: tuple[int, int, int, int]
    enabled: bool
    text: str

    def inside(self, outer: "Node") -> bool:
        return self.box[0] >= outer.box[0] and self.box[1] >= outer.box[1] and self.box[2] <= outer.box[2] and self.box[3] <= outer.box[3]

    @property
    def centre(self) -> tuple[int, int]:
        return (self.box[0] + self.box[2]) // 2, (self.box[1] + self.box[3]) // 2


def nodes_of(raw: str) -> list[Node]:
    """The drawn elements of the hierarchy Maestro prints, in reading order."""
    out: list[Node] = []
    stack = [json.loads(raw[raw.find("{"):])]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.get("children") or []))
        attributes = node.get("attributes") or {}
        found = BOUNDS.match(attributes.get("bounds") or "")
        if found is None:
            continue
        x, y, x2, y2 = (int(part) for part in found.groups())
        if x2 <= x or y2 <= y:
            continue
        text = str(attributes.get("text") or "")
        if text and text == str(attributes.get("hintText") or ""):
            text = ""
        names = tuple(value for key in NAMES if (value := str(attributes.get(key) or "").strip()))
        kind = (attributes.get("class") or "").rsplit(".", 1)[-1]
        out.append(Node(str(attributes.get("resource-id") or ""), names, kind, (x, y, x2, y2),
                        str(attributes.get("enabled", "true")).lower() != "false", text))
    return out


def named(node: Node, name: str) -> bool:
    return name in node.names


class Device:
    """Same verbs as `Browser`, aimed at an app on an Android device. `app_id` is the bundle id the app installs as;
    `serial` picks the device when several are attached."""

    def __init__(self, app_id: str, lang: str = "", serial: str = "", timeout: float = 20.0):
        self.app_id = app_id
        self.lang = lang
        self.serial = serial
        self.timeout = timeout
        self.video_dir: str | None = None
        self._recording: ScreenRecording | None = None
        self._name = ""
        self._began = 0.0
        self._screen = load_harness_module("ostler_qa_hierarchy")

    def start(self) -> None:
        for tool in ("adb", "maestro"):
            if shutil.which(tool) is None:
                raise BookError(f"a mobile book drives a device through {tool}, which is not on PATH")
        if self.serial:
            os.environ["ANDROID_SERIAL"] = self.serial
        if not android.ready(self.serial):
            raise BookError("a mobile book needs an Android device or emulator that adb reports as attached")

    def stop(self) -> None:
        self._screen.release_device()

    def adb(self, *args: str, timeout: float = 120) -> str:
        done = subprocess.run([*android.adb(self.serial), *args], capture_output=True, text=True, timeout=timeout, check=False)
        if done.returncode:
            raise BookError(f"adb {' '.join(args[:3])} exited {done.returncode}: {(done.stderr or done.stdout).strip()}")
        return done.stdout

    def launch(self) -> None:
        self.adb("shell", "monkey", "-p", self.app_id, "-c", "android.intent.category.LAUNCHER", "1")

    def restart(self) -> None:
        self.adb("shell", "am", "force-stop", self.app_id)
        self.launch()

    def clear(self) -> None:
        self.adb("shell", "pm", "clear", self.app_id)

    def forward(self, port: int) -> None:
        self.adb("forward", f"tcp:{port}", f"tcp:{port}")

    def begin(self, name: str) -> None:
        """Starts a recording named `name`, when a video directory is set."""
        if self.video_dir is None:
            return
        self._name = name
        self._recording = ScreenRecording(Path(self.video_dir), re.sub(r"[^A-Za-z0-9_.-]+", "-", name), str(os.getpid()),
                                          lambda: int((time.monotonic() - self._began) * 1000), self.serial)
        self._began = time.monotonic()
        self._recording.start()
        if self._recording.error:
            raise BookError(f"the screen recording failed to start: {self._recording.error}")

    def offset(self) -> float | None:
        """Seconds from the start of the recording to now, or None when nothing is recording."""
        return time.monotonic() - self._began if self._recording is not None else None

    def finish(self, keep: bool) -> str:
        """Ends the recording. The video is kept as `<video_dir>/<name>.mp4` and its path returned, or deleted."""
        recording, self._recording = self._recording, None
        if recording is None:
            return ""
        recording.stop_event.set()
        assert recording.thread is not None
        recording.thread.join(timeout=45 * (len(recording.remote_segments) + 2))
        if recording.error:
            raise BookError(f"the screen recording failed: {recording.error}")
        paths = [path for path, _start, _end in recording.segments]
        kept = ""
        if keep and paths:
            kept = str(Path(self.video_dir or ".") / (re.sub(r"[^A-Za-z0-9_.-]+", "-", self._name) + ".mp4"))
            joined(paths, kept)
        for path in paths:
            path.unlink(missing_ok=True)
        return kept

    def nodes(self) -> list[Node]:
        for _attempt in range(2):
            try:
                return nodes_of(self._screen.resident_reader(self.timeout))
            except RuntimeError as unread:
                if "Failed to inspect UI" not in str(unread):
                    raise
        return nodes_of(self._screen.resident_reader(self.timeout))

    def find(self, component: Component, within: Component | None = None) -> Node | None:
        """The first node a user would call this component, inside `within` when given."""
        screen = self.nodes()
        scope = screen
        if within is not None:
            root = self.match(screen, within)
            scope = [n for n in screen if root is not None and n.inside(root)] if root is not None else []
        return self.match(scope, component)

    def match(self, screen: list[Node], component: Component) -> Node | None:
        if component.id is not None:
            return next((n for n in screen if n.id == component.id), None)
        assert component.label is not None
        name = component.label[self.lang]
        return next((n for n in screen if named(n, name) and self.plays(n, component)), None)

    @staticmethod
    def plays(node: Node, component: Component) -> bool:
        role = ROLES.get(component.kind)
        if role == "textbox":
            return node.kind == "EditText"
        if role == "button":
            return node.kind in ("Button", "ImageButton", "View")
        return True

    def await_node(self, component: Component, present: bool, within: Component | None = None) -> Node | None:
        deadline = time.monotonic() + self.timeout
        while True:
            found = self.find(component, within)
            if (found is not None) == present:
                return found
            if time.monotonic() > deadline:
                state = "appear" if present else "go away"
                raise BookError(f"{component.found_by(self.lang)} did not {state} on the screen")

    def locate(self, component: Component, within: Component | None = None) -> Node:
        found = self.await_node(component, True, within)
        assert found is not None
        return found

    def tap(self, node: Node) -> None:
        x, y = node.centre
        self.adb("shell", "input", "tap", str(x), str(y))

    def press(self, component: Component, within: Component | None = None) -> None:
        self.tap(self.locate(component, within))

    def fill(self, component: Component, value: str, within: Component | None = None) -> None:
        """Types `value` into a field. Text the device cannot type is a `CannotReach`."""
        if component.kind not in EDITS:
            raise BookError(f"{component.found_by(self.lang)} is not a field a device can type into")
        if not TYPED.fullmatch(value):
            raise CannotReach(f"{component.found_by(self.lang)} cannot be typed {value!r} from a keyboard command")
        before = self.value(component, within)
        kept = None
        for _attempt in range(3):
            self.type_into(component, value, within)
            now = self.value(component, within)
            if now == value:
                return
            if now == kept and value.startswith(now):
                self.type_into(component, before, within)
                raise CannotReach(cut_by_limit(component.found_by(self.lang), len(now), len(value)))
            kept = now
        raise BookError(f"{component.found_by(self.lang)} kept {kept!r} after being typed {value!r}")

    def type_into(self, component: Component, value: str, within: Component | None = None) -> None:
        self.tap(self.locate(component, within))
        self.adb("shell", "input", "keycombination", "113", "29")
        self.adb("shell", "input", "keyevent", "67")
        for start in range(0, len(value), CHUNK):
            self.adb("shell", "input", "text", shlex.quote(value[start:start + CHUNK].replace(" ", "%s")))
        self.dismiss_keyboard()

    def dismiss_keyboard(self) -> None:
        if "mInputShown=true" in self.adb("shell", "dumpsys", "input_method"):
            self.adb("shell", "input", "keyevent", "4")

    def text(self, component: Component, within: Component | None = None) -> str:
        found = self.locate(component, within)
        return found.text or found.names[0]

    def value(self, component: Component, within: Component | None = None) -> str:
        return self.locate(component, within).text

    def disabled(self, component: Component, within: Component | None = None) -> bool:
        return not self.locate(component, within).enabled

    def visible(self, component: Component, within: Component | None = None) -> bool:
        return self.find(component, within) is not None

    def wait_for(self, component: Component, state: str = "visible", within: Component | None = None) -> None:
        """Waits until the component is `visible` or `hidden`."""
        self.await_node(component, state in ("visible", "attached"), within)

    def await_first(self, *components: Component) -> Component:
        """Waits until one of `components` is visible and returns it."""
        deadline = time.monotonic() + self.timeout
        while True:
            on_screen = self.nodes()
            for component in components:
                if self.match(on_screen, component) is not None:
                    return component
            if time.monotonic() > deadline:
                raise BookError("none of " + ", ".join(c.found_by(self.lang) for c in components) + " appeared on the screen")

    def heard(self, prefixes: tuple[str, ...]) -> str | None:
        """The first name on the screen that starts with one of `prefixes`, such as a snackbar's words."""
        return next((name for node in self.nodes() for name in node.names if name.startswith(prefixes)), None)

    def await_heard(self, prefixes: tuple[str, ...], present: bool = True) -> str | None:
        deadline = time.monotonic() + self.timeout
        while True:
            heard = self.heard(prefixes)
            if (heard is not None) == present:
                return heard
            if time.monotonic() > deadline:
                raise BookError(f"nothing starting {' or '.join(map(repr, prefixes))} {'appeared' if present else 'went away'} on the screen")

    def await_value(self, component: Component, wanted: str, within: Component | None = None) -> None:
        deadline = time.monotonic() + self.timeout
        while self.value(component, within) != wanted:
            if time.monotonic() > deadline:
                raise BookError(f"{component.found_by(self.lang)} did not come to hold {wanted!r}")

    def wrong_labels(self, lang: str, screens: tuple[type[Screen], ...]) -> str | None:
        """Every visible component whose name on the device is not its label in `lang`, one per line, or None."""
        wrong = []
        for screen in screens:
            on_screen = self.nodes()
            for component in screen.components():
                if component.label is None or component.per_row or component.kind == "spinner" or component.id is None:
                    continue
                node = self.match(on_screen, component)
                if node is not None and component.label[lang] not in node.names:
                    wrong.append(f"{screen.__name__}.{component.found_by(lang)}: saw {node.names!r}, wanted {component.label[lang]!r}")
        return "\n".join(wrong) or None

    def watching(self, prefix: str) -> None:
        return None

    def taken(self) -> list[Any]:
        return []


def joined(paths: list[Path], target: str) -> None:
    """One video out of the segments the device wrote, in order."""
    if len(paths) == 1:
        os.replace(paths[0], target)
        return
    listing = Path(target + ".list")
    listing.write_text("".join(f"file {shlex.quote(str(path))}\n" for path in paths))
    try:
        done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", target],
                              capture_output=True, text=True, timeout=120, check=False)
    finally:
        listing.unlink(missing_ok=True)
    if done.returncode:
        raise BookError(f"ffmpeg could not join the recording segments: {done.stderr.strip()}")
