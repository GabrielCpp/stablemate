from __future__ import annotations

from dataclasses import dataclass, field, replace

from groom.tui.link import Frame


@dataclass(frozen=True)
class Store:
    runs: tuple[Frame, ...] = ()
    status: Frame = field(default_factory=dict)
    scanning: bool = False
    selected: str = ""
    detail: Frame | None = None
    trail_view: str = "all"
    trail_kind: str = ""
    repo: Frame | None = None


TRAIL_VIEWS = ("all", "transcript", "telemetry")
TRAIL_KINDS = ("", "log", "span", "metric")
VIEW_LABELS = {"all": "All", "transcript": "Transcript", "telemetry": "Telemetry"}
KIND_LABELS = {
    "": "all telemetry", "log": "log records", "span": "completed spans", "metric": "metric samples",
}


def apply_state(store: Store, msg: Frame) -> Store:
    return replace(
        store,
        runs=tuple(msg.get("runs") or ()),
        status=msg.get("status") or store.status,
        scanning=bool(msg.get("scanning")),
    )


def apply_run(store: Store, msg: Frame) -> Store:
    row = msg.get("run")
    if not row:
        return store
    runs = [existing for existing in store.runs if existing["id"] != row["id"]]
    at = next((i for i, existing in enumerate(store.runs) if existing["id"] == row["id"]), None)
    if at is None:
        runs.append(row)
    else:
        runs.insert(at, row)
    runs.sort(key=lambda r: (r["rank"], r["name"]))
    return replace(store, runs=tuple(runs))


def apply_detail(store: Store, msg: Frame) -> Store:
    if msg.get("id") != store.selected:
        return store
    return replace(store, detail=msg.get("detail"))


def select(store: Store, run_id: str) -> Store:
    return replace(store, selected=run_id, detail=None, repo=store.repo if run_id == store.selected else None)


def choose_repo(store: Store, item: Frame) -> Store:
    chosen = {"container": item["container"], "repo": item.get("repo") or "", "label": item.get("label") or ""}
    return replace(store, repo=chosen)


def answered_gate(store: Store, msg: Frame) -> str:
    if store.selected and msg.get("id") == store.selected:
        return str(msg.get("file_path") or "")
    return ""


def run_by_id(store: Store, run_id: str) -> Frame | None:
    return next((row for row in store.runs if row["id"] == run_id), None)


def trail_lines(history: list[Frame], view: str, kind: str) -> list[Frame]:
    if view == "all":
        shown = [line for line in history if not line.get("absorbed")]
    else:
        shown = [line for line in history if (line.get("kind") == "turn") == (view == "transcript")]
    if kind and view != "transcript":
        return [line for line in shown if line.get("kind") == kind]
    return shown


def _following(options: tuple[str, ...], current: str) -> str:
    at = options.index(current) if current in options else -1
    return options[(at + 1) % len(options)]


def cycle_view(store: Store) -> Store:
    return replace(store, trail_view=_following(TRAIL_VIEWS, store.trail_view))


def cycle_kind(store: Store) -> Store:
    return replace(store, trail_kind=_following(TRAIL_KINDS, store.trail_kind))
