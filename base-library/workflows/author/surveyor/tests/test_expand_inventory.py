"""expand-inventory.py — deterministic materialization + freeze."""
from __future__ import annotations

import json

from tests.conftest import init_repo, run_script, write_inventory, write_rules

RULES = "docs/survey/units.yml"
INV = "docs/survey/inventory.json"


def make_tree(repo):
    for name in ("alpha", "beta"):
        d = repo / "src" / "components" / name
        d.mkdir(parents=True)
        (d / "main.ts").write_text("x\n", encoding="utf-8")
    routes = repo / "src" / "routes"
    routes.mkdir(parents=True)
    (routes / "home.svelte").write_text("x\n", encoding="utf-8")
    (routes / "about.svelte").write_text("x\n", encoding="utf-8")
    junk = repo / "src" / "components" / "node_modules"
    junk.mkdir()
    (junk / "dep.ts").write_text("x\n", encoding="utf-8")


def test_expands_folder_file_and_command_rules(tmp_path):
    init_repo(tmp_path)
    make_tree(tmp_path)
    write_rules(tmp_path, (
        "rules:\n"
        "  - kind: folder\n"
        "    glob: \"src/components/*\"\n"
        "  - kind: file\n"
        "    glob: \"src/routes/*.svelte\"\n"
        "  - kind: command\n"
        "    command: \"printf 'GET /a\\nGET /b\\n'\"\n"
        "    unit_kind: endpoint\n"
        "exclude:\n"
        "  - \"src/components/node_modules*\"\n"
    ))

    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "yes", out["expand_errors"]
    inv = json.loads((tmp_path / INV).read_text())
    ids = [u["id"] for u in inv["units"]]
    assert "src/components/alpha" in ids and "src/components/beta" in ids
    assert "src/routes/home.svelte" in ids and "src/routes/about.svelte" in ids
    assert "GET /a" in ids and "GET /b" in ids
    assert "src/components/node_modules" not in ids
    kinds = {u["id"]: u["kind"] for u in inv["units"]}
    assert kinds["src/components/alpha"] == "folder"
    assert kinds["src/routes/home.svelte"] == "file"
    assert kinds["GET /a"] == "endpoint"
    assert all(u["status"] == "pending" for u in inv["units"])
    assert out["unit_count"] == len(inv["units"]) == 6


def test_existing_inventory_is_frozen_and_never_reexpanded(tmp_path):
    init_repo(tmp_path)
    make_tree(tmp_path)
    write_rules(tmp_path, "rules:\n  - kind: folder\n    glob: \"src/components/*\"\n")
    write_inventory(tmp_path, [{"id": "only/unit", "status": "assessed"}])

    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "yes"
    assert "frozen" in out["inventory_note"]
    inv = json.loads((tmp_path / INV).read_text())
    assert [u["id"] for u in inv["units"]] == ["only/unit"]  # untouched


def test_rule_matching_nothing_is_rejected(tmp_path):
    init_repo(tmp_path)
    make_tree(tmp_path)
    write_rules(tmp_path, "rules:\n  - kind: folder\n    glob: \"nope/*\"\n")
    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "no"
    assert "matched no folder" in out["expand_errors"]
    assert not (tmp_path / INV).exists()


def test_structurally_bad_rules_are_rejected(tmp_path):
    init_repo(tmp_path)
    write_rules(tmp_path, (
        "rules:\n"
        "  - kind: nonsense\n"
        "    glob: \"src/*\"\n"
        "  - kind: command\n"
        "    command: \"\"\n"
    ))
    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "no"
    assert "kind 'nonsense'" in out["expand_errors"]
    assert "missing non-empty `command`" in out["expand_errors"]
    assert "unit_kind" in out["expand_errors"]


def test_missing_rules_file_is_rejected(tmp_path):
    init_repo(tmp_path)
    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "no"
    assert "planner must write it" in out["expand_errors"]


def test_record_slug_collision_is_rejected(tmp_path):
    init_repo(tmp_path)
    (tmp_path / "src" / "a-b").mkdir(parents=True)
    (tmp_path / "src" / "a_b").mkdir(parents=True)
    write_rules(tmp_path, "rules:\n  - kind: folder\n    glob: \"src/*\"\n")
    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "no"
    assert "collide on record slug" in out["expand_errors"]


def test_failing_command_is_rejected(tmp_path):
    init_repo(tmp_path)
    write_rules(tmp_path, (
        "rules:\n"
        "  - kind: command\n"
        "    command: \"exit 3\"\n"
        "    unit_kind: endpoint\n"
    ))
    out = run_script("expand-inventory.py", RULES, INV, repo=tmp_path)
    assert out["expand_ok"] == "no"
    assert "exited 3" in out["expand_errors"]
