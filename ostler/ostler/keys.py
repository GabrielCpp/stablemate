"""The keys a browser driver can press, so a book that names one the driver cannot press is refused before a lap reaches it."""

from __future__ import annotations

import re

_NAMED = frozenset({
    "Alt", "AltGraph", "AltLeft", "AltRight", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowUp",
    "AudioVolumeDown", "AudioVolumeMute", "AudioVolumeUp", "Backquote", "Backslash", "Backspace",
    "BracketLeft", "BracketRight", "CapsLock", "Clear", "Comma", "ContextMenu", "Control",
    "ControlLeft", "ControlOrMeta", "ControlRight", "Delete", "End", "Enter", "Equal", "Escape",
    "Home", "Insert", "MediaPlayPause", "MediaTrackNext", "MediaTrackPrevious", "Meta", "MetaLeft",
    "MetaRight", "Minus", "NumLock", "NumpadAdd", "NumpadDecimal", "NumpadDivide", "NumpadEnter",
    "NumpadMultiply", "NumpadSubtract", "PageDown", "PageUp", "Pause", "Period", "PrintScreen",
    "Quote", "ScrollLock", "Semicolon", "Shift", "ShiftLeft", "ShiftRight", "Slash", "Space", "Tab",
})

_NUMBERED = re.compile(r"Key[A-Z]|Digit[0-9]|Numpad[0-9]|F(?:[1-9]|1[0-2])")

_CHORD = re.compile(r"[+](?!$)")


def pressable(text: str) -> bool:
    """Whether *text* names a key or a chord such as `Shift+Tab` the driver can press."""
    return bool(text) and all(_key(part) for part in _CHORD.split(text))


def _key(part: str) -> bool:
    return part in _NAMED or bool(_NUMBERED.fullmatch(part)) or (len(part) == 1 and " " <= part <= "~")
