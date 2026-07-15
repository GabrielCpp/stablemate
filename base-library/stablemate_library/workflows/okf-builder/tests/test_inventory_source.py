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


def test_operational_surface_inventoried_from_generic_evidence(tmp_path: Path) -> None:
    (tmp_path / "Makefile").write_text(
        "VERSION = 1\n.PHONY: serve\nserve:\n\tgroom serve\ntest:\n\tpytest\n"
        "%.o: %.c\n\tcc\n"
    )
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  gateway:\n    image: x\n  db:\n    image: pg\nvolumes:\n  data:\n"
    )
    (tmp_path / "package.json").write_text('{"scripts": {"dev": "vite", "build": "vite build"}}')
    (tmp_path / "pyproject.toml").write_text(
        "[project.scripts]\ngroom = \"groom.cli:main\"\n"
    )
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__main__.py").write_text("print('hi')\n")
    output = tmp_path / "inventory.json"

    result = run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))

    data = json.loads(output.read_text())
    ops = {(u["kind"], u["name"]) for u in data["operational"]}
    assert ("make-target", "serve") in ops
    assert ("make-target", "test") in ops
    assert ("make-target", "VERSION") not in ops     # a variable, not a target
    assert not any(name == "%.o" for _, name in ops)  # pattern rules skipped
    assert ("compose-service", "gateway") in ops
    assert ("compose-service", "db") in ops
    assert ("compose-service", "data") not in ops     # `volumes:`, not `services:`
    assert ("package-script", "dev") in ops
    assert ("console-script", "groom") in ops
    assert ("entry-point", "app") in ops
    assert result["operational_unit_count"] == len(data["operational"])


def test_operational_surface_empty_for_a_bare_source_tree(tmp_path: Path) -> None:
    (tmp_path / "lib.py").write_text("def f():\n    pass\n")
    output = tmp_path / "inventory.json"
    result = run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))
    assert json.loads(output.read_text())["operational"] == []
    assert result["operational_unit_count"] == 0


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
