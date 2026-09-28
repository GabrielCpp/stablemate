"""The claim verifiers: what each `verify:` kind observes, and the document reads they share."""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Mapping, Sized
from dataclasses import dataclass
from pathlib import Path

from ostler_qa_paths import JsonScalar, JsonValue, Resolved, is_projection, resolve_path, scalar_equal


_MISSING = object()


type CheckValue = str | int | float | bool | list[str]
type Args = Mapping[str, CheckValue]


def _str(args: Args, key: str) -> str:
    """The string a check's `key` argument holds, which the check's declaration types as one."""
    value = args[key]
    if not isinstance(value, str):
        raise TypeError(f"`{key}` must be a string, not {type(value).__name__}")
    return value


def _scalar(args: Args, key: str) -> JsonScalar:
    """The scalar a check's `key` argument holds, which the check's declaration types as one."""
    value = args[key]
    if isinstance(value, list):
        raise TypeError(f"`{key}` must be a scalar, not a list")
    return value


def _strings(args: Args, key: str) -> list[str]:
    """The strings a check's optional `key` argument lists, none when it is absent."""
    value = args.get(key, [])
    if not isinstance(value, list):
        raise TypeError(f"`{key}` must be a list of strings, not {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Verdict:
    """Whether a check passed, and the actual and expected values its assert record carries."""

    passed: bool
    actual: JsonValue
    expected: JsonValue


type Verifier = Callable[[object, Args], Verdict]


def _recorded_key(key: object) -> str:
    """*key* spelled the way `json.dumps` spells a dict key."""
    if isinstance(key, str):
        return key
    if key is None or isinstance(key, bool | int | float):
        return json.dumps(key)
    return str(key)


def _recorded(value: object) -> JsonValue:
    """*value* as the assert record writes it, which serializes with `default=str`."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [_recorded(item) for item in value]
    if isinstance(value, dict):
        return {_recorded_key(key): _recorded(item) for key, item in value.items()}
    return str(value)


def _verdict(passed: bool, actual: object, expected: object) -> Verdict:
    return Verdict(passed=passed, actual=_recorded(actual), expected=_recorded(expected))


def _verifier[R](read: Callable[[object, Args], R], judge: Callable[[R, Args], Verdict]) -> Verifier:
    """A verifier that parses the observation once with *read*, then judges only that reading."""

    def verify(observed: object, args: Args) -> Verdict:
        return judge(read(observed, args), args)

    return verify


@dataclass(frozen=True)
class HttpReading:
    """What a response answered: its status, its parsed body, and the route that answered."""

    status: int
    body: object
    route: str | None


def _read_response(observed: object, args: Args) -> HttpReading:
    """The status code, parsed body and route of whatever a scenario handed over as a response."""
    if isinstance(observed, int) and not isinstance(observed, bool):
        status: object = observed
    else:
        status = getattr(observed, "status", getattr(observed, "status_code", None))
    if not isinstance(status, int):
        raise TypeError(
            "http_status observes a response — pass the object qa.http returned (or its "
            f"integer status), not {type(observed).__name__}"
        )
    body: object = None
    reader = getattr(observed, "json", None)
    if callable(reader):
        try:
            body = reader()
        except ValueError:
            body = None
    url = getattr(observed, "url", None)
    if "path" in args and not isinstance(url, str):
        raise TypeError(
            "http_status(path=…) observes which request answered — pass the object "
            f"qa.http returned, not {type(observed).__name__}"
        )
    route = urllib.parse.urlsplit(url).path if isinstance(url, str) else None
    return HttpReading(status=status, body=body, route=route)


@dataclass(frozen=True)
class HeaderReading:
    """The headers a response carried, in the order it carried them."""

    headers: tuple[tuple[str, str], ...]


def _read_headers(observed: object, args: Args) -> HeaderReading:
    headers = getattr(observed, "headers", None)
    if callable(headers):
        headers = headers()
    if not isinstance(headers, Mapping):
        raise TypeError(
            "response_header observes the headers a response carried — pass the object "
            f"qa.http returned, not {type(observed).__name__}"
        )
    return HeaderReading(headers=tuple((str(key), str(value)) for key, value in headers.items()))


@dataclass(frozen=True)
class PairReading:
    """The two reads a differential check compares."""

    before: object
    after: object


def _read_pair(check: str) -> Callable[[object, Args], PairReading]:
    """A reader insisting on the before/after a differential check needs, rather than inferring it."""

    def read(observed: object, args: Args) -> PairReading:
        if isinstance(observed, tuple | list) and len(observed) == 2:
            return PairReading(before=observed[0], after=observed[1])
        raise TypeError(
            f"{check} observes a change — pass `(before, after)`, the two reads it compares, "
            f"not {type(observed).__name__}"
        )

    return read


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


@dataclass(frozen=True)
class FileReading:
    """The text of the one file a check names, or `None` when no file sits there."""

    text: str | None


def _read_file(observed: object, args: Args) -> FileReading:
    """The text of the file `subject` names in a working directory, as written."""
    subject = _str(args, "subject")
    texts = getattr(observed, "texts", None)
    if isinstance(texts, Mapping):
        text = texts.get(subject)
        return FileReading(text=text if isinstance(text, str) else None)
    if not isinstance(observed, Mapping):
        raise TypeError(f"a file is read from a working directory, got {type(observed).__name__}")
    value = dict(observed).get(subject, _MISSING)
    if value is _MISSING:
        return FileReading(text=None)
    return FileReading(text=value if isinstance(value, str) else json.dumps(value))


@dataclass(frozen=True)
class DocumentReading:
    """What a check reads, whether the file its `file=` names was there to read, and why it could not be parsed when it could not."""

    present: bool
    document: object
    unreadable: str | None = None


def _read_document(observed: object, args: Args) -> DocumentReading:
    """What a check reads: the file its `file=` names in a working directory, or what was observed when it names none."""
    if "file" not in args:
        return DocumentReading(present=True, document=observed)
    if not isinstance(observed, Mapping):
        raise TypeError(f"`file=` reads a working directory, got {type(observed).__name__}")
    name = args["file"]
    return DocumentReading(present=name in observed, document=observed.get(name))


def _read_countable(observed: object, args: Args) -> DocumentReading:
    """The document a count resolves its subject in, parsed when it is a response."""
    checked = _read_document(observed, args)
    reader = getattr(checked.document, "json", None)
    if not checked.present or not callable(reader):
        return checked
    try:
        return DocumentReading(present=True, document=reader())
    except ValueError as exc:
        return DocumentReading(present=True, document=None, unreadable=str(exc))


@dataclass(frozen=True)
class BodyReading:
    """Everything the subject carries: a response's parsed body, its text when that does not parse, or the value itself."""

    document: object


def _read_body(observed: object, args: Args) -> BodyReading:
    reader = getattr(observed, "json", None)
    if not callable(reader):
        return BodyReading(document=observed)
    try:
        return BodyReading(document=reader())
    except ValueError:
        return BodyReading(document=getattr(observed, "text", observed))


def json_value(value: object) -> JsonValue:
    """*value* as parsed JSON, refused with `ValueError` on anything JSON cannot hold."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {str(key): json_value(item) for key, item in value.items()}
    raise ValueError(f"not a JSON value: {type(value).__name__}")


def _resolve(document: object, path: str) -> Resolved:
    """Walk `path` into *document*, which resolves nothing when JSON cannot hold it."""
    try:
        parsed = json_value(document)
    except ValueError:
        return Resolved(False)
    return resolve_path(parsed, path)


def _read_tree_file(path: Path) -> JsonValue:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".json":
        return text
    try:
        return json_value(json.loads(text))
    except ValueError:
        return text


def _named_files(before: object, after: object, subject: object) -> tuple[object, object]:
    """A tree pair cut down to the one file `subject` names, present or not, so `created` and `removed` judge that file and nothing else in the directory."""
    if not isinstance(before, Tree) or not isinstance(after, Tree):
        return before, after
    return (
        {path: value for path, value in before.items() if path == subject},
        {path: value for path, value in after.items() if path == subject},
    )


def _named_file_or_tree(before: object, after: object, subject: object) -> tuple[object, object]:
    """A tree pair cut down to the file `subject` names when either side holds it, or left whole, which asserts more than any part of it."""
    if not isinstance(before, Tree) or not isinstance(after, Tree):
        return before, after
    if subject in before or subject in after:
        return before.get(str(subject)), after.get(str(subject))
    return before, after


def _leaves_by_path(value: object, prefix: str = "") -> dict[str, object]:
    """Every leaf of a JSON-ish value, keyed by its dotted path."""
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for key, item in value.items():
            out.update(_leaves_by_path(item, f"{prefix}.{key}" if prefix else str(key)))
        return out
    if isinstance(value, list):
        out = {}
        for index, item in enumerate(value):
            out.update(_leaves_by_path(item, f"{prefix}[{index}]"))
        return out
    return {prefix: value}


def _verify_http_status(reading: HttpReading, args: Args) -> Verdict:
    expected: dict[str, object] = {"code": args["code"]}
    actual: dict[str, object] = {"code": reading.status}
    passed = reading.status == args["code"]
    if "title" in args:
        found = reading.body.get("title") if isinstance(reading.body, dict) else None
        expected["title"], actual["title"] = args["title"], found
        passed = passed and found == args["title"]
    if "path" in args:
        expected["path"], actual["path"] = _str(args, "path"), reading.route
        passed = passed and reading.route == _str(args, "path")
    return _verdict(passed, actual, expected)


def _verify_response_header(reading: HeaderReading, args: Args) -> Verdict:
    wanted = str(_str(args, "name")).lower()
    value = next((v for k, v in reading.headers if k.lower() == wanted), None)
    actual = {_str(args, "name"): value}
    if value is None:
        return _verdict(False, actual, {_str(args, "name"): "present"})
    if "equals" in args:
        return _verdict(value == args["equals"], actual, {_str(args, "name"): args["equals"]})
    return _verdict(re.search(_str(args, "matches"), value) is not None, actual,
                    {_str(args, "name"): f"~ {_str(args, 'matches')}"})


def _matchable(value: object) -> str:
    """*value* rendered the way a `json_path(matches=...)` pattern is written against."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _verify_json_path(reading: DocumentReading, args: Args) -> Verdict:
    if not reading.present:
        return _verdict(False, {"file": args["file"], "present": False}, {"file": "present"})
    hit = _resolve(reading.document, _str(args, "path"))
    if "absent" in args:
        want_absent = bool(args["absent"])
        return _verdict(hit.found is not want_absent, {"present": hit.found}, {"present": not want_absent})
    if not hit.found:
        return _verdict(False, {"present": False}, {"path": _str(args, "path")})
    value = hit.value
    if is_projection(_str(args, "path")) and isinstance(value, list):
        if len(value) != 1:
            return _verdict(False, {"selected": value}, {"selected": "exactly one"})
        value = value[0]
    if "equals" in args:
        return _verdict(scalar_equal(value, _scalar(args, "equals")), value, args["equals"])
    if "matches" in args:
        return _verdict(re.search(_str(args, "matches"), _matchable(value)) is not None, value,
                        f"~ {_str(args, 'matches')}")
    return _verdict(False, value, "equals=, matches= or absent=true — presence asserts nothing")


def _verify_unchanged(reading: PairReading, args: Args) -> Verdict:
    before, after = _named_file_or_tree(reading.before, reading.after, args.get("subject"))
    allowed = set(_strings(args, "except_fields"))
    before_leaves, after_leaves = _leaves_by_path(before), _leaves_by_path(after)
    changed = sorted(
        {
            path
            for path in before_leaves.keys() | after_leaves.keys()
            if before_leaves.get(path, _MISSING) != after_leaves.get(path, _MISSING)
        }
        - allowed
    )
    return _verdict(not changed, {"changed": changed}, {"changed": []})


def _verify_keys_unchanged(reading: PairReading, args: Args) -> Verdict:
    before, after = _named_file_or_tree(reading.before, reading.after, args.get("subject"))
    gone = sorted(_leaves_by_path(before).keys() - _leaves_by_path(after).keys())
    added = sorted(_leaves_by_path(after).keys() - _leaves_by_path(before).keys())
    return _verdict(not gone and not added, {"removed": gone, "added": added}, {"removed": [], "added": []})


def _verify_count(reading: DocumentReading, args: Args) -> Verdict:
    """How many of `subject` there are — the subject resolved, not taken on trust."""
    if not reading.present:
        return _verdict(False, {"file": args["file"], "present": False}, args["equals"])
    if reading.unreadable is not None:
        return _verdict(
            False, {"subject": _str(args, "subject"), "countable": False, "reason": reading.unreadable}, args["equals"]
        )
    document = reading.document
    if isinstance(document, Mapping):
        hit = _resolve(document, _str(args, "subject"))
        document = hit.value
        selected_nothing = is_projection(_str(args, "subject")) and document == []
        if not hit.found and not selected_nothing:
            return _verdict(False, {"subject": _str(args, "subject"), "present": False}, args["equals"])
    if isinstance(document, bool | str) or not isinstance(document, int | Sized):
        return _verdict(False, {"subject": _str(args, "subject"), "countable": False}, args["equals"])
    found = document if isinstance(document, int) else len(document)
    return _verdict(found == args["equals"], found, args["equals"])


def _empty(value: object) -> bool:
    """Nothing there: `None`, or a sized thing with nothing in it."""
    return value is None or (isinstance(value, Sized) and len(value) == 0)


@dataclass(frozen=True)
class AbsenceReading:
    """Whether nothing is there, and what was there to see."""

    empty: bool
    seen: object


def _read_absence(observed: object, args: Args) -> AbsenceReading:
    """Nothing there. On a working directory, no file at the path `subject` names."""
    if isinstance(observed, Tree):
        subject = args.get("subject")
        return AbsenceReading(
            empty=subject not in observed,
            seen={path: value for path, value in observed.items() if path == subject},
        )
    return AbsenceReading(empty=_empty(observed), seen=observed)


def _verify_absent(reading: AbsenceReading, args: Args) -> Verdict:
    return _verdict(reading.empty, reading.seen, "absent")


def _verify_created(reading: PairReading, args: Args) -> Verdict:
    """Absent before the action, present after — both halves, or it proves nothing."""
    before, after = _named_files(reading.before, reading.after, args.get("subject"))
    was_absent, is_present = _empty(before), not _empty(after)
    return _verdict(
        was_absent and is_present,
        {"before": before, "after": after},
        {"before": "absent", "after": "present"},
    )


def _verify_removed(reading: PairReading, args: Args) -> Verdict:
    """Present before the action, absent after — the mirror of `created`, and for the mirror reason: absence afterwards alone passes on a subject that was never there."""
    before, after = _named_files(reading.before, reading.after, args.get("subject"))
    return _verdict(
        not _empty(before) and _empty(after),
        {"before": before, "after": after},
        {"before": "present", "after": "absent"},
    )


def _readings(observed: object) -> tuple[str, ...]:
    """Every spelling of an element's text the page can offer, rendered first."""
    readings: list[str] = []
    for reader in ("inner_text", "text_content"):
        read = getattr(observed, reader, None)
        if read is None:
            continue
        value = read()
        if value is not None and str(value) not in readings:
            readings.append(str(value))
    return tuple(readings)


@dataclass(frozen=True)
class VisibilityReading:
    """Whether the subject is shown, and every spelling of its text when the check reads text."""

    shown: bool
    readings: tuple[str, ...]


def _read_visibility(observed: object, args: Args) -> VisibilityReading:
    is_visible = getattr(observed, "is_visible", None)
    if callable(is_visible):
        shown = bool(is_visible())
        return VisibilityReading(shown=shown, readings=_readings(observed) if shown and "text" in args else ())
    readings = (str(observed),) if "text" in args and observed is not None else ()
    return VisibilityReading(shown=bool(observed), readings=readings)


def _verify_visible(reading: VisibilityReading, args: Args) -> Verdict:
    if "text" not in args:
        return _verdict(reading.shown, {"visible": reading.shown}, {"visible": True})
    text = reading.readings[0] if reading.readings else None
    contains = reading.shown and any(_str(args, "text") in each for each in reading.readings)
    return _verdict(contains, {"visible": reading.shown, "text": text}, {"visible": True, "text": _str(args, "text")})


@dataclass(frozen=True)
class ControlReading:
    """Whether the product will let a user act on this control."""

    enabled: bool


def _read_control(check: str) -> Callable[[object, Args], ControlReading]:
    def read(observed: object, args: Args) -> ControlReading:
        is_enabled = getattr(observed, "is_enabled", None)
        if not callable(is_enabled):
            raise TypeError(
                f"{check} observes whether a control accepts the action — pass the element "
                f"itself, not {type(observed).__name__}"
            )
        return ControlReading(enabled=bool(is_enabled()))

    return read


def _verify_actionable(reading: ControlReading, args: Args) -> Verdict:
    return _verdict(reading.enabled, {"actionable": reading.enabled}, {"actionable": True})


def _verify_inert(reading: ControlReading, args: Args) -> Verdict:
    return _verdict(not reading.enabled, {"actionable": reading.enabled}, {"actionable": False})


@dataclass(frozen=True)
class FocusReading:
    """Whether a real keypress reached the control, and whether the key `activates` names then clicked it, when it names one."""

    focused: bool
    activated: bool | None


def _read_focus(observed: object, args: Args) -> FocusReading:
    """Reachable by a real keypress, and — when `activates` names one — responsive to it."""
    focus = getattr(observed, "focus", None)
    if not callable(focus):
        raise TypeError(
            f"focusable observes a control through real keyboard focus — pass the element "
            f"itself, not {type(observed).__name__}"
        )
    focus()
    evaluate = getattr(observed, "evaluate")
    focused = bool(evaluate("el => el === document.activeElement"))
    if "activates" not in args:
        return FocusReading(focused=focused, activated=None)
    if not focused:
        return FocusReading(focused=False, activated=False)
    evaluate(
        "el => { el.__ostlerActivated = false; "
        "el.addEventListener('click', () => { el.__ostlerActivated = true; }, {once: true}); }"
    )
    getattr(observed, "page").keyboard.press(args["activates"])
    return FocusReading(focused=True, activated=bool(evaluate("el => el.__ostlerActivated === true")))


def _verify_focusable(reading: FocusReading, args: Args) -> Verdict:
    if reading.activated is None:
        return _verdict(reading.focused, {"focused": reading.focused}, {"focused": True})
    return _verdict(
        reading.focused and reading.activated,
        {"focused": reading.focused, "activated": reading.activated},
        {"focused": True, "activated": True},
    )


def _verify_persists(reading: PairReading, args: Args) -> Verdict:
    written, reread = reading.before, reading.after
    return _verdict(reread is not None and reread == written, reread, written)


@dataclass(frozen=True)
class SizeReading:
    """How many things were emitted."""

    size: int


def _read_size(observed: object, args: Args) -> SizeReading:
    if not isinstance(observed, Sized):
        raise TypeError(f"object of type '{type(observed).__name__}' has no len()")
    return SizeReading(size=len(observed))


def _verify_emitted(reading: SizeReading, args: Args) -> Verdict:
    if "count" in args:
        return _verdict(reading.size == args["count"], reading.size, args["count"])
    return _verdict(reading.size > 0, reading.size, "at least one")


def _verify_omits(reading: BodyReading, args: Args) -> Verdict:
    """What the subject must not carry — the one assertion the rest of the vocabulary cannot make."""
    document = reading.document
    if isinstance(document, Mapping):
        hit = _resolve(document, _str(args, "subject"))
        if hit.found:
            document = hit.value
    haystack = document if isinstance(document, str) else _rendered(document)
    found: list[str] = []
    if "text" in args and _str(args, "text") in haystack:
        found.append(_str(args, "text"))
    if "matches" in args:
        hit = re.search(_str(args, "matches"), haystack)
        if hit is not None:
            found.append(hit.group(0))
    return _verdict(not found, {"found": found}, {"found": []})


def _rendered(document: object) -> str:
    """Everything the subject carries, as one string to search."""
    try:
        return json.dumps(document, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(document)


@dataclass(frozen=True)
class ExitReading:
    """The code a process exited with."""

    code: int


def _read_exit(observed: object, args: Args) -> ExitReading:
    code = getattr(observed, "exit_code", None)
    if isinstance(code, bool) or not isinstance(code, int):
        raise TypeError(
            "exit_status observes a tool or maestro result (something with an exit_code), "
            f"got {type(observed).__name__}"
        )
    return ExitReading(code=code)


def _verify_exit_status(reading: ExitReading, args: Args) -> Verdict:
    """The process ended the way the book says it does."""
    return _verdict(reading.code == args["code"], reading.code, args["code"])


@dataclass(frozen=True)
class StreamReading:
    """What a command printed on one output stream."""

    printed: str


def _read_stream(stream: str) -> Callable[[object, Args], StreamReading]:
    def read(observed: object, args: Args) -> StreamReading:
        printed = getattr(observed, stream, None)
        if not isinstance(printed, str):
            raise TypeError(
                f"{stream} observes a tool result (something with a text {stream}), "
                f"got {type(observed).__name__}"
            )
        return StreamReading(printed=printed)

    return read


def _verify_printed(reading: StreamReading, args: Args) -> Verdict:
    """The command printed on the stream what the book says it prints."""
    missing = {key: args[key] for key in ("text", "matches") if key in args}
    if "text" in args and _str(args, "text") in reading.printed:
        missing.pop("text")
    if "matches" in args and re.search(_str(args, "matches"), reading.printed) is not None:
        missing.pop("matches")
    return _verdict(not missing, reading.printed, missing)


def _verify_contents(reading: FileReading, args: Args) -> Verdict:
    """The file `subject` names holds the text or the pattern the book says it holds."""
    text = reading.text
    if text is None:
        return _verdict(False, {"subject": _str(args, "subject"), "present": False}, {"subject": "present"})
    missing = {key: args[key] for key in ("text", "matches") if key in args}
    if "text" in args and _str(args, "text") in text:
        missing.pop("text")
    if "matches" in args and re.search(_str(args, "matches"), text) is not None:
        missing.pop("matches")
    return _verdict(not missing, text, missing)


def _verify_conflict_on_stale(reading: HttpReading, args: Args) -> Verdict:
    return _verdict(400 <= reading.status < 500, reading.status, "a refusal (4xx)")


VERIFIERS: dict[str, Verifier] = {
    "http_status": _verifier(_read_response, _verify_http_status),
    "response_header": _verifier(_read_headers, _verify_response_header),
    "json_path": _verifier(_read_document, _verify_json_path),
    "unchanged": _verifier(_read_pair("unchanged"), _verify_unchanged),
    "keys_unchanged": _verifier(_read_pair("keys_unchanged"), _verify_keys_unchanged),
    "count": _verifier(_read_countable, _verify_count),
    "absent": _verifier(_read_absence, _verify_absent),
    "created": _verifier(_read_pair("created"), _verify_created),
    "removed": _verifier(_read_pair("removed"), _verify_removed),
    "visible": _verifier(_read_visibility, _verify_visible),
    "actionable": _verifier(_read_control("actionable"), _verify_actionable),
    "inert": _verifier(_read_control("inert"), _verify_inert),
    "focusable": _verifier(_read_focus, _verify_focusable),
    "persists": _verifier(_read_pair("persists"), _verify_persists),
    "emitted": _verifier(_read_size, _verify_emitted),
    "omits": _verifier(_read_body, _verify_omits),
    "exit_status": _verifier(_read_exit, _verify_exit_status),
    "stdout": _verifier(_read_stream("stdout"), _verify_printed),
    "stderr": _verifier(_read_stream("stderr"), _verify_printed),
    "contents": _verifier(_read_file, _verify_contents),
    "conflict_on_stale": _verifier(_read_response, _verify_conflict_on_stale),
}
