"""split-unit.py — self-healing granularity."""
from __future__ import annotations

import json

from .conftest import init_repo, run_script, write_inventory, write_rules

INV = "docs/survey/inventory.json"


def inv_units(repo):
    return json.loads((repo / INV).read_text())["units"]


def test_folder_splits_into_children_in_place(tmp_path):
    init_repo(tmp_path)
    big = tmp_path / "src" / "big"
    (big / "childdir").mkdir(parents=True)
    (big / "a.ts").write_text("x\n", encoding="utf-8")
    (big / ".hidden").write_text("x\n", encoding="utf-8")
    write_inventory(tmp_path, [{"id": "src/zero"}, {"id": "src/big"}, {"id": "src/last"}])

    out = run_script("split-unit.py", INV, "src/big", repo=tmp_path)
    assert out["split_ok"] == "yes", out["split_errors"]
    assert out["children_count"] == 2
    ids = [u["id"] for u in inv_units(tmp_path)]
    # Children replace the parent AT its position; siblings untouched; dotfiles skipped.
    assert ids == ["src/zero", "src/big/a.ts", "src/big/childdir", "src/last"]
    kinds = {u["id"]: u["kind"] for u in inv_units(tmp_path)}
    assert kinds["src/big/childdir"] == "folder"
    assert kinds["src/big/a.ts"] == "file"
    assert all(u["status"] == "pending" for u in inv_units(tmp_path) if "big" in u["id"])


def test_split_children_honor_rules_excludes(tmp_path):
    init_repo(tmp_path)
    big = tmp_path / "src" / "big"
    (big / "node_modules").mkdir(parents=True)
    (big / "a.ts").write_text("x\n", encoding="utf-8")
    write_rules(tmp_path, "rules:\n  - kind: folder\n    glob: \"src/*\"\nexclude:\n  - \"*node_modules*\"\n")
    write_inventory(tmp_path, [{"id": "src/big"}])

    out = run_script("split-unit.py", INV, "src/big", repo=tmp_path)
    assert out["split_ok"] == "yes"
    assert [u["id"] for u in inv_units(tmp_path)] == ["src/big/a.ts"]


def test_file_unit_cannot_split(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/a.ts", "kind": "file"}])
    out = run_script("split-unit.py", INV, "src/a.ts", repo=tmp_path)
    assert out["split_ok"] == "no"
    assert "only folder" in out["split_errors"]


def test_missing_directory_cannot_split(tmp_path):
    init_repo(tmp_path)
    write_inventory(tmp_path, [{"id": "src/gone"}])
    out = run_script("split-unit.py", INV, "src/gone", repo=tmp_path)
    assert out["split_ok"] == "no"
    assert "not a directory" in out["split_errors"]


def test_empty_folder_cannot_split(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "src" / "empty").mkdir(parents=True)
    write_inventory(tmp_path, [{"id": "src/empty"}])
    out = run_script("split-unit.py", INV, "src/empty", repo=tmp_path)
    assert out["split_ok"] == "no"
    assert "no splittable children" in out["split_errors"]
