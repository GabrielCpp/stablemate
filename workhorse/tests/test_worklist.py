"""Tests for the generic worklist primitive (workhorse/worklist.py).

The primitive is workflow-agnostic: items are ``{id, status, order?, payload?}`` and
nothing here knows a story from an epic. Covered:
- select_next: active-first crash-safe re-pick, then first pending in order, skipping
  done/blocked/skip-set;
- counts: status buckets + not-done category composition ("N of X");
- the JSON backend: atomic round-trip, mark/prune, object-with-items_key form;
- snapshot: the label/activity-ready shape.

Run: ./.venv/bin/python tests/test_worklist.py   (or via pytest)
"""
from __future__ import annotations

import json
from pathlib import Path

from workhorse import worklist as wl


def _items():
    return [
        {"id": "a", "status": "done", "order": 1, "payload": {"cat": "ui"}},
        {"id": "b", "status": "blocked", "order": 2, "payload": {"cat": "api"}},
        {"id": "c", "status": "pending", "order": 3, "payload": {"cat": "ui"}},
        {"id": "d", "status": "pending", "order": 4, "payload": {"cat": "api"}},
    ]


# --------------------------------------------------------------------------- #
# select_next
# --------------------------------------------------------------------------- #
def test_select_next_skips_done_and_blocked():
    got = wl.select_next(_items())
    assert got["id"] == "c"


def test_active_item_is_preferred_for_crash_safe_repick():
    items = _items()
    items[3]["status"] = "active"  # d is mid-flight
    got = wl.select_next(items)
    assert got["id"] == "d", "an active item must be re-picked before a fresh pending one"


def test_skip_set_passes_over_an_item():
    got = wl.select_next(_items(), skip={"c"})
    assert got["id"] == "d"


def test_drained_queue_returns_none():
    items = [{"id": "a", "status": "done"}, {"id": "b", "status": "blocked"}]
    assert wl.select_next(items) is None


def test_order_key_beats_list_order():
    items = [
        {"id": "late", "status": "pending", "order": 9},
        {"id": "early", "status": "pending", "order": 1},
    ]
    assert wl.select_next(items)["id"] == "early"


def test_custom_scheme_vocabulary():
    scheme = wl.Scheme(done=frozenset({"merged"}), blocked=frozenset({"held"}))
    items = [
        {"id": "a", "status": "merged"},
        {"id": "b", "status": "held"},
        {"id": "c", "status": "todo"},
    ]
    assert wl.select_next(items, scheme=scheme)["id"] == "c"


# --------------------------------------------------------------------------- #
# counts
# --------------------------------------------------------------------------- #
def test_counts_breakdown_and_composition():
    c = wl.counts(_items(), category_key="cat")
    assert c["total"] == 4
    assert c["done"] == 1 and c["blocked"] == 1 and c["pending"] == 2
    assert c["remaining"] == 3  # not-done
    # by_category counts the NOT-done items only: c(ui), d(api), b(api, blocked-but-not-done)
    assert c["by_category"] == {"ui": 1, "api": 2}


def test_counts_without_category_key_has_empty_composition():
    c = wl.counts(_items())
    assert c["by_category"] == {}


# --------------------------------------------------------------------------- #
# JSON backend + WorkList
# --------------------------------------------------------------------------- #
def test_json_backend_roundtrip_mark_and_prune(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text(json.dumps(_items()))
    lst = wl.WorkList(wl.JsonBackend(path), category_key="cat")

    assert lst.select_next()["id"] == "c"
    assert lst.mark("c", "done") is True
    assert lst.mark("nonexistent", "done") is False
    # After marking c done, next pending is d.
    assert lst.select_next()["id"] == "d"
    # The change persisted atomically to disk.
    on_disk = json.loads(path.read_text())
    assert next(i for i in on_disk if i["id"] == "c")["status"] == "done"

    assert lst.prune("d") is True
    assert lst.select_next() is None  # a done, b blocked, c done, d gone


def test_json_backend_object_with_items_key(tmp_path):
    path = tmp_path / "board.json"
    path.write_text(json.dumps({"meta": {"v": 1}, "items": _items()}))
    lst = wl.WorkList(wl.JsonBackend(path, items_key="items"))
    assert lst.mark("c", "done") is True
    saved = json.loads(path.read_text())
    assert saved["meta"] == {"v": 1}  # sibling metadata preserved
    assert next(i for i in saved["items"] if i["id"] == "c")["status"] == "done"


def test_snapshot_is_label_ready(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(_items()))
    lst = wl.WorkList(wl.JsonBackend(path), category_key="cat")
    snap = lst.snapshot(current="c")
    assert snap["current"] == "c"
    assert snap["progress"] == "1/4"
    assert snap["remaining"] == 3
    assert snap["composition"] == "2 api · 1 ui"  # sorted, deterministic


def test_missing_file_is_an_empty_queue(tmp_path):
    lst = wl.WorkList(wl.JsonBackend(tmp_path / "absent.json"))
    assert lst.items() == []
    assert lst.select_next() is None


# --------------------------------------------------------------------------- #
# kind — one worklist holding many lists
# --------------------------------------------------------------------------- #
def _mixed():
    """One worklist holding three lists (epics, stories, fixes), the shape a run that
    tracks all its work in a single store would keep."""
    return [
        {"id": "E1", "kind": "epic", "status": "done", "order": 1},
        {"id": "E2", "kind": "epic", "status": "pending", "order": 2},
        {"id": "S1", "kind": "story", "status": "done", "order": 1},
        {"id": "S2", "kind": "story", "status": "pending", "order": 2},
        {"id": "S3", "kind": "story", "status": "pending", "order": 3},
        {"id": "F1", "kind": "fix", "status": "blocked", "order": 1},
    ]


def test_select_next_scopes_to_a_kind():
    # Unscoped, the first pending item overall is E2; scoped to stories it is S2.
    assert wl.select_next(_mixed())["id"] == "E2"
    assert wl.select_next(_mixed(), kind="story")["id"] == "S2"
    assert wl.select_next(_mixed(), kind="fix") is None  # only a blocked fix remains


def test_counts_scope_by_kind_and_report_by_kind():
    # Scoped to stories: 3 total, 1 done, 2 pending.
    cs = wl.counts(_mixed(), kind="story")
    assert cs["total"] == 3 and cs["done"] == 1 and cs["pending"] == 2
    # Unscoped, by_kind is the composition of NOT-done items: E2, S2, S3, F1.
    call = wl.counts(_mixed())
    assert call["by_kind"] == {"epic": 1, "story": 2, "fix": 1}


def test_snapshot_scoped_to_a_kind_and_the_kinds_line():
    snap = wl.snapshot(_mixed(), current="S2", kind="story")
    assert snap["progress"] == "1/3"  # stories only
    # Sorted by kind name, not-done items only: epic(1), fix(1), story(2).
    assert wl.snapshot(_mixed())["kinds"] == "1 epic · 1 fix · 2 story"


def test_mark_and_prune_disambiguate_by_kind(tmp_path):
    """An id that recurs across lists (an epic and a story both "A1") is marked/pruned
    on the right list when kind is given."""
    items = [
        {"id": "A1", "kind": "epic", "status": "pending"},
        {"id": "A1", "kind": "story", "status": "pending"},
    ]
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(items))
    lst = wl.WorkList(wl.JsonBackend(path))

    assert lst.mark("A1", "done", kind="story") is True
    on_disk = json.loads(path.read_text())
    story = next(i for i in on_disk if i["kind"] == "story")
    epic = next(i for i in on_disk if i["kind"] == "epic")
    assert story["status"] == "done" and epic["status"] == "pending"  # only the story moved

    assert lst.prune("A1", kind="epic") is True
    remaining = json.loads(path.read_text())
    assert [i["kind"] for i in remaining] == ["story"]  # only the epic dropped


def test_items_filter_by_kind(tmp_path):
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(_mixed()))
    lst = wl.WorkList(wl.JsonBackend(path))
    assert {i["id"] for i in lst.items(kind="epic")} == {"E1", "E2"}
    assert len(lst.items()) == 6  # unscoped = every kind


def test_stateless_snapshot_matches_the_worklist_method():
    """The module-level snapshot (for stores that aren't a Backend — coder hands items in
    directly) produces the same label-ready shape as WorkList.snapshot."""
    items = _items()
    snap = wl.snapshot(items, current="c", category_key="cat")
    assert snap["current"] == "c"
    assert snap["progress"] == "1/4"
    assert snap["remaining"] == 3
    assert snap["composition"] == "2 api · 1 ui"
    # An empty queue is a valid snapshot, not a crash — "0/0", nothing remaining.
    empty = wl.snapshot([])
    assert empty["progress"] == "0/0" and empty["remaining"] == 0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            import inspect
            if "tmp_path" in inspect.signature(fn).parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    fn(Path(d))
            else:
                fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
