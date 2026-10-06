"""Paste and drop: the two triggers that hand a control data instead of a press.

A browser fires them with a `DataTransfer` the page reads in its handler, so each one is
dispatched on the element itself with that payload, the way the user's clipboard or file
manager would hand it over.
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

_PASTE = """(element, items) => {
    const data = new DataTransfer();
    for (const [type, value] of items) data.setData(type, value);
    element.focus();
    element.dispatchEvent(new ClipboardEvent("paste", {clipboardData: data, bubbles: true, cancelable: true}));
}"""

_DROP = """(element, file) => {
    const bytes = Uint8Array.from(atob(file.content), (c) => c.charCodeAt(0));
    const data = new DataTransfer();
    data.items.add(new File([bytes], file.name, {type: file.type}));
    for (const type of ["dragenter", "dragover", "drop"]) {
        element.dispatchEvent(new DragEvent(type, {dataTransfer: data, bubbles: true, cancelable: true}));
    }
}"""


def paste(locator: Any, *, text: str | None = None, html: str | None = None) -> None:
    """Paste *text*, *html* or both into *locator*, as a clipboard holding those types would."""
    items = [(kind, value) for kind, value in (("text/plain", text), ("text/html", html)) if value is not None]
    if not items:
        raise ValueError("paste needs the text or the html the clipboard holds")
    locator.evaluate(_PASTE, items)


def drop(locator: Any, path: Path) -> None:
    """Drop the file at *path* on *locator*, as a file manager's drag would."""
    if not path.is_file():
        raise FileNotFoundError(f"drop names {str(path)!r}, which is no file in this checkout")
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    content = base64.b64encode(path.read_bytes()).decode("ascii")
    locator.evaluate(_DROP, {"name": path.name, "type": kind, "content": content})
