from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"


def run_script(name: str, *args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_inventory_covers_python_go_and_typescript(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("class Public:\n    pass\n\ndef helper():\n    pass\n")
    (tmp_path / "server.go").write_text(
        "package p\n\ntype Server struct{}\ntype Handler interface{}\n"
        "func NewServer() *Server { return nil }\nfunc (s *Server) ServeHTTP() {}\n"
        "func internalHelper() {}\n"
    )
    (tmp_path / "route.tsx").write_text(
        "export default function ProjectRoute() { return null }\n"
        "export interface Props {}\nexport const loader = () => null\n"
    )
    output = tmp_path / "inventory.json"

    result = run_script("inventory-source.py", str(tmp_path), str(output))

    assert result["inventory_errors"] == ""
    codes = {unit["code"] for unit in json.loads(output.read_text())["units"]}
    assert "app.py::Public" in codes
    assert "app.py::helper" in codes
    assert "server.go::Server" in codes
    assert "server.go::Handler" in codes
    assert "server.go::NewServer" in codes
    assert "server.go::ServeHTTP" in codes
    assert "server.go::internalHelper" not in codes
    assert "route.tsx::ProjectRoute" in codes
    assert "route.tsx::Props" in codes
    assert "route.tsx::loader" in codes


def test_inventory_excludes_tests_generated_and_dependencies(tmp_path: Path) -> None:
    (tmp_path / "main.go").write_text("package p\nfunc Main() {}\n")
    (tmp_path / "main_test.go").write_text("package p\nfunc TestMain() {}\n")
    (tmp_path / "types.gen.go").write_text("package p\ntype Generated struct{}\n")
    node_modules = tmp_path / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "index.ts").write_text("export const dependency = 1\n")
    output = tmp_path / "inventory.json"

    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "capture.ts").write_text("export const capture = 1\n")

    run_script("inventory-source.py", str(tmp_path), str(output), "tools")

    paths = {unit["path"] for unit in json.loads(output.read_text())["units"]}
    assert paths == {"main.go"}


def test_record_can_requeue_a_completed_item(tmp_path: Path) -> None:
    worklist = tmp_path / "worklist.json"
    worklist.write_text(json.dumps({"items": [
        {"kind": "concept", "target": "Server", "context": "old", "status": "done"}
    ]}))

    result = run_script(
        "record.py", str(worklist), "",
        json.dumps([{"kind": "concept", "target": "Server", "context": "below bar",
                     "requeue": True}]),
    )

    item = json.loads(worklist.read_text())["items"][0]
    assert item["status"] == "pending"
    assert item["context"] == "below bar"
    assert result["added"] == 1
