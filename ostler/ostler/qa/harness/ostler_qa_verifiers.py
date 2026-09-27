"""The claim verifiers: what each `verify:` kind observes, and the document reads they share."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sized
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MISSING = object()


def _observed_status(observed: Any) -> tuple[int, Any]:
    """The status code and parsed body of whatever a scenario handed over as a response."""
    if isinstance(observed, int) and not isinstance(observed, bool):
        return observed, None
    status = getattr(observed, "status", getattr(observed, "status_code", None))
    if not isinstance(status, int):
        raise TypeError(
            "http_status observes a response — pass the object qa.http returned (or its "
            f"integer status), not {type(observed).__name__}"
        )
    body: Any = None
    reader = getattr(observed, "json", None)
    if callable(reader):
        try:
            body = reader()
        except Exception:  # noqa: BLE001 — a non-JSON body is not a scenario defect
            body = None
    return status, body


def _pair(observed: Any, check: str) -> tuple[Any, Any]:
    """The before/after a differential check needs, insisted on rather than inferred."""
    if isinstance(observed, (tuple, list)) and len(observed) == 2:
        return observed[0], observed[1]
    raise TypeError(
        f"{check} observes a change — pass `(before, after)`, the two reads it compares, "
        f"not {type(observed).__name__}"
    )


type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class Tree(dict[str, JsonValue]):
    """Every file under one directory, keyed by its path relative to it: parsed JSON for a `.json`, text otherwise."""

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.texts: dict[str, str] = {}
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    name = path.relative_to(root).as_posix()
                    self.texts[name] = path.read_text(encoding="utf-8", errors="replace")
                    self[name] = _read_tree_file(path)


def _file_text(observed: Any, subject: str) -> str | None:
    """The text of the file `subject` names in a working directory, as written, or `None` when no file sits there."""
    texts = getattr(observed, "texts", None)
    if isinstance(texts, Mapping):
        text = texts.get(subject)
        return text if isinstance(text, str) else None
    if not isinstance(observed, Mapping):
        raise TypeError(f"a file is read from a working directory, got {type(observed).__name__}")
    if subject not in observed:
        return None
    value = observed[subject]
    return value if isinstance(value, str) else json.dumps(value)


@dataclass(frozen=True)
class _CheckedDocument:
    """What a check reads, and whether the file its `file=` names was there to read."""

    present: bool
    document: Any


def _checked_document(observed: Any, args: Mapping[str, Any]) -> _CheckedDocument:
    """What a check reads: the file its `file=` names in a working directory, or what was observed when it names none."""
    if "file" not in args:
        return _CheckedDocument(present=True, document=observed)
    if not isinstance(observed, Mapping):
        raise TypeError(f"`file=` reads a working directory, got {type(observed).__name__}")
    name = args["file"]
    return _CheckedDocument(present=name in observed, document=observed.get(name))


def _json_value(value: object) -> JsonValue:
    """*value* as parsed JSON, refused with `ValueError` on anything JSON cannot hold."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"not a JSON value: {type(value).__name__}")


def _read_tree_file(path: Path) -> JsonValue:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".json":
        return text
    try:
        return _json_value(json.loads(text))
    except ValueError:
        return text


def _named_files(before: Any, after: Any, subject: Any) -> tuple[Any, Any]:
    """A tree pair cut down to the one file `subject` names, present or not, so `created` and `removed` judge that file and nothing else in the directory."""
    if not isinstance(before, Tree) or not isinstance(after, Tree):
        return before, after
    return (
        {path: value for path, value in before.items() if path == subject},
        {path: value for path, value in after.items() if path == subject},
    )


def _named_file_or_tree(before: Any, after: Any, subject: Any) -> tuple[Any, Any]:
    """A tree pair cut down to the file `subject` names when either side holds it, or left whole, which asserts more than any part of it."""
    if not isinstance(before, Tree) or not isinstance(after, Tree):
        return before, after
    if subject in before or subject in after:
        return before.get(subject), after.get(subject)
    return before, after


def _paths(value: Any, prefix: str = "") -> dict[str, Any]:
    """Every leaf of a JSON-ish value, keyed by its dotted path."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            out.update(_paths(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        out = {}
        for index, item in enumerate(value):
            out.update(_paths(item, f"{prefix}[{index}]"))
        return out
    return {prefix: value}


class _Wild:
    """The `[*]` segment: every element of a list, every value of an object."""

    def __repr__(self) -> str:
        return "[*]"


WILD = _Wild()


@dataclass(frozen=True)
class Filter:
    """The `[?(@.key==value)]` segment: the elements whose `key` holds `value`."""

    key: str
    value: Any

    def __repr__(self) -> str:
        return f"[?(@.{self.key}=={json.dumps(self.value)})]"


PathStep = str | int | _Wild | Filter

_FILTER = re.compile(
    r"\[\?\(@\.(?P<key>[^=\s)]+)\s*==\s*"
    r"(?P<value>'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?|true|false|null)\s*\)\]"
)


def path_steps(path: str) -> list[PathStep]:
    """The segments of a path, in the one grammar every reader of a document path shares."""
    steps: list[PathStep] = []
    text = path.strip()
    if text.startswith("$"):
        text = text[1:]
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char == ".":
            pos += 1
            continue
        if char == "[":
            if text.startswith("[*]", pos):
                steps.append(WILD)
                pos += 3
                continue
            hit = _FILTER.match(text, pos)
            if hit is not None:
                steps.append(Filter(hit.group("key"), json.loads(hit.group("value").replace("'", '"'))))
                pos = hit.end()
                continue
            close = text.find("]", pos)
            if close == -1:
                raise ValueError(f"json path {path!r}: '[' at {pos} is never closed")
            inner = text[pos + 1 : close]
            steps.append(int(inner) if inner.isdigit() else inner)
            pos = close + 1
            continue
        nxt = len(text)
        for stop in (".", "["):
            found = text.find(stop, pos)
            if found != -1:
                nxt = min(nxt, found)
        steps.append(text[pos:nxt])
        pos = nxt
    return steps


def _step_into(current: Any, step: str | int) -> tuple[bool, Any]:
    if isinstance(current, Mapping):
        key = str(step) if isinstance(step, int) else step
        return (True, current[key]) if key in current else (False, None)
    if isinstance(current, (list, tuple)):
        if isinstance(step, int):
            index = step
        elif step.isdigit():
            index = int(step)
        else:
            return False, None
        return (True, current[index]) if index < len(current) else (False, None)
    return False, None


def _selected(current: Any, step: _Wild | Filter) -> list[Any]:
    if isinstance(current, Mapping):
        candidates = list(current.values())
    elif isinstance(current, (list, tuple)):
        candidates = list(current)
    else:
        return []
    if isinstance(step, _Wild):
        return candidates
    chosen = []
    for item in candidates:
        ok, held = resolve_path(item, step.key)
        if ok and _scalar_equal(held, step.value):
            chosen.append(item)
    return chosen


def resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """Walk `path` into `document`: whether it resolved, and to what."""
    steps = path_steps(path)
    current: Any = document
    projected = False
    for step in steps:
        if isinstance(step, (_Wild, Filter)):
            if projected:
                current = [item for element in current for item in _selected(element, step)]
            else:
                current = _selected(current, step)
                projected = True
            continue
        if projected:
            kept = []
            for element in current:
                ok, value = _step_into(element, step)
                if ok:
                    kept.append(value)
            current = kept
            continue
        ok, current = _step_into(current, step)
        if not ok:
            return False, None
    if projected:
        return bool(current), current
    return True, current


def _resolve_path(document: Any, path: str) -> tuple[bool, Any]:
    """`resolve_path`, under the name the verifiers grew up calling it."""
    return resolve_path(document, path)


def _is_projection(path: str) -> bool:
    return any(isinstance(step, (_Wild, Filter)) for step in path_steps(path))


def _verify_http_status(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, body = _observed_status(observed)
    expected: Any = {"code": args["code"]}
    actual: Any = {"code": status}
    passed = status == args["code"]
    if "title" in args:
        found = body.get("title") if isinstance(body, dict) else None
        expected["title"], actual["title"] = args["title"], found
        passed = passed and found == args["title"]
    if "path" in args:
        url = getattr(observed, "url", None)
        if not isinstance(url, str):
            raise TypeError(
                "http_status(path=…) observes which request answered — pass the object "
                f"qa.http returned, not {type(observed).__name__}"
            )
        route = urllib.parse.urlsplit(url).path
        expected["path"], actual["path"] = args["path"], route
        passed = passed and route == args["path"]
    return passed, actual, expected


def _verify_response_header(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    headers = getattr(observed, "headers", None)
    if callable(headers):
        headers = headers()
    if not isinstance(headers, Mapping):
        raise TypeError(
            "response_header observes the headers a response carried — pass the object "
            f"qa.http returned, not {type(observed).__name__}"
        )
    wanted = str(args["name"]).lower()
    value = next((str(v) for k, v in headers.items() if str(k).lower() == wanted), None)
    actual = {args["name"]: value}
    if value is None:
        return False, actual, {args["name"]: "present"}
    if "equals" in args:
        return value == args["equals"], actual, {args["name"]: args["equals"]}
    return (re.search(args["matches"], value) is not None, actual,
            {args["name"]: f"~ {args['matches']}"})


def _scalar_equal(observed: Any, expected: Any) -> bool:
    """`json_path(equals=)` against what the document holds, typed the way JSON types it."""
    if isinstance(expected, bool) or isinstance(observed, bool):
        return isinstance(observed, bool) and isinstance(expected, bool) and observed is expected
    if isinstance(expected, (int, float)):
        return isinstance(observed, (int, float)) and observed == expected
    if isinstance(expected, str):
        return isinstance(observed, str) and observed == expected
    return False


def _matchable(value: Any) -> str:
    """*value* rendered the way a `json_path(matches=...)` pattern is written against."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _verify_json_path(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    checked = _checked_document(observed, args)
    if not checked.present:
        return False, {"file": args["file"], "present": False}, {"file": "present"}
    document = checked.document
    resolved, value = _resolve_path(document, args["path"])
    if "absent" in args:
        want_absent = bool(args["absent"])
        return resolved is not want_absent, {"present": resolved}, {"present": not want_absent}
    if not resolved:
        return False, {"present": False}, {"path": args["path"]}
    if _is_projection(args["path"]):
        if len(value) != 1:
            return False, {"selected": value}, {"selected": "exactly one"}
        value = value[0]
    if "equals" in args:
        return _scalar_equal(value, args["equals"]), value, args["equals"]
    if "matches" in args:
        return (re.search(args["matches"], _matchable(value)) is not None, value,
                f"~ {args['matches']}")
    return False, value, "equals=, matches= or absent=true — presence asserts nothing"


def _verify_unchanged(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    before, after = _pair(observed, "unchanged")
    before, after = _named_file_or_tree(before, after, args.get("subject"))
    allowed = set(args.get("except_fields", []))
    before_paths, after_paths = _paths(before), _paths(after)
    changed = sorted(
        {
            path
            for path in before_paths.keys() | after_paths.keys()
            if before_paths.get(path, _MISSING) != after_paths.get(path, _MISSING)
        }
        - allowed
    )
    return not changed, {"changed": changed}, {"changed": []}


def _verify_keys_unchanged(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    before, after = _pair(observed, "keys_unchanged")
    before, after = _named_file_or_tree(before, after, args.get("subject"))
    gone = sorted(_paths(before).keys() - _paths(after).keys())
    added = sorted(_paths(after).keys() - _paths(before).keys())
    return not gone and not added, {"removed": gone, "added": added}, {"removed": [], "added": []}


def _verify_count(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """How many of `subject` there are — the subject resolved, not taken on trust."""
    checked = _checked_document(observed, args)
    if not checked.present:
        return False, {"file": args["file"], "present": False}, args["equals"]
    document = checked.document
    reader = getattr(document, "json", None)
    if callable(reader):
        try:
            document = reader()
        except ValueError as exc:
            return False, {"subject": args["subject"], "countable": False, "reason": str(exc)}, args["equals"]
    if isinstance(document, Mapping):
        resolved, document = _resolve_path(document, args["subject"])
        selected_nothing = _is_projection(args["subject"]) and document == []
        if not resolved and not selected_nothing:
            return False, {"subject": args["subject"], "present": False}, args["equals"]
    if isinstance(document, bool | str) or not isinstance(document, int | Sized):
        return False, {"subject": args["subject"], "countable": False}, args["equals"]
    found = document if isinstance(document, int) else len(document)
    return found == args["equals"], found, args["equals"]


def _empty(value: Any) -> bool:
    """Nothing there: `None`, or a sized thing with nothing in it."""
    return value is None or (hasattr(value, "__len__") and len(value) == 0)


def _verify_absent(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Nothing there. On a working directory, no file at the path `subject` names."""
    if isinstance(observed, Tree):
        subject = args.get("subject")
        return subject not in observed, {path: value for path, value in observed.items() if path == subject}, "absent"
    return _empty(observed), observed, "absent"


def _verify_created(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Absent before the action, present after — both halves, or it proves nothing."""
    before, after = _pair(observed, "created")
    before, after = _named_files(before, after, args.get("subject"))
    was_absent, is_present = _empty(before), not _empty(after)
    return (
        was_absent and is_present,
        {"before": before, "after": after},
        {"before": "absent", "after": "present"},
    )


def _verify_removed(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Present before the action, absent after — the mirror of `created`, and for the mirror reason: absence afterwards alone passes on a subject that was never there."""
    before, after = _pair(observed, "removed")
    before, after = _named_files(before, after, args.get("subject"))
    return (
        not _empty(before) and _empty(after),
        {"before": before, "after": after},
        {"before": "present", "after": "absent"},
    )


def _readings(observed: Any) -> list[str]:
    """Every spelling of an element's text the page can offer, rendered first."""
    readings: list[str] = []
    for reader in ("inner_text", "text_content"):
        read = getattr(observed, reader, None)
        if read is None:
            continue
        value = read()
        if value is not None and str(value) not in readings:
            readings.append(str(value))
    return readings


def _verify_visible(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    if hasattr(observed, "is_visible"):
        shown = bool(observed.is_visible())
        readings = _readings(observed) if shown and "text" in args else []
    else:
        shown = bool(observed)
        readings = [str(observed)] if "text" in args and observed is not None else []
    if "text" not in args:
        return shown, {"visible": shown}, {"visible": True}
    text = readings[0] if readings else None
    contains = shown and any(args["text"] in reading for reading in readings)
    return contains, {"visible": shown, "text": text}, {"visible": True, "text": args["text"]}


def _enabled(observed: Any, check: str) -> bool:
    """Whether the product will let a user act on this control."""
    if not hasattr(observed, "is_enabled"):
        raise TypeError(
            f"{check} observes whether a control accepts the action — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    return bool(observed.is_enabled())


def _verify_actionable(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    usable = _enabled(observed, "actionable")
    return usable, {"actionable": usable}, {"actionable": True}


def _verify_inert(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    usable = _enabled(observed, "inert")
    return not usable, {"actionable": usable}, {"actionable": False}


def _verify_focusable(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """Reachable by a real keypress, and — when `activates` names one — responsive to it."""
    if not hasattr(observed, "focus"):
        raise TypeError(
            f"focusable observes a control through real keyboard focus — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    observed.focus()
    focused = bool(observed.evaluate("el => el === document.activeElement"))
    if "activates" not in args:
        return focused, {"focused": focused}, {"focused": True}
    if not focused:
        return False, {"focused": False, "activated": False}, {"focused": True, "activated": True}
    observed.evaluate(
        "el => { el.__ostlerActivated = false; "
        "el.addEventListener('click', () => { el.__ostlerActivated = true; }, {once: true}); }"
    )
    observed.page.keyboard.press(args["activates"])
    activated = bool(observed.evaluate("el => el.__ostlerActivated === true"))
    return (
        activated,
        {"focused": True, "activated": activated},
        {"focused": True, "activated": True},
    )


def _verify_persists(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    written, reread = _pair(observed, "persists")
    return reread is not None and reread == written, reread, written


def _verify_emitted(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    found = len(observed)
    if "count" in args:
        return found == args["count"], found, args["count"]
    return found > 0, found, "at least one"


def _verify_omits(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """What the subject must not carry — the one assertion the rest of the vocabulary cannot make."""
    document = observed
    reader = getattr(document, "json", None)
    if callable(reader):
        try:
            document = reader()
        except Exception:  # noqa: BLE001 — a non-JSON body is still searchable as text
            document = getattr(observed, "text", observed)
    if isinstance(document, Mapping):
        resolved, value = _resolve_path(document, args["subject"])
        if resolved:
            document = value
    haystack = document if isinstance(document, str) else _rendered(document)
    found: list[str] = []
    if "text" in args and args["text"] in haystack:
        found.append(args["text"])
    if "matches" in args:
        hit = re.search(args["matches"], haystack)
        if hit is not None:
            found.append(hit.group(0))
    return not found, {"found": found}, {"found": []}


def _rendered(document: Any) -> str:
    """Everything the subject carries, as one string to search."""
    try:
        return json.dumps(document, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(document)


def _verify_exit_status(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """The process ended the way the book says it does."""
    code = getattr(observed, "exit_code", None)
    if isinstance(code, bool) or not isinstance(code, int):
        raise TypeError(
            "exit_status observes a tool or maestro result (something with an exit_code), "
            f"got {type(observed).__name__}"
        )
    return code == args["code"], code, args["code"]



def _stream_verifier(stream: str) -> Callable[[Any, Mapping[str, Any]], tuple[bool, Any, Any]]:
    """A verifier reading one output stream of a tool result for the text or the pattern the book names."""

    def verify(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
        printed = getattr(observed, stream, None)
        if not isinstance(printed, str):
            raise TypeError(
                f"{stream} observes a tool result (something with a text {stream}), "
                f"got {type(observed).__name__}"
            )
        missing = {key: args[key] for key in ("text", "matches") if key in args}
        if "text" in args and args["text"] in printed:
            missing.pop("text")
        if "matches" in args and re.search(args["matches"], printed) is not None:
            missing.pop("matches")
        return not missing, printed, missing

    verify.__doc__ = f"The command printed on {stream} what the book says it prints."
    return verify

def _verify_contents(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    """The file `subject` names holds the text or the pattern the book says it holds."""
    text = _file_text(observed, args["subject"])
    if text is None:
        return False, {"subject": args["subject"], "present": False}, {"subject": "present"}
    missing = {key: args[key] for key in ("text", "matches") if key in args}
    if "text" in args and args["text"] in text:
        missing.pop("text")
    if "matches" in args and re.search(args["matches"], text) is not None:
        missing.pop("matches")
    return not missing, text, missing


def _verify_conflict_on_stale(observed: Any, args: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    status, _ = _observed_status(observed)
    return 400 <= status < 500, status, "a refusal (4xx)"


VERIFIERS: dict[str, Callable[[Any, Mapping[str, Any]], tuple[bool, Any, Any]]] = {
    "http_status": _verify_http_status,
    "response_header": _verify_response_header,
    "json_path": _verify_json_path,
    "unchanged": _verify_unchanged,
    "keys_unchanged": _verify_keys_unchanged,
    "count": _verify_count,
    "absent": _verify_absent,
    "created": _verify_created,
    "removed": _verify_removed,
    "visible": _verify_visible,
    "actionable": _verify_actionable,
    "inert": _verify_inert,
    "focusable": _verify_focusable,
    "persists": _verify_persists,
    "emitted": _verify_emitted,
    "omits": _verify_omits,
    "exit_status": _verify_exit_status,
    "stdout": _stream_verifier("stdout"),
    "stderr": _stream_verifier("stderr"),
    "contents": _verify_contents,
    "conflict_on_stale": _verify_conflict_on_stale,
}
