from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ostler.qa.context import (
    CONTEXT_HEADING,
    OWED_HEADING,
    ChangedUnit,
    _is_generated_unit,
    _sort_key,
    _verification_refs,
    build_context,
    render_context,
    render_obligations,
    select_obligations,
    validate_context,
)


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
- tests: tests/test_service.py::test_create
- tests: tests/test_service.py::test_read
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


def test_a_deletion_needs_no_code_bullet_to_be_mapped(tmp_path: Path):
    """Documenting the absence of something is not documentation — a deletion is satisfied on
    its own. No node cites the deleted symbol at all, and the change must still not surface
    as `unmapped-change`.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    feature = tmp_path / "docs/features/demo/item.md"
    feature.write_text(
        """---
type: concept
title: Item
---
# Item

- code: app/other.py::keep_item
""",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.write_text("def create_item():\n    return 'old'\n", encoding="utf-8")
    other = tmp_path / "app/other.py"
    other.write_text("def keep_item():\n    return 'kept'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    source.unlink()
    _git(tmp_path, "add", "-A", "app")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert validate_context(packet) == []
    change = next(c for c in packet["changedCode"] if c["status"] == "deleted")
    assert change["baseSymbols"] == ["create_item"]
    codes = {finding["code"] for finding in packet.get("healthFindings", [])}
    assert "unmapped-change" not in codes


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
- verify: persists(subject="the saved item")
- verify: visible(locator="alert", text="could not save")
- tests: tests/test_items.py::test_save, tests/test_items.py::test_retry
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
    # `verify:` and `tests:` land in different places on purpose: the checks travel with the
    # obligations a scenario has to prove, the test paths only with the regression index.
    by_id = {item["id"]: item for item in packet["obligations"]}
    both = {
        'persists(subject="the saved item")',
        'visible(locator="alert", text="could not save")',
    }
    # Both `verify:` bullets sit under the one `does:`, so both bind to each of the claims it
    # nests — and to neither the node's own contract nor a claim written elsewhere.
    for suffix in (":does:1", ":does:2"):
        obligation = next(v for k, v in by_id.items() if k.endswith(suffix))
        assert {row["call"] for row in obligation["checksDeclared"]} == both
    contract = next(v for k, v in by_id.items()
                    if k.endswith("#save-item:contract"))
    assert "checksDeclared" not in contract
    assert not any("tests/test_items.py" in row for row in both)


def test_a_check_binds_to_the_claim_it_was_written_under(tmp_path: Path):
    """Two sibling claims, each with its own `verify:`, are two separately observed claims.

    A node-level list credits both checks to both claims, so the weaker one covers the claim
    the discriminating one was written for and the sharper one covers a claim nothing observes.
    Document order is what the author used to say which is which, and it is read here.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: endpoint
title: Claims
---
# Claims

## Invocations

### list-claims
- route: `GET /api/claims`
- code: app/list.py::list_claims
- verify: http_status(200, path="/api/claims")
- authorization: a holder reads only their own claims.
- verify: count(subject="claims", equals=1)
- authorization: an adjuster reads every claim on file.
- verify: count(subject="claims", equals=2)
""",
        encoding="utf-8",
    )
    (tmp_path / "app/list.py").write_text("def list_claims():\n    return []\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/list.py").write_text("def list_claims():\n    return [1]\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    calls = {
        item["id"].rsplit("#", 1)[-1]: [row["call"] for row in item.get("checksDeclared", [])]
        for item in packet["obligations"]
    }

    assert calls["list-claims:authorization:1"] == ['count(subject="claims", equals=1)']
    assert calls["list-claims:authorization:2"] == ['count(subject="claims", equals=2)']
    # Written before any claim, so it observes the node itself — where it has always belonged.
    assert calls["list-claims:contract"] == ['http_status(code=200, path="/api/claims")']


def test_a_contract_declaring_no_observation_is_a_health_warning(tmp_path: Path):
    """Not "cites no test" — a test citation proves nothing about the running product. The
    defect worth naming is an impacted contract no scenario can be held to."""
    (tmp_path / "docs/features/acme/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    doc = tmp_path / "docs/features/acme/screens/items.md"
    body = """---
type: screen
slug: items
title: Items
---
# Items

## Interactions

### save-item
- on: [items](#items)
- trigger: click
- does:
  - request: persist the item
- code: app/items.py::save_item
"""
    doc.write_text(body, encoding="utf-8")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    assert "missing-declared-check" in {f["kind"] for f in packet["healthFindings"]}

    doc.write_text(body + '- verify: persists(subject="the item")\n', encoding="utf-8")
    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    assert "missing-declared-check" not in {f["kind"] for f in packet["healthFindings"]}


def test_the_tenth_case_of_a_bullet_sorts_after_the_second():
    """Sorting obligation ids as plain strings puts `:10` between `:1` and `:2`.

    Harmless until a bullet enumerates ten cases, and then wrong in the one place it
    matters: the packet the planner reads and the packet a reviewer cites back number
    the same requirement differently.
    """
    node = "okf:docs/features/acme/concepts/store.md#put"
    ids = [f"{node}:raises:{index}" for index in (10, 2, 1, 11)] + [f"{node}:contract"]
    assert sorted(ids, key=_sort_key) == [
        f"{node}:contract",
        f"{node}:raises:1",
        f"{node}:raises:2",
        f"{node}:raises:10",
        f"{node}:raises:11",
    ]


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
- tests: tests/test_items.py::test_save
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
- tests: tests/test_accounts.py::test_login
- tests: mobile/test/accounts_test.dart::login succeeds
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


def test_the_toolchains_own_footprint_is_not_a_production_unit(tmp_path: Path):
    """farrier writes `agents.yml` and `.agents/`; the coder workflow's QA node writes
    `qa-stack.yml`; the QA stack's Firebase emulator drops `*-debug.log` in the repo root. All
    of them land in a story's diff, none of them is something a feature Concept can own.

    Classified as production they fail the ownership gate, and the only move left to an agent
    that must clear it is to invent a contract for them in the product's own feature docs. A
    greenfield run did that — a `#tooling` node in `docs/features/api/http/api.md` owning
    `qa-stack.yml`, `agents.yml` and `.agents/agents.mk` — which cleared the error and left a
    permanent `missing-verification` warning behind, since a stack manifest has no test to
    ground a verify reference on. The gate has to exclude them so it never asks.

    `.claude/` and `.githooks/` are the same category found later and the sharpest case,
    because what they hold is executable Python rather than a manifest: farrier installs skill
    bundles whose `scripts/check_*.py` are real linters, and `make hooks` points
    `core.hooksPath` at `.githooks/`. A greenfield story whose base commit predated the install
    drew six `unmapped-change` errors naming our own check scripts, and nothing the agent could
    write in the client's book would have been true."""
    from ostler.qa.context import _is_non_production_path as np

    for path in (
        "agents.yml", "qa-stack.yml", ".agents/agents.mk", ".agents/local.compose.yaml",
        ".opencode/opencode-loop/ses_123.json", "firebase-debug.log", "firestore-debug.log",
        "api/.mockery.yaml", "docs/doctor-waivers.json",
        ".claude/skills/demo-portability/scripts/check_portability.py",
        ".claude/settings.json", ".githooks/pre-commit", ".githooks/commit-msg",
    ):
        assert np(path), f"{path} is toolchain scaffolding and must not be a production unit"

    # Root-scoped on purpose: a nested file by the same name belongs to the product, not to us.
    for path in ("api/internal/agents.yml", "web/app/qa-stack.yml", "web/app/.claude/x.py"):
        assert not np(path), f"{path} is the product's own file and must stay production"


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


def test_deleted_binary_does_not_void_the_packet(tmp_path: Path):
    """A binary blob on the base side must not take the whole obligation packet down with it.

    `_revision_text` read `git show <base>:<path>` through `subprocess(text=True)`, so the
    bytes of a committed-then-deleted compiled artifact raised `UnicodeDecodeError` out of
    `build_context` — no packet, no `qa-okf-context.json`, and the docs gate failing with a
    codec error for a story whose real change was ordinary Go source next to it.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/link.md").write_text(
        "---\ntype: concept\ntitle: Link\n---\n# Link\n\n- code: svc/controller.py::create_link\n",
        encoding="utf-8",
    )
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/controller.py").write_text("def create_link():\n    return 1\n", "utf-8")
    # An ELF header: byte 24 is the entry point's first octet, which is where the strict
    # decode used to fail. Committed, then deleted — exactly how a stray `go build` lands.
    (tmp_path / "svc/server").write_bytes(b"\x7fELF\x02\x01\x01\x00" + bytes(16) + b"\xa0\x87G\x00")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/server").unlink()
    (tmp_path / "svc/controller.py").write_text(
        "def create_link():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"svc": ["svc"]})

    changes = {change["path"]: change for change in packet["changedCode"]}
    assert "svc/controller.py" in changes, changes
    assert changes["svc/controller.py"]["headSymbols"] == ["create_link"]
    # And it is not owed documentation: a blob with no readable side has no symbol to cite,
    # so demanding an owner for it is a gate no correct answer clears.
    assert "svc/server" not in changes, changes
    assert not [f for f in packet["healthFindings"] if f["severity"] == "error"]
    assert packet["obligations"]


def test_the_inventory_the_toolchain_writes_into_a_source_root_is_not_owed(tmp_path: Path):
    """`.source-inventory.json` is ours, not the product's, at whatever depth it lands.

    `okf_builder`'s coverage node writes it into each source root it scans, so the existing
    root-scoped `agents.yml`/`qa-stack.yml` rule never saw it and the ownership gate reported
    it as an unmapped production unit — inviting an agent to invent a feature Concept that
    owns the tool's own cache file.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/link.md").write_text(
        "---\ntype: concept\ntitle: Link\n---\n# Link\n\n- code: svc/controller.py::create_link\n",
        encoding="utf-8",
    )
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/controller.py").write_text("def create_link():\n    return 1\n", "utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/controller.py").write_text(
        "def create_link():\n    return 2\n", encoding="utf-8")
    (tmp_path / "svc/.source-inventory.json").write_text('{"symbols": []}\n', encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"svc": ["svc"]})

    paths = [change["path"] for change in packet["changedCode"]]
    assert "svc/controller.py" in paths, paths
    assert "svc/.source-inventory.json" not in paths, paths


def test_excluded_paths_leave_the_diff_before_anything_is_obligated_on_them(tmp_path: Path):
    """`head="WORKTREE"` is not a commit, so some of the dirt can be somebody else's.

    The caller that asked for this diffs one story's work against `HEAD`. When an earlier
    story died before its commit, its package is still on disk and lands in *this* story's
    packet — obligations to test code the story never wrote, forever, until a human commits
    or reverts it. The caller is the only party that can tell the two apart, so it names the
    paths and this drops them before the mapping runs: no changed unit, and no obligation
    derived from one either.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/link.md").write_text(
        "---\ntype: concept\ntitle: Link\n---\n# Link\n\n- code: svc/controller.py::create_link\n",
        encoding="utf-8",
    )
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/controller.py").write_text("def create_link():\n    return 1\n", "utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/controller.py").write_text(
        "def create_link():\n    return 2\n", encoding="utf-8")
    # The abandoned story's package: never committed, and nothing in the graph mentions it.
    (tmp_path / "svc/orphan.py").write_text("def strand():\n    return 3\n", encoding="utf-8")

    charged = build_context(tmp_path, base=base, source_roots={"svc": ["svc"]})
    assert "svc/orphan.py" in [c["path"] for c in charged["changedCode"]], charged["changedCode"]

    packet = build_context(
        tmp_path, base=base, source_roots={"svc": ["svc"]}, exclude_paths=["svc/orphan.py"]
    )

    paths = [change["path"] for change in packet["changedCode"]]
    assert "svc/controller.py" in paths, paths
    assert "svc/orphan.py" not in paths, paths
    # And it is gone from the findings too — an excluded path cannot be an unmapped unit.
    assert "orphan" not in json.dumps(packet["healthFindings"]), packet["healthFindings"]


def test_a_module_level_constant_grounds_like_any_other_declaration(tmp_path: Path):
    """A `code:` bullet naming a module-level binding is satisfiable.

    The existence check used to reuse the helper that attributes a *diff hunk* to the
    declaration whose body spans it — which can only ever report a class or a function, since
    a constant has no body to span. Every citation of one was therefore reported as resolving
    "in neither base nor head", a finding no rewrite of the book could clear: the docs gate
    burned its whole rework budget and failed the run.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "svc").mkdir()
    (tmp_path / "docs/features/demo/backend.md").write_text(
        "---\ntype: concept\ntitle: Backend\n---\n# Backend\n\n"
        "- code: `svc/backend.py::MANIFEST`, `svc/backend.py::ROUTES`, "
        "`svc/backend.py::serve`, `svc/backend.py::serve.Handler`\n",
        encoding="utf-8",
    )
    (tmp_path / "svc/backend.py").write_text(
        "MANIFEST = {'name': 'demo'}\nROUTES, ALIASES = {}, {}\n\n\n"
        "def serve(port):\n    class Handler:\n        pass\n\n    return Handler, port\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/backend.py").write_text(
        (tmp_path / "svc/backend.py").read_text(encoding="utf-8").replace("port", "bind"),
        encoding="utf-8",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["svc"]})

    dangling = [f for f in packet["healthFindings"] if f["kind"] == "dangling-grounding"]
    assert dangling == [], dangling


def test_a_citation_of_a_binary_file_that_exists_is_not_dangling(tmp_path: Path):
    """A `code:` bullet may cite a file nothing can decode — a `.docx` test fixture, a golden
    image, a compiled sample — and the gate has to see it.

    Existence used to be read off the *text* helpers, which answer "" for a file that is not
    UTF-8. Every citation of a binary was therefore permanently unsatisfiable: the file was
    right there in the worktree, the finding said it "resolves in neither base nor head", and
    the only rewrite that cleared it was deleting a true citation.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "svc/__fixtures__").mkdir(parents=True)
    (tmp_path / "docs/features/demo/backend.md").write_text(
        "---\ntype: concept\ntitle: Backend\n---\n# Backend\n\n"
        "- code: `svc/backend.py::serve`, `svc/__fixtures__/well-formed.docx`\n",
        encoding="utf-8",
    )
    (tmp_path / "svc/backend.py").write_text("def serve(port):\n    return port\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/backend.py").write_text("def serve(bind):\n    return bind\n", encoding="utf-8")
    (tmp_path / "svc/__fixtures__/well-formed.docx").write_bytes(b"PK\x03\x04\x00\xff\xfe\x00zip")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["svc"]})

    dangling = [f["ref"] for f in packet["healthFindings"] if f["kind"] == "dangling-grounding"]
    assert dangling == [], packet["healthFindings"]


def test_a_citation_of_a_file_that_is_nowhere_is_still_dangling(tmp_path: Path):
    """The widened existence check must not become "any path at all" — a citation of a file
    that is in neither revision nor the worktree is exactly what the finding is for."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "svc").mkdir()
    (tmp_path / "docs/features/demo/backend.md").write_text(
        "---\ntype: concept\ntitle: Backend\n---\n# Backend\n\n"
        "- code: `svc/backend.py::serve`, `svc/__fixtures__/never-written.docx`\n",
        encoding="utf-8",
    )
    (tmp_path / "svc/backend.py").write_text("def serve(port):\n    return port\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/backend.py").write_text("def serve(bind):\n    return bind\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["svc"]})

    dangling = [f["ref"] for f in packet["healthFindings"] if f["kind"] == "dangling-grounding"]
    assert dangling == ["svc/__fixtures__/never-written.docx"], packet["healthFindings"]


def test_a_citation_whose_definition_left_the_file_is_still_dangling(tmp_path: Path):
    """The widened check must not become "any name mentioned anywhere" — an import is not a
    declaration, so a symbol that moved out from under its citation stays a finding.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "svc").mkdir()
    (tmp_path / "docs/features/demo/backend.md").write_text(
        "---\ntype: concept\ntitle: Backend\n---\n# Backend\n\n"
        "- code: `svc/backend.py::MANIFEST`\n- code: `svc/backend.py::serve`\n",
        encoding="utf-8",
    )
    (tmp_path / "svc/backend.py").write_text(
        "from svc.data import MANIFEST\n\n\ndef serve():\n    return MANIFEST\n", encoding="utf-8"
    )
    (tmp_path / "svc/data.py").write_text("MANIFEST = {'name': 'demo'}\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "svc/backend.py").write_text(
        "from svc.data import MANIFEST\n\n\ndef serve():\n    return dict(MANIFEST)\n",
        encoding="utf-8",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["svc"]})

    dangling = [f["ref"] for f in packet["healthFindings"] if f["kind"] == "dangling-grounding"]
    assert dangling == ["svc/backend.py::MANIFEST"], packet["healthFindings"]


def test_a_backticked_verify_ref_keeps_the_commas_inside_its_test_name():
    """A comma in a test title is content, not a separator — the span boundary says so.

    Real titles in a browser suite read like `> exports the live editor through canonical XML,
    revokes its object URL, and clears the named status`. Scanning the raw bullet with one
    regex cut every one of them at the first comma, and the grounding gate then reported the
    truncated name as citing a test that does not exist. A story lost four documentation
    review passes to that, being told to repair a citation that was already correct.
    """
    backticked = (
        "`docs-app/app/lib/drafts.test.ts::describe(\"createPairedDrafts\") > generates once, "
        "cloning the input independently` and `docs-app/app/x.browser.test.tsx::describe(\"S\") > b`"
    )
    assert _verification_refs({"bullets": {"tests": backticked}}) == [
        'docs-app/app/lib/drafts.test.ts::describe("createPairedDrafts") > generates once, '
        "cloning the input independently",
        'docs-app/app/x.browser.test.tsx::describe("S") > b',
    ]
    # Prose in backticks is not a citation, and a bullet citing without them still splits on
    # the comma — nothing marks where a target ends there, so that reading has to stay lossy.
    assert _verification_refs({"bullets": {"tests": "`not a citation at all`"}}) == []
    assert _verification_refs(
        {"bullets": {"tests": "tests/test_items.py::test_save, tests/test_items.py::test_retry"}}
    ) == ["tests/test_items.py::test_save", "tests/test_items.py::test_retry"]


def _packet_with_a_wrapped_requirement() -> dict:
    """A packet whose one context-only entry wraps, which is the case the headings exist for."""
    return {
        "obligations": [
            {
                "id": "okf:docs/features/api/store.md#put:contract",
                "kind": "contract",
                "node": "docs/features/api/store.md",
                "requirement": "Put",
                "required": True,
                "locators": {"role": ["button"]},
            },
            {
                "id": "okf:docs/features/app/cold-start.md:end:1",
                "kind": "end",
                "node": "docs/features/app/cold-start.md",
                "requirement": "the visitor sees the requested content render, not a blank\npage",
                "required": False,
            },
        ]
    }


def test_the_owed_split_survives_a_requirement_that_wraps():
    """The class of an obligation is a heading, not a suffix on its line.

    A requirement is rendered verbatim and wraps where the book wrapped it, so the old
    ``_(context only)_`` suffix landed on a continuation line: the count of entry-start lines
    and the count of marker lines disagreed, and a planner deriving its owed set with a
    per-line grep derived the wrong one. Under a heading, wrapping cannot move an entry.
    """
    rendered = render_context(_packet_with_a_wrapped_requirement())
    owed, context = rendered.split(CONTEXT_HEADING)
    assert OWED_HEADING in owed
    assert "okf:docs/features/api/store.md#put:contract" in owed
    assert "okf:docs/features/app/cold-start.md:end:1" not in owed
    assert "okf:docs/features/app/cold-start.md:end:1" in context
    # The wrapped tail stays in the section its entry started in, and carries no marker of its own.
    assert "page" in context.split("okf:docs/features/app/cold-start.md:end:1")[1]
    assert "context only" not in rendered


def test_an_empty_section_still_says_so():
    rendered = render_context({"obligations": []})
    assert rendered.count("- (none)") >= 2


def test_selecting_obligations_filters_and_pages_without_rebuilding():
    """``build_context`` walks the diff and the graph; reading a slice of the result must not.

    The reader is an agent that cannot hold a packet where 151 of 176 entries are context, so
    the useful unit is a query over what was already written.
    """
    packet = _packet_with_a_wrapped_requirement()
    owed, matched = select_obligations(packet, required=True)
    assert [item["id"] for item in owed] == ["okf:docs/features/api/store.md#put:contract"]
    assert matched == 1
    _, matched = select_obligations(packet, required=False)
    assert matched == 1
    # No `required` filter is every obligation, which is what the whole file already said.
    _, matched = select_obligations(packet)
    assert matched == 2
    # `node` is a substring of the node path, not a glob — a caller types it at a shell.
    _, matched = select_obligations(packet, node="docs/features/app")
    assert matched == 1
    _, matched = select_obligations(packet, kind="contract")
    assert matched == 1
    # A page reports the size of the whole match, not of the window, or paging cannot terminate.
    page, matched = select_obligations(packet, offset=1, limit=5)
    assert len(page) == 1 and matched == 2
    page, matched = select_obligations(packet, offset=9)
    assert page == [] and matched == 2


def test_rendering_a_slice_can_drop_the_locator_bullets():
    packet = _packet_with_a_wrapped_requirement()
    page, _ = select_obligations(packet, required=True)
    assert any("role:" in line for line in render_obligations(page))
    assert not any("role:" in line for line in render_obligations(page, locators=False))
    assert render_obligations([]) == ["- (none)"]


def test_a_leading_fixture_is_ambient_while_a_nested_one_binds_to_its_claim(tmp_path: Path):
    """The asymmetry between the two things a bullet above every claim can be.

    A `verify:` written there observes the node's own contract and nothing else — an observation
    is specific by nature, and crediting it to claims it was not written for is how a weak check
    comes to cover a sharp claim. An arrangement is the opposite: the state the node as a whole is
    documented in is the state every claim it mints is documented in, so a leading `fixture:` fans
    out and a nested one adds to it rather than replacing it.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: endpoint
title: Claims
---
# Claims

## Invocations

### list-claims
- route: `GET /api/claims`
- code: app/list.py::list_claims
- fixture: three-identities — the adjuster and both holders exist
- authorization: a holder reads only their own claims.
- authorization: an adjuster reads every claim on file.
- fixture: seeded-ledger 2 — two claims on file
""",
        encoding="utf-8",
    )
    (tmp_path / "app/list.py").write_text("def list_claims():\n    return []\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/list.py").write_text("def list_claims():\n    return [1]\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    arranged = {
        item["id"].rsplit("#", 1)[-1]: [
            (row["name"], tuple(row["args"])) for row in item.get("fixturesDeclared", [])
        ]
        for item in packet["obligations"]
    }

    ambient = ("three-identities", ())
    assert arranged["list-claims:contract"] == [ambient]
    assert arranged["list-claims:authorization:1"] == [ambient]
    # The second claim is documented in the seeded ledger *as well as* the identities — an
    # arrangement written under it narrows nothing, it adds a second state to reach.
    assert arranged["list-claims:authorization:2"] == [ambient, ("seeded-ledger", ("2",))]

    provides = {
        row["name"]: row["provides"]
        for item in packet["obligations"]
        for row in item.get("fixturesDeclared", [])
    }
    assert provides["three-identities"] == "the adjuster and both holders exist"
    assert provides["seeded-ledger"] == "two claims on file"
