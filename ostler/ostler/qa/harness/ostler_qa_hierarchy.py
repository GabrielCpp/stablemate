"""The view-hierarchy scan a device screen is vetted from.

`ostler_qa_scan` gives a browser page its regions from the DOM. Everything downstream of
that scan — `merge_rects`, the layout digest, `placement:`, the vet report — is already
platform-agnostic: it consumes a list of `{selector, tag, role, bbox}` dicts and a frame.
What a phone lacked was the source of those dicts, so `qa.vet` refused a `maestro` target.

This is that source. It shells out to the tools the mobile stack already has — `maestro
hierarchy` for both platforms, `uiautomator dump` for the places Maestro does not reach on
Android — and translates their view hierarchy into the same element shape. Like every other
harness module it is stdlib-only and never imports ostler.

Two facts here were measured against a live emulator rather than assumed, because both
would have failed silently:

- `maestro hierarchy` prints a `Running on <device>` banner on **stdout** before the JSON,
  so the payload starts at the first `{`, not at byte zero.
- neither the root node nor its only child carries `bounds`, so the screen size cannot be
  read off the root. The viewport is the maximum extent over every bounded node — 1080x2400
  on the probe, exactly what `adb shell wm size` reports.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

#: `[x,y][x2,y2]`, the one bounds spelling both Android sources use.
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

#: A widget class (the last dotted segment) to the role vocabulary the layout digest and
#: `placement:` already speak. Only names that really carry a role are here: a `TextView` or
#: a `FrameLayout` is a box, not a landmark, and guessing one would put a made-up region in
#: the digest. iOS classes arrive through Maestro as `XCUIElementType<Name>`, so the same
#: table serves both platforms once the prefix is stripped.
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
}

#: Attributes that name an element, most specific first. The book writes one of these
#: spellings in a component's `selector:`, and which one is a matter of what the app
#: exposes — so every spelling an element has becomes its own element sharing that
#: element's rect, and `merge_rects` folds them back into one region carrying all of them.
NAME_ATTRIBUTES = ("resource-id", "accessibilityText", "content-desc", "text", "hintText")


def role_for(class_name: str) -> str:
    """The role a widget class implies, or `""` when it implies none."""
    simple = class_name.rsplit(".", 1)[-1]
    if simple.startswith("XCUIElementType"):
        simple = simple[len("XCUIElementType") :]
    return CLASS_ROLES.get(simple.lower(), "")


def selectors_for(attributes: dict[str, str]) -> list[str]:
    """Every spelling that could name this element, deduplicated, in book-likeliest order.

    An Android `resource-id` arrives fully qualified (`com.example.app:id/submit`) and is
    written both ways in practice, so the short form after `:id/` is offered too. A selector
    is never invented from geometry: an element no attribute names contributes none, and the
    region it lands in is simply one no component can claim.
    """
    found: list[str] = []
    for key in NAME_ATTRIBUTES:
        value = (attributes.get(key) or "").strip()
        if not value:
            continue
        for spelling in (value, value.split(":id/")[-1] if ":id/" in value else ""):
            if spelling and spelling not in found:
                found.append(spelling)
    return found


def _element(attributes: dict[str, str], bounds: str) -> list[dict[str, Any]]:
    """One hierarchy node as zero or more scan elements — one per spelling that names it."""
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
    return [
        {"selector": selector, "tag": class_name, "role": role, "bbox": dict(box)}
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
    """Elements from `maestro hierarchy` output, banner and all.

    The banner is not on stderr and not behind a flag, so a parser that starts at byte zero
    raises `JSONDecodeError` on every device — which is why this is a named function with a
    test over captured output rather than a `json.loads` inside the adapter.
    """
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


def uiautomator_elements(*, udid: str = "", timeout: float = 120.0) -> list[dict[str, Any]]:
    """The screen's elements from `uiautomator dump` — Android, where Maestro does not reach.

    `uiautomator dump` writes to a path *on the device* and prints where it put it, so the
    file has to be pulled back before anything can read it.
    """
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
    """The screen the elements were measured against.

    Read off the elements rather than from a second CLI call, because the root node carries
    no bounds on either source. A device does not scroll its *screen*, so the document is the
    viewport — `horizontal-overflow` is a browser flag and stays absent here rather than
    being faked from a list item that happens to hang off the right edge.
    """
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
    """Photograph the device screen, whichever device is attached.

    Android first because `adb` answers in under a second; an iOS simulator through
    `xcrun simctl` otherwise. Neither is Maestro, which takes a screenshot only as a step
    inside a flow — and running a flow to photograph the state a flow just produced can move
    the app off that state.
    """
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
