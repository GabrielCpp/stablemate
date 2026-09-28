"""The verifiers that observe documents and bodies: a path into parsed JSON, a count of what it selects, and what a body must not carry."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sized
from dataclasses import dataclass

from ostler_qa_paths import JsonValue, Resolved, is_projection, resolve_path, scalar_equal
from ostler_qa_verdicts import Args, Verdict, json_value, recorded, scalar_arg, str_arg, verdict


@dataclass(frozen=True)
class DocumentReading:
    """What a check reads, whether the file its `file=` names was there to read, and why it could not be parsed when it could not."""

    present: bool
    document: JsonValue
    unreadable: str | None = None

    def resolve(self, path: str) -> Resolved:
        """Walk `path` into the document, which resolves nothing when it could not be read as JSON."""
        if self.unreadable is not None:
            return Resolved(False)
        return resolve_path(self.document, path)


def _named(observed: object, args: Args) -> tuple[bool, object]:
    """The file a check's `file=` names in a working directory and whether it is there, or what was observed when it names none."""
    if "file" not in args:
        return True, observed
    if not isinstance(observed, Mapping):
        raise TypeError(f"`file=` reads a working directory, got {type(observed).__name__}")
    name = args["file"]
    return name in observed, observed.get(name)


def read_document(observed: object, args: Args) -> DocumentReading:
    """What a check reads, as JSON: the file its `file=` names in a working directory, or what was observed when it names none."""
    present, named = _named(observed, args)
    try:
        return DocumentReading(present=present, document=json_value(named))
    except ValueError as exc:
        return DocumentReading(present=present, document=None, unreadable=str(exc))


def _countable(value: object) -> JsonValue:
    """*value* as JSON a count reads, where a collection of anything keeps its length."""
    if isinstance(value, Sized) and isinstance(value, Iterable) and not isinstance(value, Mapping | str):
        return [recorded(item) for item in value]
    return json_value(value)


def read_countable(observed: object, args: Args) -> DocumentReading:
    """The document a count resolves its subject in, parsed when it is a response."""
    present, named = _named(observed, args)
    if not present:
        return DocumentReading(present=False, document=None)
    reader = getattr(named, "json", None)
    try:
        return DocumentReading(present=True, document=_countable(reader() if callable(reader) else named))
    except ValueError as exc:
        return DocumentReading(present=True, document=None, unreadable=str(exc))


def _matchable(value: object) -> str:
    """*value* rendered the way a `json_path(matches=...)` pattern is written against."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


def verify_json_path(reading: DocumentReading, args: Args) -> Verdict:
    if not reading.present:
        return verdict(False, {"file": args["file"], "present": False}, {"file": "present"})
    hit = reading.resolve(str_arg(args, "path"))
    if "absent" in args:
        want_absent = bool(args["absent"])
        return verdict(hit.found is not want_absent, {"present": hit.found}, {"present": not want_absent})
    if not hit.found:
        return verdict(False, {"present": False}, {"path": str_arg(args, "path")})
    value = hit.value
    if is_projection(str_arg(args, "path")) and isinstance(value, list):
        if len(value) != 1:
            return verdict(False, {"selected": value}, {"selected": "exactly one"})
        value = value[0]
    if "equals" in args:
        return verdict(scalar_equal(value, scalar_arg(args, "equals")), value, args["equals"])
    if "matches" in args:
        return verdict(re.search(str_arg(args, "matches"), _matchable(value)) is not None, value,
                        f"~ {str_arg(args, 'matches')}")
    return verdict(False, value, "equals=, matches= or absent=true — presence asserts nothing")


def verify_count(reading: DocumentReading, args: Args) -> Verdict:
    """How many of `subject` there are — the subject resolved, not taken on trust."""
    if not reading.present:
        return verdict(False, {"file": args["file"], "present": False}, args["equals"])
    if reading.unreadable is not None:
        return verdict(
            False, {"subject": str_arg(args, "subject"), "countable": False, "reason": reading.unreadable}, args["equals"]
        )
    document = reading.document
    if isinstance(document, dict):
        hit = resolve_path(document, str_arg(args, "subject"))
        document = hit.value
        selected_nothing = is_projection(str_arg(args, "subject")) and document == []
        if not hit.found and not selected_nothing:
            return verdict(False, {"subject": str_arg(args, "subject"), "present": False}, args["equals"])
    if isinstance(document, bool) or not isinstance(document, int | list | dict):
        return verdict(False, {"subject": str_arg(args, "subject"), "countable": False}, args["equals"])
    found = document if isinstance(document, int) else len(document)
    return verdict(found == args["equals"], found, args["equals"])


@dataclass(frozen=True)
class BodyReading:
    """Everything the subject carries: a response's parsed body, its text when that does not parse, or the value itself, rendered when JSON cannot hold it."""

    document: JsonValue


def read_body(observed: object, args: Args) -> BodyReading:
    carried = observed
    reader = getattr(observed, "json", None)
    if callable(reader):
        try:
            carried = reader()
        except ValueError:
            carried = getattr(observed, "text", observed)
    try:
        return BodyReading(document=json_value(carried))
    except ValueError:
        return BodyReading(document=_rendered(carried))


def _rendered(document: object) -> str:
    """Everything the subject carries, as one string to search."""
    try:
        return json.dumps(document, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(document)


def verify_omits(reading: BodyReading, args: Args) -> Verdict:
    """What the subject must not carry — the one assertion the rest of the vocabulary cannot make."""
    document = reading.document
    if isinstance(document, dict):
        hit = resolve_path(document, str_arg(args, "subject"))
        if hit.found:
            document = hit.value
    haystack = document if isinstance(document, str) else _rendered(document)
    found: list[str] = []
    if "text" in args and str_arg(args, "text") in haystack:
        found.append(str_arg(args, "text"))
    if "matches" in args:
        hit = re.search(str_arg(args, "matches"), haystack)
        if hit is not None:
            found.append(hit.group(0))
    return verdict(not found, {"found": found}, {"found": []})
