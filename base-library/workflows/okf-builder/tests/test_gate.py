"""The gate: the verdict is computed, the budget is per-run, and the worklist is keyed.

Every test here is a shape of one bug — *absence of signal rendered as a pass*. They exist
because each of these paths used to exit 0 and report a finished book.
"""
from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


select_item = load("okf_select_item", SCRIPTS / "select-item.py")
prepare = load("okf_prepare", SCRIPTS / "prepare.py")


def run(module, argv, monkeypatch, capsys) -> dict:
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        module.main(logging.getLogger("test"))
    return json.loads(capsys.readouterr().out)


def worklist(tmp_path: Path, done: int, pending: int = 1, service: str = "api") -> Path:
    items = [{"kind": "layer", "target": f"d{i}", "context": "", "status": "done"}
             for i in range(done)]
    items += [{"kind": "layer", "target": f"p{i}", "context": "", "status": "pending"}
              for i in range(pending)]
    path = tmp_path / "wl.json"
    path.write_text(json.dumps({"service": service, "items": items}))
    return path


# ── select-item: `max_items` bounds THIS run, not the worklist's lifetime ──────────────

def test_max_items_is_measured_from_the_run_baseline(tmp_path, monkeypatch, capsys):
    """A resumed worklist already past the cap must still get its own allowance.

    Counting `done` over the whole file made `max_items` a lifetime cap: a worklist with 10
    done items and a cap of 5 was instantly over budget and handed out zero items, and the
    run reported success having done nothing.
    """
    wl = worklist(tmp_path, done=10, pending=3)
    out = run(select_item, ["select-item.py", str(wl), "5", "10"], monkeypatch, capsys)
    assert out["over_budget"] == "no"
    assert out["has_item"] == "yes"
    assert out["done_this_run"] == 0


def test_over_budget_once_this_run_hits_the_cap(tmp_path, monkeypatch, capsys):
    wl = worklist(tmp_path, done=10, pending=3)
    out = run(select_item, ["select-item.py", str(wl), "5", "5"], monkeypatch, capsys)
    assert out["over_budget"] == "yes"
    assert out["has_item"] == "no"
    assert out["done_this_run"] == 5


def test_a_baseline_above_the_count_cannot_make_the_cap_unreachable(tmp_path, monkeypatch,
                                                                    capsys):
    """The worklist shrank under the run (a reset mid-flight): clamp, don't go negative."""
    wl = worklist(tmp_path, done=2, pending=1)
    out = run(select_item, ["select-item.py", str(wl), "1", "99"], monkeypatch, capsys)
    assert out["done_this_run"] == 0
    assert out["over_budget"] == "no"


# ── prepare: the worklist is a memory of work whose product is the book ────────────────

def book(root: Path, service: str, docs: bool) -> Path:
    features = root / "docs" / "features" / service
    features.mkdir(parents=True)
    if docs:
        (features / "index.md").write_text("# book\n")
    return features


def test_a_worklist_outliving_its_book_is_discarded(tmp_path):
    """A deleted book's stale `done` counter is a false memory, not a resume."""
    features = book(tmp_path, "api", docs=False)
    wl = worklist(tmp_path, done=7, pending=2)
    data, reset = prepare.load_worklist(wl, "api", features)
    assert reset is True
    assert data["items"] == []


def test_a_worklist_whose_book_still_exists_is_reused(tmp_path):
    features = book(tmp_path, "api", docs=True)
    wl = worklist(tmp_path, done=7, pending=2)
    data, reset = prepare.load_worklist(wl, "api", features)
    assert reset is False
    assert len(data["items"]) == 9


def test_a_worklist_for_another_service_is_discarded(tmp_path):
    features = book(tmp_path, "web", docs=True)
    wl = worklist(tmp_path, done=3, service="api")
    data, reset = prepare.load_worklist(wl, "web", features)
    assert reset is True
    assert data["items"] == []


def test_an_untouched_book_with_no_docs_reuses_an_undrained_worklist(tmp_path):
    """Nothing done yet: there is no product to be missing, so this is a real resume."""
    features = book(tmp_path, "api", docs=False)
    wl = worklist(tmp_path, done=0, pending=4)
    data, reset = prepare.load_worklist(wl, "api", features)
    assert reset is False
    assert len(data["items"]) == 4


def test_a_corrupt_worklist_is_discarded_not_crashed_on(tmp_path):
    features = book(tmp_path, "api", docs=True)
    wl = tmp_path / "wl.json"
    wl.write_text("{not json")
    data, reset = prepare.load_worklist(wl, "api", features)
    assert reset is True
    assert data["items"] == []
