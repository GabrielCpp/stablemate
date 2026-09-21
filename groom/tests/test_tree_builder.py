"""Tests for the dashboard's path tree builder (assets/dashboard.js)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "groom" / "assets"
NODE = shutil.which("node")

_START = "function buildTree(entries) {"
_END = "function TreeDir("

_HARNESS = """
import {{ readFileSync }} from "node:fs";
const src = readFileSync({path}, "utf8");
const start = src.indexOf({start});
const end = src.indexOf({end});
const buildTree = new Function(src.slice(start, end) + "\\nreturn buildTree;")();
console.log(JSON.stringify(buildTree(JSON.parse(process.env.GROOM_ENTRIES))));
"""


def _build(entries: list[dict]) -> dict:
    """Run the JS builder over a list of entries."""
    harness = _HARNESS.format(
        path=json.dumps(str(ASSETS / "dashboard.js")),
        start=json.dumps(_START),
        end=json.dumps(_END),
    )
    result = subprocess.run(
        [_node(), "--input-type=module", "-e", harness],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GROOM_ENTRIES": json.dumps(entries)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _node() -> str:
    """The node binary."""
    assert NODE is not None
    return NODE


def _skipped() -> bool:
    if NODE is None:
        print("SKIP  node not on PATH — tree builder not exercised", file=sys.stderr)
        return True
    return False


def test_source_still_bounds_the_function_the_harness_extracts():
    src = (ASSETS / "dashboard.js").read_text()
    assert src.count(_START) == 1
    assert src.index(_START) < src.index(_END)


def test_flat_paths_become_directory_nodes_and_file_leaves():
    if _skipped():
        return
    root = _build([{"path": "src/api/client.py"}, {"path": "README.md"}])
    assert root["files"] == [{"name": "README.md", "entry": {"path": "README.md"}}]
    leaf = root["dirs"]["src"]["dirs"]["api"]["files"][0]
    assert leaf["name"] == "client.py"
    assert root["dirs"]["src"]["files"] == []


def test_paths_sharing_a_prefix_reuse_one_directory_node():
    if _skipped():
        return
    root = _build([{"path": "src/a.py"}, {"path": "src/b.py"}])
    assert list(root["dirs"]) == ["src"]
    assert [f["name"] for f in root["dirs"]["src"]["files"]] == ["a.py", "b.py"]


def test_the_whole_entry_rides_along_on_the_leaf():
    if _skipped():
        return
    root = _build([{"path": "pkg/mod.go", "idx": 3, "add": 12, "del": 4}])
    assert root["dirs"]["pkg"]["files"][0]["entry"] == {
        "path": "pkg/mod.go", "idx": 3, "add": 12, "del": 4
    }


def test_insertion_order_is_preserved_and_nothing_is_deduplicated():
    if _skipped():
        return
    root = _build([{"path": "z.py"}, {"path": "a.py"}, {"path": "z.py"}])
    assert [f["name"] for f in root["files"]] == ["z.py", "a.py", "z.py"]


def test_an_empty_entry_list_yields_an_empty_root():
    if _skipped():
        return
    assert _build([]) == {"dirs": {}, "files": []}


def test_a_non_string_path_is_coerced_rather_than_rejected():
    if _skipped():
        return
    root = _build([{"path": None}, {"path": "ok.py"}])
    assert [f["name"] for f in root["files"]] == ["null", "ok.py"]


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(list(globals().items())):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report and keep going
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - failed}/{total} passed")
    raise SystemExit(1 if failed else 0)
