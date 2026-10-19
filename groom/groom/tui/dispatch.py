from __future__ import annotations

import json
from dataclasses import dataclass

from rich.text import Text

from groom.tui.attend import when
from groom.tui.clean import clean
from groom.tui.link import Frame

LOADING_TEXT = "Loading queues…"
EMPTY_TEXT = "No dispatch queues configured. Add a [groom.dispatch.<name>] section to enable one."
NO_QUEUE_TEXT = "Select a queue to see its items."
NO_ITEMS_TEXT = "No items on this queue."
NO_ITEM_TEXT = "Select an item to see its parameters."
GONE_TEXT = "That item is no longer on this queue."
STATUS_STYLE = {
    "pending": "yellow",
    "running": "bold green",
    "done": "dim",
    "failed": "red",
    "cancelled": "dim",
}


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    select: bool
    required: bool
    default: str
    options: tuple[str, ...]


def queue_row(row: Frame) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(clean(row.get("name")), style="bold")
    text.append(f"  {clean(row.get('running'))}/{clean(row.get('concurrency'))} running")
    text.append("\n" + clean(row.get("command")), style="dim")
    return text


def item_row(item: Frame) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    status = clean(item.get("status"))
    text.append(status, style=STATUS_STYLE.get(status, ""))
    text.append("  " + clean(item.get("item_id")))
    if item.get("exit_code") is not None:
        text.append(f"  exit {clean(item['exit_code'])}", style="dim")
    return text


def _value(value: object) -> str:
    return "—" if value is None else clean(value)


def params_json(params: object) -> str:
    return clean(json.dumps(params if params is not None else {}, indent=2, ensure_ascii=False))


def detail_text(item: Frame, queue: str) -> Text:
    text = Text()
    text.append(clean(item.get("queue") or queue), style="bold")
    text.append("  " + clean(item.get("item_id")))
    status = clean(item.get("status"))
    text.append("  " + status, style=STATUS_STYLE.get(status, ""))
    rows = [
        ("command", clean(item.get("command"))),
        ("pid", _value(item.get("pid"))),
        ("exit code", _value(item.get("exit_code"))),
        ("started", when(item.get("started_at")) or "—"),
        ("run id", clean(item.get("run_id"))),
    ]
    for label, value in rows:
        text.append(f"\n{label:<10}", style="dim")
        text.append(value)
    text.append("\nparams", style="dim")
    text.append("\n" + "\n".join("  " + line for line in params_json(item.get("params")).splitlines()))
    return text


def fields(params: list[Frame]) -> list[Field]:
    result = []
    for entry in params:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        options = entry.get("options")
        result.append(Field(
            name=str(entry["name"]),
            label=clean(entry.get("label") or entry["name"]),
            select=entry.get("type") == "select",
            required=bool(entry.get("required")),
            default=clean(entry.get("default")),
            options=tuple(clean(option) for option in options) if isinstance(options, list) else (),
        ))
    return result


def label_text(field: Field) -> str:
    return field.label + (" *" if field.required else "")


def missing(form: list[Field], values: dict[str, str]) -> Field | None:
    return next((field for field in form if field.required and not values[field.name].strip()), None)
