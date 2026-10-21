"""The view-hierarchy scan a device screen is vetted from."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ostler_qa_elements import name_pattern
from ostler_qa_settle import ANNOUNCED_ROLES, Reading

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

CLASS_ROLES = {
    "button": "button",
    "imagebutton": "button",
    "checkbox": "checkbox",
    "checkbutton": "checkbox",
    "radiobutton": "radio",
    "switch": "switch",
    "edittext": "textbox",
    "textfield": "textbox",
    "securetextfield": "textbox",
    "searchview": "search",
    "searchfield": "search",
    "imageview": "img",
    "image": "img",
    "listview": "list",
    "recyclerview": "list",
    "collectionview": "list",
    "table": "list",
    "gridview": "list",
    "scrollview": "region",
    "nestedscrollview": "region",
    "horizontalscrollview": "region",
    "toolbar": "banner",
    "navigationbar": "navigation",
    "tabwidget": "navigation",
    "tablayout": "navigation",
    "tabbar": "navigation",
    "bottomnavigationview": "navigation",
    "alertdialoglayout": "dialog",
    "alert": "dialog",
    "webview": "region",
    "progressbar": "progressbar",
    "activityindicator": "progressbar",
    "progressindicator": "progressbar",
}

SETTLE_NAME_ATTRIBUTES = ("accessibilityText", "content-desc", "text", "hintText")

NAME_ATTRIBUTES = ("resource-id", "accessibilityText", "content-desc", "text", "hintText")


def role_for(class_name: str) -> str:
    """The role a widget class implies, or `""` when it implies none."""
    simple = class_name.rsplit(".", 1)[-1]
    if simple.startswith("XCUIElementType"):
        simple = simple[len("XCUIElementType") :]
    return CLASS_ROLES.get(simple.lower(), "")


def selectors_for(attributes: dict[str, str]) -> list[str]:
    """Every spelling that could name this element, deduplicated, in book-likeliest order."""
    found: list[str] = []
    for key in NAME_ATTRIBUTES:
        value = (attributes.get(key) or "").strip()
        if not value:
            continue
        for spelling in (value, value.split(":id/")[-1] if ":id/" in value else ""):
            if spelling and spelling not in found:
                found.append(spelling)
    return found


def accessible_name(attributes: dict[str, str]) -> str:
    """The name a screen reader announces for a node: its first non-empty name attribute, or empty when it has none."""
    return next(
        (value for key in SETTLE_NAME_ATTRIBUTES if (value := str(attributes.get(key) or "").strip())),
        "",
    )


def _element(attributes: dict[str, str], bounds: str) -> list[dict[str, Any]]:
    """One hierarchy node as zero or more scan elements — one per spelling that names it, each carrying the name the node announces."""
    match = BOUNDS.match(bounds)
    if match is None:
        return []
    x, y, x2, y2 = (int(part) for part in match.groups())
    if x2 <= x or y2 <= y:
        return []
    box = {"x": float(x), "y": float(y), "width": float(x2 - x), "height": float(y2 - y)}
    class_name = attributes.get("class") or attributes.get("type") or ""
    role = role_for(class_name)
    selectors = selectors_for(attributes) or [class_name.rsplit(".", 1)[-1] or "node"]
    name = accessible_name(attributes)
    return [
        {"selector": selector, "tag": class_name, "role": role, "ownRole": role, "name": name, "bbox": dict(box)}
        for selector in selectors
    ]


def _run(command: list[str], *, timeout: float) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, built from the constants above
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} exited {done.returncode}: {(done.stderr or done.stdout).strip()}"
        )
    return done.stdout


def maestro_elements(*, udid: str = "", timeout: float = 120.0) -> list[dict[str, Any]]:
    """The screen's elements from `maestro hierarchy` — the default source, both platforms."""
    if shutil.which("maestro") is None:
        raise RuntimeError("the maestro CLI is not installed on this machine")
    command = ["maestro"] + (["--device", udid] if udid else []) + ["hierarchy"]
    return parse_maestro(_run(command, timeout=timeout))


def parse_maestro(raw: str) -> list[dict[str, Any]]:
    """Elements from `maestro hierarchy` output, banner and all."""
    start = raw.find("{")
    if start < 0:
        raise ValueError(f"maestro hierarchy printed no JSON object: {raw.strip()[:200]!r}")
    elements: list[dict[str, Any]] = []
    stack = [json.loads(raw[start:])]
    while stack:
        node = stack.pop()
        attributes = node.get("attributes") or {}
        elements.extend(_element(attributes, attributes.get("bounds") or ""))
        stack.extend(reversed(node.get("children") or []))
    return elements


@dataclass(frozen=True)
class DeviceNode:
    """What a settle reads of one drawn hierarchy node: its role, the names it answers to, and its states when the hierarchy reports them."""

    role: str
    names: tuple[str, ...]
    enabled: bool | None
    checked: bool | None
    selected: bool | None


def _flag(node: Mapping[str, Any], attributes: Mapping[str, Any], key: str) -> bool | None:
    """A node's boolean state, from its own field, else from the attribute string, else unknown."""
    own = node.get(key)
    if isinstance(own, bool):
        return own
    text = str(attributes.get(key) or "").strip().lower()
    return {"true": True, "false": False}.get(text)


def parse_device_nodes(raw: str) -> list[DeviceNode]:
    """The drawn nodes of `maestro hierarchy` output, banner and all."""
    start = raw.find("{")
    if start < 0:
        raise ValueError(f"maestro hierarchy printed no JSON object: {raw.strip()[:200]!r}")
    nodes: list[DeviceNode] = []
    stack = [json.loads(raw[start:])]
    while stack:
        node = stack.pop()
        attributes = node.get("attributes") or {}
        stack.extend(reversed(node.get("children") or []))
        match = BOUNDS.match(attributes.get("bounds") or "")
        if match is None:
            continue
        x, y, x2, y2 = (int(part) for part in match.groups())
        if x2 <= x or y2 <= y:
            continue
        names = tuple(
            value for key in SETTLE_NAME_ATTRIBUTES if (value := str(attributes.get(key) or "").strip())
        )
        class_name = attributes.get("class") or attributes.get("type") or ""
        nodes.append(DeviceNode(
            role_for(class_name), names,
            _flag(node, attributes, "enabled"), _flag(node, attributes, "checked"),
            _flag(node, attributes, "selected"),
        ))
    return nodes


def _named(node: DeviceNode, role: str, name: str) -> bool:
    """Whether the node answers to the book's *name*: announced roles by the text they contain, the rest by the words whole."""
    if role in ANNOUNCED_ROLES:
        return any(name.casefold() in found.casefold() for found in node.names)
    pattern = name_pattern(name)
    return any(pattern.match(found) for found in node.names)


class DeviceReading:
    """One view hierarchy, asked whether a perceivable is drawn on it."""

    def __init__(self, nodes: list[DeviceNode]) -> None:
        self._nodes = nodes

    def shown(self, perceivable: Mapping[str, Any]) -> bool:
        role, name = str(perceivable["role"]), str(perceivable["name"])
        announced = role in ANNOUNCED_ROLES
        return any(
            _named(node, role, name)
            and (announced or not node.role or node.role == role)
            and (not perceivable.get("disabled") or node.enabled is False)
            and (not perceivable.get("checked") or node.checked is True)
            and (not perceivable.get("selected") or node.selected is True)
            for node in self._nodes
        )


def _maestro_hierarchy(timeout: float) -> str:
    if shutil.which("maestro") is None:
        raise RuntimeError("the maestro CLI is not installed on this machine")
    return _run(["maestro", "hierarchy"], timeout=timeout)


class DeviceScreen:
    """The device behind `maestro hierarchy`, read one hierarchy at a time."""

    def __init__(self, reader: Callable[[float], str] = _maestro_hierarchy) -> None:
        self._reader = reader

    def read(self, within: float) -> Reading | None:
        try:
            raw = self._reader(within)
        except subprocess.TimeoutExpired:
            return None
        return DeviceReading(parse_device_nodes(raw))

    def pause(self, seconds: float) -> None:
        time.sleep(seconds)


def uiautomator_elements(*, udid: str = "", timeout: float = 120.0) -> list[dict[str, Any]]:
    """The screen's elements from `uiautomator dump` — Android, where Maestro does not reach."""
    if shutil.which("adb") is None:
        raise RuntimeError("the adb CLI is not installed on this machine")
    adb = ["adb"] + (["-s", udid] if udid else [])
    remote = "/sdcard/ostler-vet-hierarchy.xml"
    _run([*adb, "shell", "uiautomator", "dump", remote], timeout=timeout)
    return parse_uiautomator(_run([*adb, "exec-out", "cat", remote], timeout=timeout))


def parse_uiautomator(raw: str) -> list[dict[str, Any]]:
    """Elements from a `uiautomator dump` XML document."""
    root = ET.fromstring(raw.strip())  # noqa: S314 - a local device's own dump
    elements: list[dict[str, Any]] = []
    for node in root.iter("node"):
        elements.extend(_element(dict(node.attrib), node.attrib.get("bounds", "")))
    return elements


def frame_for(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """The screen the elements were measured against."""
    width = max((e["bbox"]["x"] + e["bbox"]["width"] for e in elements), default=0.0)
    height = max((e["bbox"]["y"] + e["bbox"]["height"] for e in elements), default=0.0)
    size = {"width": float(width), "height": float(height)}
    return {"viewport": dict(size), "document": dict(size)}


def scan(*, source: str = "maestro", udid: str = "") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The frame and the raw elements of the screen currently on the device."""
    readers = {"maestro": maestro_elements, "uiautomator": uiautomator_elements}
    if source not in readers:
        raise ValueError(f"unknown hierarchy source {source!r}; expected one of {sorted(readers)}")
    elements = readers[source](udid=udid)
    if not elements:
        raise RuntimeError(
            f"the {source} hierarchy of the current screen has no bounded element — is an app "
            "in the foreground on the device?"
        )
    return frame_for(elements), elements


def screenshot(path: Path, *, udid: str = "", timeout: float = 120.0) -> Path:
    """Photograph the device screen, whichever device is attached."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("adb") is not None:
        command = ["adb"] + (["-s", udid] if udid else []) + ["exec-out", "screencap", "-p"]
        done = subprocess.run(  # noqa: S603 - fixed argv
            command, capture_output=True, timeout=timeout, check=False
        )
        if done.returncode == 0 and done.stdout:
            path.write_bytes(done.stdout)
            return path
    if shutil.which("xcrun") is not None:
        _run(
            ["xcrun", "simctl", "io", udid or "booted", "screenshot", str(path)], timeout=timeout
        )
        return path
    raise RuntimeError(
        "no device screenshot tool is installed: adb (Android) or xcrun simctl (iOS simulator)"
    )
