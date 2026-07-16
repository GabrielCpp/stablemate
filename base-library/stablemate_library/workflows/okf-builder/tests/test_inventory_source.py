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
    assert "server.go::(*Server).ServeHTTP" in codes
    assert "server.go::internalHelper" not in codes
    assert "route.tsx::ProjectRoute" in codes
    assert "route.tsx::Props" in codes
    assert "route.tsx::loader" in codes


def test_go_methods_are_qualified_by_their_receiver(tmp_path: Path) -> None:
    # The measured regression: `symbols()` emitted bare `SetRoleClaims` while books cite the
    # idiomatic `(*FirebaseClaimsWriter).SetRoleClaims`, so 1136 citations could never match
    # any of 877 inventory symbols. The book is right and the inventory was wrong.
    (tmp_path / "claims.go").write_text(
        "package p\n"
        "type FirebaseClaimsWriter struct{}\n"
        "type Reader struct{}\n"
        "func (w *FirebaseClaimsWriter) SetRoleClaims() {}\n"
        "func (r Reader) SetRoleClaims() {}\n"          # same method, different owner
        "func (*FirebaseClaimsWriter) Anonymous() {}\n"  # receiver with no variable name
        "func (w *FirebaseClaimsWriter) unexported() {}\n"
    )
    output = tmp_path / "inventory.json"
    run_script("inventory-source.py", str(tmp_path), str(output))
    codes = {u["code"] for u in json.loads(output.read_text())["units"]}

    # A pointer receiver keeps its star; a value receiver does not. Both forms appear in books.
    assert "claims.go::(*FirebaseClaimsWriter).SetRoleClaims" in codes
    assert "claims.go::Reader.SetRoleClaims" in codes
    # The whole point: two types declaring the same method in one file stay distinguishable.
    assert "claims.go::SetRoleClaims" not in codes
    assert "claims.go::(*FirebaseClaimsWriter).Anonymous" in codes
    assert "claims.go::(*FirebaseClaimsWriter).unexported" not in codes


def test_go_generic_declarations_are_read(tmp_path: Path) -> None:
    (tmp_path / "gen.go").write_text(
        "package p\n"
        "type Stack[T any] struct{}\n"
        "func Map[T any, U any](xs []T) []U { return nil }\n"
        "func (s *Stack[T]) Push(v T) {}\n"
    )
    output = tmp_path / "inventory.json"
    run_script("inventory-source.py", str(tmp_path), str(output))
    codes = {u["code"] for u in json.loads(output.read_text())["units"]}
    assert "gen.go::Map" in codes
    assert "gen.go::Stack" in codes
    # The receiver's type parameters are not part of the unit's name — books cite the type.
    assert "gen.go::(*Stack).Push" in codes


def test_unit_paths_are_repo_root_relative(tmp_path: Path) -> None:
    # A monorepo runs one book per service, but `code:` targets are repo-rooted so that one
    # book's citation means the same thing as another's. Source-relative paths made
    # `internal/x.go::S` ambiguous across services.
    source = tmp_path / "api-service"
    (source / "internal").mkdir(parents=True)
    (source / "internal" / "claims.go").write_text("package p\nfunc Write() {}\n")
    output = tmp_path / "inventory.json"

    run_script("inventory-source.py", str(source), str(output), "", str(tmp_path))

    data = json.loads(output.read_text())
    codes = {u["code"] for u in data["units"]}
    assert "api-service/internal/claims.go" in codes                 # the module unit
    assert "api-service/internal/claims.go::Write" in codes
    assert {u["path"] for u in data["units"]} == {"api-service/internal/claims.go"}


def test_excludes_stay_source_relative_while_paths_are_repo_rooted(tmp_path: Path) -> None:
    # `excludes` is configured per service (`okfBuilder.services.<name>.excludes`), so it is
    # relative to the service's source root even though emitted paths are not.
    source = tmp_path / "api-service"
    (source / "internal" / "testenv").mkdir(parents=True)
    (source / "internal" / "claims.go").write_text("package p\nfunc Write() {}\n")
    (source / "internal" / "testenv" / "fake.go").write_text("package p\nfunc Fake() {}\n")
    output = tmp_path / "inventory.json"

    run_script("inventory-source.py", str(source), str(output), "internal/testenv", str(tmp_path))

    paths = {u["path"] for u in json.loads(output.read_text())["units"]}
    assert paths == {"api-service/internal/claims.go"}


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


def test_inventory_covers_php_classes_and_qualified_methods(tmp_path: Path) -> None:
    (tmp_path / "AddProjectAction.php").write_text(
        "<?php\n"
        "namespace Project\\ProjectBundle\\Action;\n"
        "class AddProjectAction extends AbstractFormAction\n"
        "{\n"
        "    public function __construct( $container ) {}\n"
        "    public function getRenderPath( $packager ) {}\n"
        "    private function secret() {}\n"
        "    protected function alsoHidden() {}\n"
        "    static function fromRequest() {}\n"
        "}\n"
    )
    output = tmp_path / "inventory.json"
    run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))
    codes = {u["code"] for u in json.loads(output.read_text())["units"]}

    assert "AddProjectAction.php" in codes                                  # the module
    assert "AddProjectAction.php::AddProjectAction" in codes                # the class
    # A method is qualified by its class, so two classes in one file stay distinguishable.
    assert "AddProjectAction.php::AddProjectAction.getRenderPath" in codes
    assert "AddProjectAction.php::AddProjectAction.fromRequest" in codes    # static counts
    # Not the documented surface: private/protected, and DI/framework magic methods.
    assert "AddProjectAction.php::AddProjectAction.secret" not in codes
    assert "AddProjectAction.php::AddProjectAction.alsoHidden" not in codes
    assert "AddProjectAction.php::AddProjectAction.__construct" not in codes


def test_php_methods_are_qualified_by_their_own_class(tmp_path: Path) -> None:
    # Two classes in one file each declaring `handle` must not collapse into one unit.
    (tmp_path / "pair.php").write_text(
        "<?php\n"
        "class Alpha\n{\n    public function handle() {}\n}\n"
        "class Beta\n{\n    public function handle() {}\n}\n"
    )
    output = tmp_path / "inventory.json"
    run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))
    codes = {u["code"] for u in json.loads(output.read_text())["units"]}
    assert "pair.php::Alpha.handle" in codes
    assert "pair.php::Beta.handle" in codes


def test_inventory_covers_twig_templates_and_blocks(tmp_path: Path) -> None:
    (tmp_path / "HomePage.html.twig").write_text(
        "{% extends 'base.html.twig' %}\n"
        "{% block title %}Home{% endblock %}\n"
        "{%- block content -%}\n<p>hi</p>\n{%- endblock -%}\n"
    )
    output = tmp_path / "inventory.json"
    run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))
    codes = {u["code"] for u in json.loads(output.read_text())["units"]}
    # A template renders a screen, so the FILE is a real unit here — unlike Go/TS, where a
    # file is just a container for symbols. Both whitespace-control forms are recognized.
    assert "HomePage.html.twig" in codes
    assert "HomePage.html.twig::title" in codes
    assert "HomePage.html.twig::content" in codes


def test_unreadable_language_is_an_error_not_an_empty_inventory(tmp_path: Path) -> None:
    # The regression this guards: a PHP/Twig tree once yielded 0 units and 0 errors, which
    # reads downstream as "every unit is covered" — a book declared complete having
    # documented nothing. Blindness must be loud.
    (tmp_path / "foo.rb").write_text("class Foo\n  def bar\n  end\nend\n")
    (tmp_path / "bar.rb").write_text("class Bar\nend\n")
    output = tmp_path / "inventory.json"
    result = run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))

    assert result["source_unit_count"] == 0
    assert result["inventory_errors"], "an unsupported language must not report a clean bill"
    assert ".rb" in result["inventory_errors"]      # names what it could not read


def test_supported_language_present_does_not_trip_the_blindness_guard(tmp_path: Path) -> None:
    # A tree that mixes readable and unreadable files is not blind — only a tree with NO
    # readable source is. Otherwise every repo with a stray .rb would fail.
    (tmp_path / "app.py").write_text("def f():\n    pass\n")
    (tmp_path / "stray.rb").write_text("class Foo\nend\n")
    output = tmp_path / "inventory.json"
    result = run_script("inventory-source.py", str(tmp_path), str(output), "", str(tmp_path))
    assert result["inventory_errors"] == ""
    assert result["source_unit_count"] > 0


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
