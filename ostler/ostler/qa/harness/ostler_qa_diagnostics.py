from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import traceback
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ostler_qa_dsl import Target


RECORD_FD = 3


RECORD_FD_ENV = "OSTLER_QA_RECORD_FD"


RECORD_PATH_ENV = "OSTLER_QA_RECORD_PATH"


_SHELL = shutil.which("bash") or "/bin/sh"


_NODE_REF = re.compile(r"(?<![\w.])@([a-zA-Z0-9][a-zA-Z0-9_-]*)\.([a-zA-Z0-9][a-zA-Z0-9_-]*)")


_CAPTURE_REF = re.compile(r"(?<![\w.])\$([a-zA-Z0-9][a-zA-Z0-9_-]*)")


_ID_TOKEN = re.compile(r"\b[0-9a-fA-F]{16,}\b")


MECHANISMS = ("live", "fixture")


@dataclass(frozen=True)
class DriverSpec:
    """A driver's declared observation channels — a capability, not a bare name."""
    name: str
    observes: frozenset[str]


DRIVERS = (
    DriverSpec("python", frozenset({"response", "body", "subject"})),
    DriverSpec("playwright", frozenset({"page", "response", "body", "keyboard", "dom", "title", "console", "url", "stored", "clipboard", "download"})),
    DriverSpec("maestro", frozenset({"page", "subject"})),
)


DRIVER_NAMES = tuple(driver.name for driver in DRIVERS)


UI_DRIVERS = tuple(driver for driver in DRIVERS if driver.name in ("playwright", "maestro"))


UI_DRIVER_NAMES = tuple(driver.name for driver in UI_DRIVERS)


DEVICE_LAYOUT_SCHEMA = "device-layout/1"


DEFAULT_HTTP_TIMEOUT = 30.0


CEILING_S = 30.0


DEFAULT_EVENTUALLY_TIMEOUT = 5.0


EVENTUALLY_INTERVAL = 0.1


_PROCESS_START = time.monotonic()


_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "x-api-key"})


_CREDENTIAL_FACT_MIN_CHARS = 8


class HttpError(RuntimeError):
    """A response whose status the scenario did not say it expected, and whether the scenario already recorded it as a failed check."""

    def __init__(self, message: str, *, recorded: bool = False) -> None:
        super().__init__(message)
        self.recorded = recorded


class CheckFailed(AssertionError):
    """A `qa.require` that did not hold."""


STOP_REASON_LINES = 3


STOP_REASON_CHARS = 600


def stop_reason(exc: BaseException, plan_file: str) -> str:
    """The plan line a crash stopped at and the exception it raised, short enough to share a failure list."""
    frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if frame.filename == plan_file]
    parts = [f"line {frames[-1].lineno}: {(frames[-1].line or '').strip()}"] if frames else []
    lines = [line.strip() for line in str(exc).splitlines() if line.strip()][:STOP_REASON_LINES]
    name = type(exc).__name__
    parts.append(f"{name}: {' '.join(lines)}" if lines else name)
    reason = "; ".join(parts)
    if len(reason) > STOP_REASON_CHARS:
        return reason[: STOP_REASON_CHARS - 1] + "…"
    return reason


ADDRESS_BOOK_ENV = "STABLEMATE_ADDRESS_BOOK"


_ADDRESS = re.compile(r"(?<![$\w])\{([a-z][a-z0-9-]*)\}")


def resolve_addresses(text: str) -> str:
    """*text* with each `{name}` read from the run's address book, unchanged when the run names none."""
    if not _ADDRESS.search(text):
        return text
    where = os.environ.get(ADDRESS_BOOK_ENV, "")
    if not where:
        return text
    try:
        book = json.loads(Path(where).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{text!r} reads the address book at {where}, which is unreadable: {exc}") from exc
    if not isinstance(book, dict):
        raise ValueError(f"the address book at {where} is not a JSON object of name to URL")

    def value_of(match: re.Match[str]) -> str:
        value = book.get(match.group(1))
        if not isinstance(value, str):
            raise ValueError(f"{text!r} reads `{match.group(0)}`, which the address book at {where} does not give")
        return value.rstrip("/")

    return _ADDRESS.sub(value_of, text)


def unresolved_address_detail(target_decl: Target) -> str | None:
    """Why *target_decl*'s base URL still holds `{name}` references with no address book to give them, or None when it holds none."""
    base_url = target_decl.base_url
    if not base_url or os.environ.get(ADDRESS_BOOK_ENV, ""):
        return None
    names = list(dict.fromkeys(f"{{{name}}}" for name in _ADDRESS.findall(base_url)))
    if not names:
        return None
    return (
        f"target {target_decl.name!r} base_url {base_url!r} reads {', '.join(names)}, "
        f"and ${ADDRESS_BOOK_ENV} is unset, so no address book gives it"
    )


class _Recorder:
    """Writes JSONL records to a path, to `RECORD_FD`, or nowhere."""

    def __init__(self, fd: int | None = None) -> None:
        self._stream: Any = None
        path = os.environ.get(RECORD_PATH_ENV)
        if fd is None and path:
            try:
                self._stream = open(path, "a", encoding="utf-8")  # noqa: SIM115
            except OSError:
                self._stream = None
            return
        if fd is None:
            fd = int(os.environ.get(RECORD_FD_ENV, RECORD_FD))
        try:
            self._stream = os.fdopen(os.dup(fd), "w", encoding="utf-8")
        except OSError:
            self._stream = None

    def emit(self, record: Mapping[str, Any]) -> None:
        if self._stream is None:
            return
        self._stream.write(json.dumps(record, default=str) + "\n")
        self._stream.flush()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None


class _Missing:
    """The value `qa.field` yields for something the product did not put there."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def __contains__(self, item: Any) -> bool:
        return False

    def __getitem__(self, key: Any) -> "_Missing":
        return self

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("<missing>")

    def __lt__(self, other: object) -> bool:
        return False

    def __le__(self, other: object) -> bool:
        return False

    def __gt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return False


MISSING = _Missing()


@dataclass
class FixtureFault:
    """One book-fixture step that could not prove its state, classified per Q38."""

    fixture: str
    step_index: int
    step_kind: str
    fault_class: str
    detail: str


ARRIVAL_WAIT_S = 10.0


SETTLE_WAIT_MS = 5000


def harness_module(name: str) -> Any:
    """Import a sibling harness module by name."""
    import importlib

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module(name)
