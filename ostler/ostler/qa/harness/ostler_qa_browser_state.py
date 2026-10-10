"""The verifiers that read what the browser holds beyond the drawn page: its address, its storage and its clipboard."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar
from urllib.parse import urlsplit, urlunsplit

from ostler_qa_verdicts import Args, Verdict, str_arg, verdict

STATE_WAIT_S = 5.0

CLIPBOARD_KEY = "__ostlerClipboard"

CLIPBOARD_JS = f"""(() => {{
  const record = (text) => {{
    try {{
      const seen = JSON.parse(sessionStorage.getItem("{CLIPBOARD_KEY}") || "[]");
      seen.push(String(text));
      sessionStorage.setItem("{CLIPBOARD_KEY}", JSON.stringify(seen));
    }} catch (error) {{}}
  }};
  const clipboard = navigator.clipboard;
  if (clipboard) {{
    const writeText = clipboard.writeText.bind(clipboard);
    clipboard.writeText = (text) => {{ record(text); return writeText(text); }};
    const write = clipboard.write.bind(clipboard);
    clipboard.write = async (items) => {{
      for (const item of items) {{
        if (item.types.includes("text/plain")) record(await (await item.getType("text/plain")).text());
      }}
      return write(items);
    }};
  }}
  window.addEventListener("copy", (event) => {{
    record((event.clipboardData && event.clipboardData.getData("text/plain")) || String(document.getSelection() || ""));
  }});
}})();"""

_CLIPBOARD_READ_JS = f"""() => JSON.parse(sessionStorage.getItem("{CLIPBOARD_KEY}") || "[]")"""

_STORED_READ_JS = """async ({key, database, store}) => {
  if (key !== null) {
    const value = localStorage.getItem(key);
    return value === null ? [] : [value];
  }
  if (indexedDB.databases && !(await indexedDB.databases()).some((known) => known.name === database)) return [];
  const db = await new Promise((resolve, reject) => {
    const opening = indexedDB.open(database);
    opening.onsuccess = () => resolve(opening.result);
    opening.onerror = () => reject(opening.error);
  });
  try {
    if (!db.objectStoreNames.contains(store)) return [];
    return await new Promise((resolve, reject) => {
      const reading = db.transaction(store).objectStore(store).getAll();
      reading.onsuccess = () => resolve(reading.result.map((record) => JSON.stringify(record)));
      reading.onerror = () => reject(reading.error);
    });
  } finally {
    db.close();
  }
}"""

T = TypeVar("T")


def _settled(read: Callable[[], T], done: Callable[[T], bool]) -> T:
    """What *read* returns once *done* holds of it, or its last reading after `STATE_WAIT_S`, for state a screen writes late."""
    deadline = time.monotonic() + STATE_WAIT_S
    while True:
        reading = read()
        if done(reading) or time.monotonic() >= deadline:
            return reading
        time.sleep(0.1)


def _evaluate(observed: object) -> Callable[..., object]:
    evaluate = getattr(observed, "evaluate", None)
    if not callable(evaluate):
        raise TypeError(f"this check reads the browser through the page itself, not {type(observed).__name__}")
    return evaluate


def _strings(value: object) -> tuple[str, ...]:
    return tuple(str(each) for each in value) if isinstance(value, list) else ()


def _says(text: str, args: Args) -> bool:
    """Whether *text* is what a `text=` or `matches=` argument asks for, or anything when neither is given."""
    if "text" in args and str_arg(args, "text") not in text:
        return False
    return "matches" not in args or re.search(str_arg(args, "matches"), text) is not None


def _address(url: str) -> str:
    """The page's address as a user shares it within the app: path, query and fragment, with no origin."""
    parts = urlsplit(url)
    return urlunsplit(("", "", parts.path or "/", parts.query, parts.fragment))


def _url_matches(address: str, args: Args) -> bool:
    if "equals" in args:
        return address == str_arg(args, "equals")
    return re.search(str_arg(args, "matches"), address) is not None


@dataclass(frozen=True)
class UrlReading:
    """The page's address, once a screen that moves it late has had time to."""

    address: str


def read_url(observed: object, args: Args) -> UrlReading:
    if isinstance(observed, str):
        return UrlReading(address=_address(observed))
    address = _settled(lambda: _address(str(getattr(observed, "url"))), lambda read: _url_matches(read, args))
    return UrlReading(address=address)


def verify_url(reading: UrlReading, args: Args) -> Verdict:
    expected = {"equals": args["equals"]} if "equals" in args else {"matches": args["matches"]}
    return verdict(_url_matches(reading.address, args), reading.address, expected)


@dataclass(frozen=True)
class StoredReading:
    """The stored values the claim names, each a localStorage value or one IndexedDB record as JSON."""

    values: tuple[str, ...]


def _stored_location(args: Args) -> dict[str, str | None]:
    if "key" in args:
        return {"key": str_arg(args, "key"), "database": None, "store": None}
    database, slash, store = str_arg(args, "records").rpartition("/")
    if not slash or not database or not store:
        raise ValueError(f"`records` names an IndexedDB store as `<database>/<store>`, not {args['records']!r}")
    return {"key": None, "database": database, "store": store}


def _stored_holds(reading: StoredReading, args: Args) -> bool:
    found = len(reading.values)
    return found == args["count"] if "count" in args else found > 0


def read_stored(observed: object, args: Args) -> StoredReading:
    if isinstance(observed, list):
        values = _strings(observed)
        return StoredReading(values=tuple(value for value in values if _says(value, args)))
    evaluate = _evaluate(observed)
    location = _stored_location(args)

    def read() -> StoredReading:
        values = _strings(evaluate(_STORED_READ_JS, location))
        return StoredReading(values=tuple(value for value in values if _says(value, args)))

    return _settled(read, lambda reading: _stored_holds(reading, args))


def verify_stored(reading: StoredReading, args: Args) -> Verdict:
    expected = {"count": args["count"]} if "count" in args else "at least one"
    return verdict(_stored_holds(reading, args), list(reading.values), expected)


@dataclass(frozen=True)
class ClipboardReading:
    """Every text the page wrote to the clipboard, oldest first."""

    writes: tuple[str, ...]

    @property
    def last(self) -> str | None:
        return self.writes[-1] if self.writes else None


def _clipboard_holds(reading: ClipboardReading, args: Args) -> bool:
    return reading.last is not None and _says(reading.last, args)


def read_clipboard(observed: object, args: Args) -> ClipboardReading:
    if isinstance(observed, list):
        return ClipboardReading(writes=_strings(observed))
    evaluate = _evaluate(observed)
    return _settled(
        lambda: ClipboardReading(writes=_strings(evaluate(_CLIPBOARD_READ_JS))),
        lambda reading: _clipboard_holds(reading, args),
    )


def verify_clipboard(reading: ClipboardReading, args: Args) -> Verdict:
    expected = {"text": args["text"]} if "text" in args else {"matches": args["matches"]}
    return verdict(_clipboard_holds(reading, args), reading.last, expected)
