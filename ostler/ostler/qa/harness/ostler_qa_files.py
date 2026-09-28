"""The verifiers that observe files and trees: what a working directory holds, and what changed in it between two reads."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sized
from dataclasses import dataclass
from pathlib import Path

from ostler_qa_paths import JsonValue
from ostler_qa_verdicts import Args, Verdict, json_value, str_arg, strings_arg, verdict


_MISSING = object()


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


def _read_tree_file(path: Path) -> JsonValue:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix != ".json":
        return text
    try:
        return json_value(json.loads(text))
    except ValueError:
        return text


@dataclass(frozen=True)
class FileReading:
    """The text of the one file a check names, or `None` when no file sits there."""

    text: str | None


def read_file(observed: object, args: Args) -> FileReading:
    """The text of the file `subject` names in a working directory, as written."""
    subject = str_arg(args, "subject")
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


def verify_contents(reading: FileReading, args: Args) -> Verdict:
    """The file `subject` names holds the text or the pattern the book says it holds."""
    text = reading.text
    if text is None:
        return verdict(False, {"subject": str_arg(args, "subject"), "present": False}, {"subject": "present"})
    missing = {key: args[key] for key in ("text", "matches") if key in args}
    if "text" in args and str_arg(args, "text") in text:
        missing.pop("text")
    if "matches" in args and re.search(str_arg(args, "matches"), text) is not None:
        missing.pop("matches")
    return verdict(not missing, text, missing)


@dataclass(frozen=True)
class PairReading:
    """The two reads a differential check compares."""

    before: object
    after: object


def read_pair(check: str) -> Callable[[object, Args], PairReading]:
    """A reader insisting on the before/after a differential check needs, rather than inferring it."""

    def read(observed: object, args: Args) -> PairReading:
        if isinstance(observed, tuple | list) and len(observed) == 2:
            return PairReading(before=observed[0], after=observed[1])
        raise TypeError(
            f"{check} observes a change — pass `(before, after)`, the two reads it compares, "
            f"not {type(observed).__name__}"
        )

    return read


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


def verify_unchanged(reading: PairReading, args: Args) -> Verdict:
    before, after = _named_file_or_tree(reading.before, reading.after, args.get("subject"))
    allowed = set(strings_arg(args, "except_fields"))
    before_leaves, after_leaves = _leaves_by_path(before), _leaves_by_path(after)
    changed = sorted(
        {
            path
            for path in before_leaves.keys() | after_leaves.keys()
            if before_leaves.get(path, _MISSING) != after_leaves.get(path, _MISSING)
        }
        - allowed
    )
    return verdict(not changed, {"changed": changed}, {"changed": []})


def verify_keys_unchanged(reading: PairReading, args: Args) -> Verdict:
    before, after = _named_file_or_tree(reading.before, reading.after, args.get("subject"))
    gone = sorted(_leaves_by_path(before).keys() - _leaves_by_path(after).keys())
    added = sorted(_leaves_by_path(after).keys() - _leaves_by_path(before).keys())
    return verdict(not gone and not added, {"removed": gone, "added": added}, {"removed": [], "added": []})


def _empty(value: object) -> bool:
    """Nothing there: `None`, or a sized thing with nothing in it."""
    return value is None or (isinstance(value, Sized) and len(value) == 0)


@dataclass(frozen=True)
class AbsenceReading:
    """Whether nothing is there, and what was there to see."""

    empty: bool
    seen: object


def read_absence(observed: object, args: Args) -> AbsenceReading:
    """Nothing there. On a working directory, no file at the path `subject` names."""
    if isinstance(observed, Tree):
        subject = args.get("subject")
        return AbsenceReading(
            empty=subject not in observed,
            seen={path: value for path, value in observed.items() if path == subject},
        )
    return AbsenceReading(empty=_empty(observed), seen=observed)


def verify_absent(reading: AbsenceReading, args: Args) -> Verdict:
    return verdict(reading.empty, reading.seen, "absent")


def verify_created(reading: PairReading, args: Args) -> Verdict:
    """Absent before the action, present after — both halves, or it proves nothing."""
    before, after = _named_files(reading.before, reading.after, args.get("subject"))
    was_absent, is_present = _empty(before), not _empty(after)
    return verdict(
        was_absent and is_present,
        {"before": before, "after": after},
        {"before": "absent", "after": "present"},
    )


def verify_removed(reading: PairReading, args: Args) -> Verdict:
    """Present before the action, absent after — the mirror of `created`, and for the mirror reason: absence afterwards alone passes on a subject that was never there."""
    before, after = _named_files(reading.before, reading.after, args.get("subject"))
    return verdict(
        not _empty(before) and _empty(after),
        {"before": before, "after": after},
        {"before": "present", "after": "absent"},
    )


def verify_persists(reading: PairReading, args: Args) -> Verdict:
    written, reread = reading.before, reading.after
    return verdict(reread is not None and reread == written, reread, written)
