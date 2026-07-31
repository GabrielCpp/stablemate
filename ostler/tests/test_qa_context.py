from __future__ import annotations

import subprocess
from pathlib import Path

from ostler.qa.context import ChangedUnit, _is_generated_unit, build_context, validate_context


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_context_maps_base_grounding_and_preserves_repeated_refs(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    feature = tmp_path / "docs/features/demo/item.md"
    feature.write_text(
        """---
type: concept
title: Item
---
# Item

- code: app/service.py::create_item
- code: app/service.py::read_item
- verify: tests/test_service.py::test_create
- verify: tests/test_service.py::test_read
""",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.write_text(
        "def create_item():\n    return 'old'\n\ndef read_item():\n    return 'item'\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    # Removing the head grounding cannot hide impact because the base graph is unioned.
    feature.write_text(feature.read_text(encoding="utf-8").replace("- code: app/service.py::create_item\n", ""), encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace("return 'old'", "return 'new'"), encoding="utf-8")

    packet = build_context(
        tmp_path,
        base=base,
        source_roots={"demo": ["app"]},
    )

    assert validate_context(packet) == []
    assert packet["changedCode"][0]["headSymbols"] == ["create_item"]
    assert packet["directNodes"]
    assert packet["obligations"]
    refs = {item["ref"] for item in packet["verificationRefs"]}
    assert "tests/test_service.py::test_create" in refs
    assert "tests/test_service.py::test_read" in refs


def test_one_code_bullet_citing_two_files_owns_both(tmp_path: Path):
    """The bullet the book actually writes: two backticked refs, one `code:` key.

    Read as a single ref it normalized to a path with a backtick-comma-backtick in the middle,
    so the node owned *neither* file and a change to one was reported `unmapped-change` — the
    silent failure `ostler.refs` exists to prevent.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/shell.md").write_text(
        "---\ntype: concept\ntitle: Shell\n---\n# Shell\n\n"
        "- code: `app/config.ts`, `app/package.json`\n",
        encoding="utf-8",
    )
    config = tmp_path / "app/config.ts"
    config.write_text("export const ssr = true\n", encoding="utf-8")
    (tmp_path / "app/package.json").write_text('{"name": "demo"}\n', encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    config.write_text("export const ssr = false\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    kinds = [f["kind"] for f in packet["healthFindings"]]
    assert "unmapped-change" not in kinds, kinds  # the node cites it; ownership must be found
    owners = {node["node"]: node["reasons"] for node in packet["directNodes"]}
    assert owners, "the node citing the changed file must own it"
    # The ref proves the parse: undecorated, and the first of the two the bullet cites.
    assert [r for reasons in owners.values() for r in reasons] == [
        {"kind": "file-owner", "ref": "app/config.ts"},
    ]


def test_context_reports_unmapped_production_change(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n",
        encoding="utf-8",
    )
    (tmp_path / "unknown").mkdir()
    source = tmp_path / "unknown/service.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("VALUE = 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"other": ["unknown"]})

    assert packet["healthFindings"][0]["kind"] == "unmapped-change"


def test_context_root_source_includes_shared_code_but_excludes_doc_roots(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    feature = tmp_path / "docs/features/demo/item.md"
    feature.write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n\n"
        "- code: internal/shared.py::shared_value\n",
        encoding="utf-8",
    )
    (tmp_path / "internal").mkdir()
    source = tmp_path / "internal/shared.py"
    source.write_text("def shared_value():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("def shared_value():\n    return 'new'\n", encoding="utf-8")
    feature.write_text(feature.read_text(encoding="utf-8") + "\nCurrent behavior.\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_shared.py").write_text(
        "def test_shared():\n    assert True\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["."]})

    assert [item["path"] for item in packet["changedCode"]] == ["internal/shared.py"]
    assert not [
        item for item in packet["healthFindings"] if item["severity"] == "error"
    ]


def test_context_fallback_symbols_cover_non_python_function_bodies(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n\n"
        "- code: app/service.ts::second\n",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    source = tmp_path / "app/service.ts"
    source.write_text(
        "function first() {\n  return 1;\n}\n\n"
        "function second() {\n  return 2;\n}\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text(source.read_text(encoding="utf-8").replace("return 2", "return 3"), encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert packet["changedCode"][0]["headSymbols"] == ["second"]


def test_context_maps_go_receiver_method_body_to_qualified_symbol(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Server\n---\n# Server\n\n"
        "- code: app/server.go::(*Server).Serve\n",
        encoding="utf-8",
    )
    (tmp_path / "app").mkdir()
    source = tmp_path / "app/server.go"
    source.write_text(
        "package app\n\ntype Server struct{}\n\n"
        "func (s *Server) Serve() int {\n\treturn 1\n}\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text(source.read_text(encoding="utf-8").replace("return 1", "return 2"), encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert packet["changedCode"][0]["headSymbols"] == ["(*Server).Serve"]


def test_context_excludes_snapshot_fixture_but_keeps_executable_markdown(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Prompt\n---\n# Prompt\n\n"
        "- code: prompts/system.md\n",
        encoding="utf-8",
    )
    (tmp_path / "prompts").mkdir()
    prompt = tmp_path / "prompts/system.md"
    prompt.write_text("Do the old behavior.\n", encoding="utf-8")
    contributing = tmp_path / "CONTRIBUTING.md"
    contributing.write_text("Old contributor guide.\n", encoding="utf-8")
    (tmp_path / "testdata").mkdir()
    snapshot = tmp_path / "testdata/output.golden"
    snapshot.write_text("old\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    prompt.write_text("Do the new behavior.\n", encoding="utf-8")
    contributing.write_text("New contributor guide.\n", encoding="utf-8")
    snapshot.write_text("new\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["."]})

    assert [item["path"] for item in packet["changedCode"]] == ["prompts/system.md"]


def test_context_turns_nested_okf_behavior_into_qa_obligations(tmp_path: Path):
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs/features/acme/gui/screens/items.md").write_text(
        """---
type: screen
title: Items
---
# Items

## Components

### save-button
- role: button
- name: Save item
- keyboard: Tab then Enter
- states: enabled while the form is valid; disabled otherwise
- code: app/items.py::save_item

## Interactions

### save-item
- on: [save-button](#save-button)
- trigger: click
- when: the form is valid
- does:
  - request: persist the item
  - error: preserve fields and expose an alert
- code: app/items.py::save_item
- verify: tests/test_items.py::test_save, tests/test_items.py::test_retry
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text(
        "def save_item():\n    return 'old'\n", encoding="utf-8"
    )
    (tmp_path / "tests/test_items.py").write_text("", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text(
        "def save_item():\n    return 'new'\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    requirements = {item["requirement"] for item in packet["obligations"]}
    assert "request: persist the item" in requirements
    assert "error: preserve fields and expose an alert" in requirements
    assert "enabled while the form is valid; disabled otherwise" in requirements
    assert "Tab then Enter" in requirements
    assert {item["path"] for item in packet["verificationRefs"]} == {
        "tests/test_items.py"
    }
    assert len(packet["verificationRefs"]) == 2


def test_context_indexes_verification_for_unimpacted_nodes(tmp_path: Path):
    (tmp_path / "docs/features/acme/concepts").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/concepts/items.md").write_text(
        """---
type: concept
title: Items
---
# Items
- code: app/items.py::save_item
- verify: tests/test_items.py::test_save
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/acme/concepts/accounts.md").write_text(
        """---
type: concept
title: Accounts
---
# Accounts
- code: app/accounts.py::login
- verify: tests/test_accounts.py::test_login
- verify: mobile/test/accounts_test.dart::login succeeds
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 1\n", encoding="utf-8")
    (tmp_path / "app/accounts.py").write_text("def login():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    indexed = {item["path"]: item["impacted"] for item in packet["verificationIndex"]}
    assert indexed == {
        "mobile/test/accounts_test.dart": False,
        "tests/test_accounts.py": False,
        "tests/test_items.py": True,
    }


def test_context_validation_accepts_version_one_packet_without_verification_index():
    packet = {
        "version": 1,
        "available": True,
        "changedCode": [],
        "directNodes": [],
        "contracts": [],
        "journeys": [],
        "journeyNodes": [],
        "verificationRefs": [],
        "healthFindings": [],
        "obligations": [],
    }

    assert validate_context(packet) == []


def test_build_and_config_files_are_not_production_units(tmp_path: Path):
    """Build, dependency-manifest, and tooling-config files carry no user-observable behaviour
    and no feature Concept owns them — correctly. Left classified as production they fail the
    documentation gate as "unmapped production units", which is exactly what blocked the first
    greenfield coder story: its diff legitimately touched go.mod/go.sum/a Makefile/Pulumi
    config alongside the real Go. Real code stays production; only the scaffolding is excluded."""
    from ostler.qa.context import _is_non_production_path as np

    for path in (
        "Makefile", "infra/Makefile", "infra/.gitignore", "infra/go.mod", "infra/go.sum",
        "infra/Pulumi.yaml", "infra/Pulumi.dev.yaml", "web/package.json", "web/tsconfig.json",
        "web/vite.config.ts", "app/pubspec.yaml", "app/pubspec.lock", "app/analysis_options.yaml",
    ):
        assert np(path), f"{path} should be non-production (build/config)"

    for path in (
        "infra/main.go", "api/handler.go", "api/internal/store/store.go",
        "web/app/routes/todos.tsx", "app/lib/main.dart",
    ):
        assert not np(path), f"{path} is real code and must stay production"


def test_context_ignores_build_files_alongside_real_change(tmp_path: Path):
    """The end-to-end shape of the greenfield-coder failure: a story that touches production
    code AND its build manifest must not be failed on the manifest."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n", encoding="utf-8")
    (tmp_path / "svc").mkdir()
    code = tmp_path / "svc/service.py"
    code.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "svc/go.mod").write_text("module x\n", encoding="utf-8")
    (tmp_path / "svc/Makefile").write_text("build:\n\techo x\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    # Change the manifest and the Makefile — but NOT the code.
    (tmp_path / "svc/go.mod").write_text("module x\n\nrequire y v1.2.3\n", encoding="utf-8")
    (tmp_path / "svc/Makefile").write_text("build:\n\techo changed\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"svc": ["svc"]})
    unmapped = [f for f in packet.get("healthFindings", []) if f["kind"] == "unmapped-change"]
    assert unmapped == [], f"build/config files must not be unmapped production units: {unmapped}"


def _unit(path: str) -> ChangedUnit:
    return ChangedUnit(
        path=path, base_path=path, head_path=path, status="modified",
        base_lines=(), head_lines=(), base_symbols=(), head_symbols=(),
    )


def test_generated_code_is_not_a_documentable_unit(tmp_path: Path):
    """Generated code ships and serves traffic, but no person authored it and no Concept can
    honestly own it. Left classified as documentable it makes the coder's documentation gate
    unwinnable: one benchmark story's diff demanded 52 grounded symbols, 26 of them oapi-codegen
    internals like `(*UnescapedCookieParamError).Unwrap` and 16 of them mockery scaffolding.
    Excluding them leaves the ~16 hand-written symbols the author can actually document.

    Note this is *not* `_is_non_production_path`'s category — these files run in production.
    They are excluded because their contract lives in what they were generated from, which is
    itself in the diff as a real unit (the OpenAPI document, the proto, the mocked interface)."""
    for path in (
        "api/pkg/api/server.gen.go", "api/pkg/api/types.gen.go", "api/pkg/pb/link.pb.go",
        "api/pkg/pb/link.pb.gw.go", "api/internal/app/controllers/mocks/link_service.go",
        "web/src/__mocks__/client.ts", "web/src/api/schema.gen.ts",
        "app/lib/models/link.g.dart", "app/lib/models/link.freezed.dart",
        "svc/proto/link_pb2.py", "svc/proto/link_pb2_grpc.py",
        "web/generated/routes.ts", "api/vendor/example.com/dep/dep.go",
    ):
        assert _is_generated_unit(tmp_path, _unit(path)), f"{path} should read as generated"

    for path in (
        "api/internal/app/controllers/link.go", "api/internal/core/services/link/service.go",
        "api/openapi.yaml", "web/src/api/client.ts", "app/lib/models/link.dart",
        # A hand-written file whose *name* merely mentions a generated concept.
        "api/internal/codegen/code_generator.go", "web/src/mocks.ts",
    ):
        assert not _is_generated_unit(tmp_path, _unit(path)), f"{path} is hand-written code"


def test_the_generated_marker_is_read_when_the_filename_says_nothing(tmp_path: Path):
    """sqlc, ent and stringer emit ordinary-looking filenames, so the conventions alone would
    miss them. They all write Go's canonical banner, which is the one signal every generator
    agreed on — and the reason it exists is precisely to tell tools like this one."""
    (tmp_path / "db").mkdir()
    (tmp_path / "db/queries.go").write_text(
        "// Code generated by sqlc. DO NOT EDIT.\n// versions:\n//   sqlc v1.25.0\n\npackage db\n",
        encoding="utf-8",
    )
    (tmp_path / "db/store.go").write_text("package db\n\n// Store wraps queries.\n", "utf-8")

    assert _is_generated_unit(tmp_path, _unit("db/queries.go"))
    assert not _is_generated_unit(tmp_path, _unit("db/store.go"))
    # A path that resolves to nothing — a packet built between two revisions — falls back to
    # the conventions rather than raising.
    assert not _is_generated_unit(tmp_path, _unit("db/gone.go"))
    # A deletion carries `/dev/null` where a head path would go. Joined onto the root that
    # would read outside the repo, so it is refused before it gets there.
    deleted = ChangedUnit(
        path="db/store.go", base_path="db/store.go", head_path="/dev/null", status="deleted",
        base_lines=(1,), head_lines=(), base_symbols=("Store",), head_symbols=(),
    )
    assert not _is_generated_unit(tmp_path, deleted)


def test_context_ignores_generated_code_alongside_real_change(tmp_path: Path):
    """End-to-end: the story's own controller is owed, its generated server stubs are not."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/link.md").write_text(
        "---\ntype: concept\ntitle: Link\n---\n# Link\n\n- code: svc/controller.py::create_link\n",
        encoding="utf-8",
    )
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/controller.py").write_text("def create_link():\n    return 1\n", "utf-8")
    (tmp_path / "svc/schema_pb2.py").write_text("CREATE = 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/controller.py").write_text(
        "def create_link():\n    return 2\n", encoding="utf-8")
    (tmp_path / "svc/schema_pb2.py").write_text("CREATE = 1\nRESOLVE = 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"svc": ["svc"]})

    paths = [change["path"] for change in packet["changedCode"]]
    assert "svc/controller.py" in paths, paths
    assert "svc/schema_pb2.py" not in paths, paths
