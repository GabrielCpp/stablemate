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
    return replace(store, selected=run_id, detail=None)


def answered_gate(store: Store, msg: Frame) -> str:
    if store.selected and msg.get("id") == store.selected:
        return str(msg.get("file_path") or "")
    return ""


def run_by_id(store: Store, run_id: str) -> Frame | None:
    return next((row for row in store.runs if row["id"] == run_id), None)
