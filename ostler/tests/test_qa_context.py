from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ostler import registry
from ostler.model import load
from ostler.qa.context import (
    CONTEXT_HEADING,
    OWED_HEADING,
    ChangedUnit,
    _acceptance_criteria,
    _book_relative,
    _book_root,
    _graph_at_revision,
    _is_generated_unit,
    _locators,
    _navigation,
    _sort_key,
    _verification_refs,
    build_context,
    render_context,
    render_obligations,
    select_obligations,
    validate_context,
)

from conftest import write


def test_story_criteria_keep_functional_and_non_functional_classification(tmp_path: Path):
    story = tmp_path / "story.md"
    story.write_text(
        "# Story: Parser\n\n"
        "## Acceptance Criteria\n\n"
        "- The compiler emits a safe AST.\n\n"
        "## Non-Functional Acceptance Criteria\n\n"
        "- Existing decimal results remain byte-identical.\n",
        encoding="utf-8",
    )

    assert _acceptance_criteria(story) == [
        {
            "id": "ac:1",
            "requirement": "The compiler emits a safe AST.",
            "kind": "behavioral",
            "category": "functional",
        },
        {
            "id": "nfac:1",
            "requirement": "Existing decimal results remain byte-identical.",
            "kind": "behavioral",
            "category": "non-functional",
        },
    ]


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
        {"kind": "file-owner", "ref": "app/config.ts", "key": "code"},
    ]


def _owning_repo(tmp_path: Path, book: str, cited: str, *, node_file: str = "node.md") -> str:
    """A repo with one book file and one cited file, committed; returns the base sha."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo" / node_file).write_text(book, encoding="utf-8")
    target = tmp_path / cited
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    target.write_text("after\n", encoding="utf-8")
    return base


def test_an_openapi_bullet_owns_the_document_it_names(tmp_path: Path):
    """A server documented against its schema is reached when the schema changes, with no
    second `code:` citation repeating the path — the registry says `openapi:` owns."""
    base = _owning_repo(
        tmp_path,
        "---\ntype: server\ntitle: API\n---\n# API\n\n"
        "- code: `app/main.py`\n- openapi: `app/openapi.yaml`\n",
        "app/openapi.yaml",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert "unmapped-change" not in [f["kind"] for f in packet["healthFindings"]]
    reasons = [r for node in packet["directNodes"] for r in node["reasons"]]
    assert reasons == [{"kind": "file-owner", "ref": "app/openapi.yaml", "key": "openapi"}]
    assert validate_context(packet) == []


def test_a_format_file_bullet_owns_the_file(tmp_path: Path):
    base = _owning_repo(
        tmp_path,
        "---\ntype: format\ntitle: Ledger file\n---\n# Ledger file\n\n"
        "- file: `app/ledger.schema.json`\n",
        "app/ledger.schema.json",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    reasons = [r for node in packet["directNodes"] for r in node["reasons"]]
    assert reasons == [{"kind": "file-owner", "ref": "app/ledger.schema.json", "key": "file"}]


def test_a_declared_config_path_is_a_production_unit(tmp_path: Path):
    """A `Pulumi.<stack>.yaml` is dropped from the change surface by the non-production filter
    — until an environment declares it under `config:`. Then the change reaches the node, and
    the node is required: the config key owns like `code:` does."""
    base = _owning_repo(
        tmp_path,
        "---\ntype: environment\ntitle: Dev stack\n---\n# Dev stack\n\n"
        "- code: `infra/main.go`\n- config: `infra/Pulumi.dev.yaml`\n",
        "infra/Pulumi.dev.yaml",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["infra"]})

    assert "unmapped-change" not in [f["kind"] for f in packet["healthFindings"]]
    assert [node["reasons"] for node in packet["directNodes"]] == [
        [{"kind": "file-owner", "ref": "infra/Pulumi.dev.yaml", "key": "config"}]
    ]
    assert [change["path"] for change in packet["changedCode"]] == ["infra/Pulumi.dev.yaml"]
    assert validate_context(packet) == []


def test_an_undeclared_stack_config_stays_filtered(tmp_path: Path):
    """Without the declaration the filter keeps its default: the stack config is not a
    production unit, so it is neither mapped nor an `unmapped-change`."""
    base = _owning_repo(
        tmp_path,
        "---\ntype: environment\ntitle: Dev stack\n---\n# Dev stack\n\n"
        "- code: `infra/main.go`\n",
        "infra/Pulumi.dev.yaml",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["infra"]})

    assert packet["changedCode"] == []
    assert packet["directNodes"] == []
    assert "unmapped-change" not in [f["kind"] for f in packet["healthFindings"]]


def test_a_config_file_shared_by_two_nodes_is_context_evidence(tmp_path: Path):
    """The shared-file demotion applies to `config:` as to any bare-file citation: two nodes
    naming one config file both stay in the packet, neither owed live evidence for it."""
    base = _owning_repo(
        tmp_path,
        "---\ntype: environment\ntitle: Dev stack\n---\n# Dev stack\n\n"
        "- code: `infra/main.go`\n- config: `infra/Pulumi.dev.yaml`\n",
        "infra/Pulumi.dev.yaml",
    )
    (tmp_path / "docs/features/demo/other.md").write_text(
        "---\ntype: environment\ntitle: Other stack\n---\n# Other stack\n\n"
        "- code: `infra/other.go`\n- config: `infra/Pulumi.dev.yaml`\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "second owner")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "infra/Pulumi.dev.yaml").write_text("again\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["infra"]})

    assert len(packet["directNodes"]) == 2
    assert packet["obligations"], "both nodes stay in the packet"
    assert all(not item["required"] for item in packet["obligations"]), packet["obligations"]


def test_a_files_own_sections_citing_one_symbol_stay_one_family(tmp_path: Path):
    """A `cli` file and its own `### ` command sections, all citing the same exact symbol,
    are one documented surface, not four independent owners — `_family_root` collapses
    a section id `path#anchor` onto its containing file id when that file is itself one of
    the citers, so the raw citer count (4) never reaches `_CONTAINER_FANOUT` and the
    obligations stay required."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/cli.md").write_text(
        "---\ntype: cli\nslug: c\ntitle: C\n---\n# C\n\n"
        "- code: `app/cli.py::run`\n\n"
        "## Commands\n\n"
        "### one\n- code: `app/cli.py::run`\n\n"
        "### two\n- code: `app/cli.py::run`\n\n"
        "### three\n- code: `app/cli.py::run`\n",
        encoding="utf-8",
    )
    source = tmp_path / "app/cli.py"
    source.parent.mkdir(parents=True)
    source.write_text("def run():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("def run():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert len(packet["directNodes"]) == 4  # the file plus its three command sections
    assert all(item["required"] for item in packet["obligations"]), packet["obligations"]
    command_obligations = [item for item in packet["obligations"] if item["nodeType"] == "command"]
    assert len(command_obligations) == 3


def test_cli_binaries_key_the_owning_files_binary_by_shared_path(tmp_path: Path):
    """A `command` section shares its owning `cli` file's `path` (`graph.py`'s `_node_dict`),
    so `context.py`'s `_cli_binaries` can key a `run:` obligation's tool by that same `source`
    without walking `parent` pointers. Two `cli` files, one that declares `binary:` and one that
    leaves it empty — the scaffolded-empty bullet must not be mistaken for a declared value
    (`_values`, not `key in bullets`), so the second file is simply absent from the map."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/tally.md").write_text(
        "---\ntype: cli\nslug: tally\ntitle: Tally\n---\n# Tally\n\n"
        "- binary: tally\n- code: `app/tally.py::run`\n\n"
        "## Commands\n\n"
        "### init\n- code: `app/tally.py::run`\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/unnamed.md").write_text(
        "---\ntype: cli\nslug: unnamed\ntitle: Unnamed\n---\n# Unnamed\n\n"
        "- code: `app/unnamed.py::run`\n\n"
        "## Commands\n\n"
        "### go\n- code: `app/unnamed.py::run`\n",
        encoding="utf-8",
    )
    for rel, body in (
        ("app/tally.py", "def run():\n    return 'old'\n"),
        ("app/unnamed.py", "def run():\n    return 'old'\n"),
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/tally.py").write_text("def run():\n    return 'new'\n", encoding="utf-8")
    (tmp_path / "app/unnamed.py").write_text("def run():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert packet["cliBinaries"] == {"docs/features/demo/tally.md": "tally"}


def test_six_unrelated_nodes_citing_one_symbol_still_demote(tmp_path: Path):
    """Six genuinely unrelated nodes — no containment, no `extends:` — citing the same exact
    symbol is the sprawl `_CONTAINER_FANOUT` exists to catch, and family-collapsing must not
    blunt it: none of them share a declared edge, so each is its own family and the fan-out
    demotion still fires. A seventh, unrelated node with its own required obligation keeps the
    tree-wide required set non-empty, so the `shared-symbol-floor` safety net does not mask
    the demotion this test is checking for."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    for index in range(6):
        (tmp_path / f"docs/features/demo/item{index}.md").write_text(
            f"---\ntype: concept\ntitle: Item {index}\n---\n# Item {index}\n\n"
            "- code: `app/service.py::shared`\n",
            encoding="utf-8",
        )
    (tmp_path / "docs/features/demo/other.md").write_text(
        "---\ntype: concept\ntitle: Other\n---\n# Other\n\n"
        "- code: `app/other.py::alone`\n",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def shared():\n    return 'old'\n", encoding="utf-8")
    other = tmp_path / "app/other.py"
    other.write_text("def alone():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("def shared():\n    return 'new'\n", encoding="utf-8")
    other.write_text("def alone():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert len(packet["directNodes"]) == 7
    shared_obligations = [item for item in packet["obligations"] if "/item" in item["node"]]
    assert len(shared_obligations) == 6
    assert all(not item["required"] for item in shared_obligations), shared_obligations
    other_obligation = next(item for item in packet["obligations"] if item["node"].endswith("other.md"))
    assert other_obligation["required"]


def test_concepts_chained_by_extends_citing_one_symbol_stay_one_family(tmp_path: Path):
    """Six `concept` nodes chained by `extends:` are one documented thing, not six owners.

    `extends:` is defined as specialization on all four types that own it — `concept`,
    `component`, `interaction`, `invocation` — and the walk asks only whether the edge lands
    inside the group, with no type filter. So `_family_root` collapses the chain whatever
    the type: six specializations of one concept
    citing one symbol never reach `_CONTAINER_FANOUT`, and their obligations stay required.
    Gate the walk on the two arm types instead and this test demotes all six.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item0.md").write_text(
        "---\ntype: concept\ntitle: Item 0\n---\n# Item 0\n\n"
        "- code: `app/service.py::shared`\n",
        encoding="utf-8",
    )
    for index in range(1, 6):
        (tmp_path / f"docs/features/demo/item{index}.md").write_text(
            f"---\ntype: concept\ntitle: Item {index}\n---\n# Item {index}\n\n"
            f"- extends: [Item {index - 1}](item{index - 1}.md)\n"
            "- code: `app/service.py::shared`\n",
            encoding="utf-8",
        )
    # The same seventh, unrelated node the sibling demotion test carries, and for the same
    # reason: it keeps the tree-wide required set non-empty so `shared-symbol-floor` cannot
    # hold these six up on its own and mask what the family walk decided.
    (tmp_path / "docs/features/demo/other.md").write_text(
        "---\ntype: concept\ntitle: Other\n---\n# Other\n\n"
        "- code: `app/other.py::alone`\n",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def shared():\n    return 'old'\n", encoding="utf-8")
    other = tmp_path / "app/other.py"
    other.write_text("def alone():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("def shared():\n    return 'new'\n", encoding="utf-8")
    other.write_text("def alone():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    shared_obligations = [item for item in packet["obligations"] if "/item" in item["node"]]
    assert len(shared_obligations) == 6
    assert all(item["required"] for item in shared_obligations), shared_obligations


def test_concepts_chained_by_same_as_citing_one_symbol_stay_one_family(tmp_path: Path):
    """Four `concept` nodes reciprocally chained by `same-as:` (A<->B, B<->C, C<->D) are one
    documented thing written four times, not four owners. `same-as:` is multi-valued and
    per-edge — B and C each name only their two immediate neighbors, never every member of the
    family — so `_family_root` must walk the whole connected component and converge every
    member on one deterministic representative (`min(ids)`), not just a node's own direct
    same-as targets. All four citing one symbol must never reach `_CONTAINER_FANOUT`. And
    because `_obligations` mints its id off the same `_same_as_component` representative, the
    four members' identical `contract` claims collapse to the one obligation the dedupe step
    keeps, not four copies of it — required stays true on that one obligation."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item0.md").write_text(
        "---\ntype: concept\ntitle: Item 0\n---\n# Item 0\n\n"
        "- code: `app/service.py::shared`\n"
        "- same-as: [Item 1](item1.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/item1.md").write_text(
        "---\ntype: concept\ntitle: Item 1\n---\n# Item 1\n\n"
        "- code: `app/service.py::shared`\n"
        "- same-as: [Item 0](item0.md)\n"
        "- same-as: [Item 2](item2.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/item2.md").write_text(
        "---\ntype: concept\ntitle: Item 2\n---\n# Item 2\n\n"
        "- code: `app/service.py::shared`\n"
        "- same-as: [Item 1](item1.md)\n"
        "- same-as: [Item 3](item3.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/demo/item3.md").write_text(
        "---\ntype: concept\ntitle: Item 3\n---\n# Item 3\n\n"
        "- code: `app/service.py::shared`\n"
        "- same-as: [Item 2](item2.md)\n",
        encoding="utf-8",
    )
    # The same unrelated node the extends-chain test carries, and for the same reason: it
    # keeps the tree-wide required set non-empty so `shared-symbol-floor` cannot hold these
    # four up on its own and mask what the family walk decided.
    (tmp_path / "docs/features/demo/other.md").write_text(
        "---\ntype: concept\ntitle: Other\n---\n# Other\n\n"
        "- code: `app/other.py::alone`\n",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.parent.mkdir(parents=True)
    source.write_text("def shared():\n    return 'old'\n", encoding="utf-8")
    other = tmp_path / "app/other.py"
    other.write_text("def alone():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("def shared():\n    return 'new'\n", encoding="utf-8")
    other.write_text("def alone():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    shared_obligations = [item for item in packet["obligations"] if "/item" in item["node"]]
    assert len(shared_obligations) == 1
    assert all(item["required"] for item in shared_obligations), shared_obligations


def _same_as_button_screens(
    tmp_path: Path, names: list[str], *, extra_bullets: dict[str, str] | None = None
) -> str:
    """`names` screens, each with a `save-button` component reciprocally `same-as:`-linked to
    every other member and grounded on its own file — so each enters the packet independently
    of the relation, the invariant `_same_as_component` collapsing must not disturb. Returns
    the base sha, after which every screen's own grounding file has changed so every member is
    `required`.

    `extra_bullets` lets one test add a bullet only some members declare, to exercise the
    "silence is legal in a family" half of the collapse.
    """
    extra_bullets = extra_bullets or {}
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    for name in names:
        others = [other for other in names if other != name]
        same_as = "".join(
            f"- same-as: [Save button]({other}.md#save-button)\n" for other in others
        )
        (tmp_path / f"docs/features/demo/{name}.md").write_text(
            f"---\ntype: screen\ntitle: {name}\n---\n# {name}\n\n"
            "## Components\n\n"
            "### save-button\n"
            "- role: button\n"
            "- name: Save item\n"
            f"{extra_bullets.get(name, '')}"
            f"{same_as}"
            f"- code: app/{name}.py::save_item\n",
            encoding="utf-8",
        )
        (tmp_path / f"app/{name}.py").write_text(
            "def save_item():\n    return 'old'\n", encoding="utf-8"
        )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    for name in names:
        (tmp_path / f"app/{name}.py").write_text(
            "def save_item():\n    return 'new'\n", encoding="utf-8"
        )
    return base


def test_same_as_pair_collapses_onto_the_lower_member_id(tmp_path: Path):
    """Two screens whose `save-button` is one documented control, `same-as:`-linked, mint one
    obligation per normative key — not one per occurrence — anchored on `min()` of the family
    (`screen-a` sorts before `screen-b`)."""
    base = _same_as_button_screens(tmp_path, ["screen-a", "screen-b"])

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    family_obligations = [
        item for item in packet["obligations"] if item["node"].endswith("#save-button")
    ]
    ids = sorted(item["id"] for item in family_obligations)
    assert ids == [
        "okf:docs/features/demo/screen-a.md#save-button:contract",
        "okf:docs/features/demo/screen-a.md#save-button:name:1",
        "okf:docs/features/demo/screen-a.md#save-button:role:1",
    ]


def test_same_as_triple_collapses_to_one_obligation_not_three(tmp_path: Path):
    """A three-member family (`screen-a`/`screen-b`/`screen-c`, each reciprocally `same-as:`
    the other two) still mints one obligation per key, never three — and because each member's
    own `_obligations` call computes the representative independently off its own id, the
    three members landing on the same `screen-a`-rooted ids also shows the id does not depend
    on which member the walk happened to start from."""
    base = _same_as_button_screens(tmp_path, ["screen-a", "screen-b", "screen-c"])

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    family_obligations = [
        item for item in packet["obligations"] if item["node"].endswith("#save-button")
    ]
    assert len(family_obligations) == 3
    assert all(
        item["id"].startswith("okf:docs/features/demo/screen-a.md#save-button:")
        for item in family_obligations
    )


def test_same_as_member_contributes_a_key_its_siblings_leave_silent(tmp_path: Path):
    """`same-as:` exists so a repeat can be written cheaply — a member is allowed to state
    less than its siblings. `screen-b` (not the family representative) is the only member that
    writes `keyboard:`; the packet must still owe a `:keyboard:1` obligation, under the
    representative's id, because every member is visited and dedupe only collapses agreement,
    it never discards what only one member said."""
    base = _same_as_button_screens(
        tmp_path,
        ["screen-a", "screen-b"],
        extra_bullets={"screen-b": "- keyboard: Tab then Enter\n"},
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    family_obligations = [
        item for item in packet["obligations"] if item["node"].endswith("#save-button")
    ]
    ids = sorted(item["id"] for item in family_obligations)
    assert ids == [
        "okf:docs/features/demo/screen-a.md#save-button:contract",
        "okf:docs/features/demo/screen-a.md#save-button:keyboard:1",
        "okf:docs/features/demo/screen-a.md#save-button:name:1",
        "okf:docs/features/demo/screen-a.md#save-button:role:1",
    ]
    keyboard = next(item for item in family_obligations if item["kind"] == "keyboard")
    # Minted while visiting screen-b's own bullets, not screen-a's — screen-a never wrote a
    # `keyboard:` bullet at all, so a design that merged onto the representative node instead
    # of visiting every member would have missed this obligation entirely.
    assert keyboard["node"] == "docs/features/demo/screen-b.md#save-button"


def test_a_node_with_no_same_as_family_keeps_its_own_obligation_id(tmp_path: Path):
    """The regression guard for every frozen plan that predates this collapse: a node that
    declares no `same-as:` is its own one-member family, so `min()` of its component is its
    own id and its obligation ids are exactly what they were before this change existed."""
    base = _same_as_button_screens(tmp_path, ["screen-solo"])

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    family_obligations = [
        item for item in packet["obligations"] if item["node"].endswith("#save-button")
    ]
    ids = sorted(item["id"] for item in family_obligations)
    assert ids == [
        "okf:docs/features/demo/screen-solo.md#save-button:contract",
        "okf:docs/features/demo/screen-solo.md#save-button:name:1",
        "okf:docs/features/demo/screen-solo.md#save-button:role:1",
    ]


def test_one_path_cited_under_two_owning_keys_is_one_owner(tmp_path: Path):
    """Citing the schema under both `code:` and `openapi:` is one owner, not two — otherwise
    the shared-file demotion would read a single node's double citation as a shared file."""
    base = _owning_repo(
        tmp_path,
        "---\ntype: server\ntitle: API\n---\n# API\n\n"
        "- code: `app/openapi.yaml`\n- openapi: `app/openapi.yaml`\n",
        "app/openapi.yaml",
    )

    packet = build_context(tmp_path, base=base, source_roots={"demo": ["app"]})

    assert [node["reasons"] for node in packet["directNodes"]] == [
        [{"kind": "file-owner", "ref": "app/openapi.yaml", "key": "code"}]
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


_REVISED_SCREEN = """---
type: screen
title: Items
---
# Items

## Components

### empty-notice
- role: paragraph
- name: {name}
- selector: p.empty-notice
- states: shown while no item is on file
- code: app/items.py::render_empty
"""


def test_an_edited_bullet_carries_only_the_head_revisions_value(tmp_path: Path):
    """A bullet's value is a property of one revision, and the union of two is a value no
    revision states.

    The base graph is unioned into the packet so a node the change *deleted* can still be
    described. A node present in both revisions is a different case: it was edited, and the
    edit is the thing under test. Pooling the two readings of an edited bullet puts the
    pre-edit value first, which is what the locator compiler reads — so the run meant to
    verify the repair addresses the element by the name the repair removed, and the extra
    reading mints a `:name:2` obligation against a claim the book no longer makes.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    book = tmp_path / "docs/features/acme/gui/screens/items.md"
    book.write_text(_REVISED_SCREEN.format(name="No items are on file yet."), encoding="utf-8")
    (tmp_path / "app/items.py").write_text("def render_empty():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    # The repair: the paragraph has no accessible name, and the book now says so.
    book.write_text(_REVISED_SCREEN.format(name="none"), encoding="utf-8")
    (tmp_path / "app/items.py").write_text("def render_empty():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    by_id = {item["id"]: item for item in packet["obligations"]}
    node = "okf:docs/features/acme/gui/screens/items.md#empty-notice"
    assert by_id[f"{node}:name:1"]["requirement"] == "none"
    assert f"{node}:name:2" not in by_id, "the pre-edit value minted an obligation of its own"
    assert by_id[f"{node}:name:1"]["locators"]["name"] == ["none"]


def test_a_node_the_change_deleted_is_still_described_by_the_base_revision(tmp_path: Path):
    """The counterpart, and the reason the merge exists at all: head wins per key only for a
    node head still has. A node the change removed keeps every bullet the base stated, or the
    packet cannot say what went away.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    book = tmp_path / "docs/features/acme/gui/screens/items.md"
    book.write_text(_REVISED_SCREEN.format(name="No items are on file yet."), encoding="utf-8")
    (tmp_path / "app/items.py").write_text("def render_empty():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    book.write_text(
        """---
type: screen
title: Items
---
# Items
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text("def render_empty():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    by_id = {item["id"]: item for item in packet["obligations"]}
    node = "okf:docs/features/acme/gui/screens/items.md#empty-notice"
    assert by_id[f"{node}:name:1"]["locators"]["name"] == ["No items are on file yet."]


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


def test_a_channel_endpoints_message_mints_one_obligation_per_frame(tmp_path: Path):
    """`message:` is `nested=True, entries=True, normative=True`: a websocket returns
    differently-shaped frames, each a thing with its own claims, so the grammar mints one
    obligation per frame — not one per grandchild (the flat `nested` shape) and not one for
    the whole block (`record`). The obligation id carries the per-key ordinal, exactly as
    `does:1`/`does:2` do above, so it is `message:1`/`message:2` here, one per entry, never
    `message:3` or `message:4` for the frames' own `direction:`/`payload:` children."""
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/stream.md").write_text(
        """---
type: server
title: Stream
---
# Stream

## Endpoints

### stream-updates
- channel: ws://events
- message:
  - update
    - direction: server-to-client
    - payload: `Update`
  - ack
    - direction: client-to-server
    - payload: `Ack`
- code: app/stream.py::stream_updates
""",
        encoding="utf-8",
    )
    (tmp_path / "app/stream.py").write_text(
        "def stream_updates():\n    return 1\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/stream.py").write_text(
        "def stream_updates():\n    return 2\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    by_id = {item["id"]: item for item in packet["obligations"]}
    message_obligations = {k: v for k, v in by_id.items() if ":message:" in k}

    assert set(message_obligations) == {
        "okf:docs/features/acme/http/stream.md#stream-updates:message:1",
        "okf:docs/features/acme/http/stream.md#stream-updates:message:2",
    }
    assert message_obligations[
        "okf:docs/features/acme/http/stream.md#stream-updates:message:1"
    ]["requirement"] == "update"
    assert message_obligations[
        "okf:docs/features/acme/http/stream.md#stream-updates:message:2"
    ]["requirement"] == "ack"


def test_a_repeated_component_lifts_its_family_contract_onto_the_obligation(tmp_path: Path):
    """A `one-per:` node's obligations carry the compiled repeat block, camelCase like the packet.

    The block is what lets `qa plan` hold a covering scenario to concrete instances without
    re-reading the book: the bindable template holes, the distinctness claim, and the variant
    axis all travel with the obligation. A node outside any repeated scope carries no block at
    all, so a book that never declares `one-per:` produces the packet it always did.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/gui/screens/planner.md").write_text(
        """---
type: screen
title: Planner
---
# Planner

## Components

### stage-row
- role: row
- name: `{stage.name} stage row`
- one-per: `stage` — one row per stage the project declares
- unique-by: `stage.id`
- variants: `stage.kind = draft | active`
- states: expanded while selected
- code: app/planner.py::render_stage

### add-stage-button
- role: button
- name: Add stage
- code: app/planner.py::render_stage

## Interactions

### toggle-stage
- on: [stage-row](#stage-row)
- trigger: click
- does:
  - request: expand the stage
- code: app/planner.py::render_stage
""",
        encoding="utf-8",
    )
    (tmp_path / "app/planner.py").write_text(
        "def render_stage():\n    return 'old'\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/planner.py").write_text(
        "def render_stage():\n    return 'new'\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    by_id = {item["id"]: item for item in packet["obligations"]}
    row = next(v for k, v in by_id.items() if k.endswith("#stage-row:contract"))
    repeat = row["repeat"]
    assert repeat["onePer"] == "stage"
    assert repeat["binds"] == ["stage.name"]
    assert repeat["template"] == "{stage.name} stage row"
    assert repeat["iterates"] == "stage"
    assert repeat["segments"][0] == {"kind": "bind", "path": "stage.name"}
    assert repeat["uniqueBy"] == "stage.id"
    assert repeat["variants"] == {"path": "stage.kind", "values": ["draft", "active"]}
    # Every obligation the node mints repeats with it — the states bullet is per instance too.
    states = next(v for k, v in by_id.items() if "#stage-row:states" in k)
    assert states["repeat"]["onePer"] == "stage"
    # Scope flows down containment and `parent:` links only — an `on:` edge is a reference,
    # not nesting, so the interaction stays unrepeated, exactly as the doctor reads it.
    toggle = next(v for k, v in by_id.items() if k.endswith("#toggle-stage:contract"))
    assert "repeat" not in toggle
    # A sibling outside the repeat carries no block at all.
    button = next(v for k, v in by_id.items() if k.endswith("#add-stage-button:contract"))
    assert "repeat" not in button
    # The rendered packet says so where a planner reads the obligation.
    lines = render_obligations([row])
    assert any(
        "repeated: one per `stage`" in line
        and "binds `stage.name`" in line
        and "unique by `stage.id`" in line
        and "variants `stage.kind` = draft | active" in line
        for line in lines
    )


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
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
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


def test_a_check_on_one_normative_key_does_not_silence_another(tmp_path: Path):
    """A node with two normative keys and one `verify:` must warn on the uncovered key alone.

    `keyboard:` and `does:` are both normative on `interaction`. The `verify:` here is written
    under `does:` alone, so it covers that claim and leaves `keyboard:`'s claim uncovered — a
    node-level predicate that asks only "does this node carry any `verify:`" cannot see that,
    because it does."""
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
- keyboard: Enter
- does:
  - request: persist the item
- verify: persists(subject="the item")
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
    findings = [f for f in packet["healthFindings"] if f["kind"] == "missing-declared-check"]

    assert len(findings) == 1
    assert findings[0]["key"] == "keyboard"


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
    """farrier writes `agents.yml` and `.agents/`; a coder run historically left a
    `qa-stack.yml` beside them; the QA stack's Firebase emulator drops `*-debug.log` in the
    repo root. All of them land in a story's diff, none of them is something a feature Concept
    can own.

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
    write in the client's book would have been true.

    `qa-stack.yml` stays on the list though nothing writes one any more — the declaration
    moved into the book's `runbook` node (`ostler/docs/okf-runbook.md`) — because a repo
    carrying the old file must not start failing the gate on it."""
    from ostler.qa.context import _is_non_production_path as np

    for path in (
        "agents.yml", "qa-stack.yml", ".agents/agents.mk", ".agents/local.compose.yaml",
        ".opencode/opencode-loop/ses_123.json", "firebase-debug.log", "firestore-debug.log",
        "api/.mockery.yaml",
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


def test_a_digest_pinned_citation_still_grounds(tmp_path: Path):
    """A stamped `@digest` must not defeat grounding, for a bare file or a symbol citation.

    `_grounding_exists` used to split a ref on `::` before parsing it, instead of reading the
    already-parsed `CodeRef`. A bare-file ref pinned with `@digest` (`path@digest`) then failed
    `is_file` outright — the digest never got stripped, so the existence probe looked for a
    file literally named `path@digest`. A symbol ref pinned with `@digest`
    (`path::symbol@digest`) fared worse: the naive split put the digest suffix inside the
    symbol half, so the `.py`-gated declaration check went looking for a symbol named
    `symbol@digest` and never matched. Both were silently reported dangling even though the
    citation was correct and current.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "svc").mkdir()
    (tmp_path / "docs/features/demo/backend.md").write_text(
        "---\ntype: concept\ntitle: Backend\n---\n# Backend\n\n"
        "- code: `svc/backend.py::serve`, `svc/backend.py::serve@0123456789ab`, "
        "`svc/backend.py`, `svc/backend.py@0123456789ab`\n",
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
    assert dangling == [], packet["healthFindings"]


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
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
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


def _judgment_repo(root: Path, *, with_judgment: bool) -> str:
    """A screen whose interaction competes with an older writer, settled by a concept.

    `with_judgment=False` builds the same book with the `detail:` pointer, the
    `unspecified:` bullet and the concept files stripped — the control for asserting the
    judgment layer adds context without changing what a change is owed.
    """
    (root / "docs/features/acme/gui/screens").mkdir(parents=True)
    (root / "docs/features/acme/concepts").mkdir(parents=True)
    (root / "docs/decisions").mkdir(parents=True)
    (root / "app").mkdir()
    judgment_bullets = (
        "- detail: [Export choice](../../concepts/choice.md)\n"
        "- unspecified: duplicate names keep insertion order, settled by"
        " [the export decision](../../../../decisions/0001-export.md)\n"
        if with_judgment
        else ""
    )
    (root / "docs/features/acme/gui/screens/items.md").write_text(
        f"""---
type: screen
title: Items
---
# Items

## Components

### save-button
- role: button
- name: Save item
- code: app/items.py::save_item

## Interactions

### save-item
- on: [save-button](#save-button)
- trigger: click
- does:
  - request: persist the item
  - error: preserve fields and expose an alert
- code: app/items.py::save_item
{judgment_bullets}""",
        encoding="utf-8",
    )
    if with_judgment:
        (root / "docs/decisions/0001-export.md").write_text("# settled\n", encoding="utf-8")
        (root / "docs/features/acme/concepts/choice.md").write_text(
            """---
type: concept
title: Export choice
---
# Export choice

- rule: prefer the streaming writer; the buffered one exists only for the legacy CLI
- prefers: [save-item](../gui/screens/items.md#save-item)
- deprecates: [legacy writer](legacy-writer.md)
""",
            encoding="utf-8",
        )
        (root / "docs/features/acme/concepts/legacy-writer.md").write_text(
            """---
type: concept
title: Legacy writer
---
# Legacy writer
""",
            encoding="utf-8",
        )
    (root / "app/items.py").write_text("def save_item():\n    return 'old'\n", encoding="utf-8")
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "app/items.py").write_text("def save_item():\n    return 'new'\n", encoding="utf-8")
    return base


def test_a_detail_edge_pulls_its_concept_as_judgment_context(tmp_path: Path):
    """The concept a selected node points `detail:` at rides along, and only as context.

    Its rule/prefers/deprecates land on the pointing node's node-level obligation — where the
    reviewer choosing between implementations reads them — and on nothing the node mints per
    bullet, while the concept itself is never owed live evidence.
    """
    base = _judgment_repo(tmp_path, with_judgment=True)

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})

    assert validate_context(packet) == []
    concept_id = next(node for node in packet["contracts"] if node.endswith("choice.md"))
    reasons = next(
        item["reasons"] for item in packet["directNodes"] if item["node"] == concept_id
    )
    pointer = next(r for r in reasons if r["kind"] == "judgment-context")
    assert pointer["ref"].endswith("#save-item")
    by_id = {item["id"]: item for item in packet["obligations"]}
    concept_contract = by_id[f"okf:{concept_id}:contract"]
    assert concept_contract["required"] is False
    assert concept_contract["evidenceRequired"] == "context"
    interaction = next(
        item
        for key, item in by_id.items()
        if key.endswith("#save-item:contract")
    )
    entry = next(e for e in interaction["judgment"] if e["concept"] == concept_id)
    assert entry["title"] == "Export choice"
    assert entry["rules"] == [
        "prefer the streaming writer; the buffered one exists only for the legacy CLI"
    ]
    assert entry["prefers"] == ["[save-item](../gui/screens/items.md#save-item)"]
    assert entry["deprecates"] == ["[legacy writer](legacy-writer.md)"]
    resolved = interaction["unspecified"]
    assert resolved[0]["citation"] == "../../../../decisions/0001-export.md"
    assert "insertion order" in resolved[0]["text"]
    for key, item in by_id.items():
        if key.endswith(":does:1") or key.endswith(":does:2"):
            assert "judgment" not in item
            assert "unspecified" not in item


def test_judgment_context_changes_no_owed_obligation(tmp_path: Path):
    """Additive only: with the judgment layer stripped, the owed set is byte-identical."""
    with_dir = tmp_path / "with"
    without_dir = tmp_path / "without"
    with_dir.mkdir()
    without_dir.mkdir()
    base_with = _judgment_repo(with_dir, with_judgment=True)
    base_without = _judgment_repo(without_dir, with_judgment=False)

    packet_with = build_context(with_dir, base=base_with, source_roots={"acme": ["app"]})
    packet_without = build_context(
        without_dir, base=base_without, source_roots={"acme": ["app"]}
    )

    def owed(packet: dict) -> set[str]:
        return {
            item["id"] for item in packet["obligations"] if item.get("required", True)
        }

    assert owed(packet_with) == owed(packet_without)


def test_rendering_shows_judgment_and_unspecified_beside_the_obligation():
    obligation = {
        "id": "okf:items#save-item:contract",
        "requirement": "save-item",
        "judgment": [
            {
                "concept": "choice",
                "title": "Export choice",
                "rules": ["prefer the streaming writer"],
                "prefers": ["[save-item](items.md#save-item)"],
                "deprecates": ["[legacy writer](legacy-writer.md)"],
            }
        ],
        "unspecified": [
            {"text": "ordering settled by [the record](../decisions/0001.md)",
             "citation": "../decisions/0001.md"}
        ],
    }
    lines = render_obligations([obligation])
    assert "  - judgment: `choice` — prefer the streaming writer" in lines
    assert "    - prefers: [save-item](items.md#save-item)" in lines
    assert "    - deprecates: [legacy writer](legacy-writer.md)" in lines
    assert (
        "  - unspecified (resolved by design): ordering settled by"
        " [the record](../decisions/0001.md)" in lines
    )
    # The prose context is not a locator detail — a caller stripping locators keeps it.
    assert any("judgment" in line for line in render_obligations([obligation], locators=False))


def test_book_root_derives_from_features_root_nesting():
    """A book nested under `<prefix>/docs/features` reports `<prefix>` as its own root; a
    book at the repo's default `docs/features` reports no root at all — it already sits
    where the host repo's paths are spelled."""
    root = Path("/repo")
    assert _book_root(root, "docs/features") == ""
    assert _book_root(root, "nested/docs/features") == "nested"
    assert _book_root(root, "a/b/docs/features") == "a/b"


def test_book_relative_rebases_onto_the_book_root():
    assert _book_relative("nested/app/service.py", "nested") == "app/service.py"
    assert _book_relative("other/app/service.py", "nested") == "other/app/service.py"
    assert _book_relative("app/service.py", "") == "app/service.py"


def test_nested_book_joins_its_own_root_relative_citations_to_host_relative_changes(tmp_path: Path):
    """A book need not live at the repo's default `docs/features` to join to its code: the
    same book joins whether the repo is checked out at the book's own root or nested inside
    a larger tree. Regression test for a book that cites paths relative to its own root
    while the changed-file feed is always relative to the git top-level.

    Also exercises the Go pointer-receiver spelling: the book cites `Widget.Create`, the
    extractor reports `(*Widget).Create` for the same method — a tolerated grammar
    variant, not a mismatch.
    """
    service = tmp_path / "service"
    (service / "docs/features/demo").mkdir(parents=True)
    (service / "app").mkdir(parents=True)
    (tmp_path / "unrelated").mkdir()
    feature = service / "docs/features/demo/widget.md"
    feature.write_text(
        """---
type: concept
title: Widget
---
# Widget

- code: app/widget.go::Widget.Create
""",
        encoding="utf-8",
    )
    source = service / "app/widget.go"
    source.write_text(
        "package app\n\ntype Widget struct{}\n\nfunc (w *Widget) Create() string {\n"
        '\treturn "old"\n}\n',
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    source.write_text(
        source.read_text(encoding="utf-8").replace('"old"', '"created"'), encoding="utf-8"
    )

    packet = build_context(
        tmp_path,
        base=base,
        features_root="service/docs/features",
        source_roots={"demo": ["service/app"]},
    )

    assert validate_context(packet) == []
    assert [c["headSymbols"] for c in packet["changedCode"]] == [["(*Widget).Create"]]
    assert packet["directNodes"]
    assert packet["obligations"]
    kinds = {finding["kind"] for finding in packet["healthFindings"]}
    assert "unmapped-change" not in kinds
    assert "dangling-grounding" not in kinds


def test_a_check_locator_is_resolved_into_the_packet(tmp_path: Path):
    """The packet says which component a `verify:` points at, and what that component is.

    Resolution happens here and only here. `Graph.resolve_doc_ref` consults the filesystem to
    prefer an origin-relative reading, so a compiler that never opens a graph could not repeat
    it — and one that re-implemented it would be free to disagree with the `doctor` rule that
    passed the book. One resolution, stamped; two readers, agreeing by construction.
    """
    (tmp_path / "docs/features/acme/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/screens/items.md").write_text(
        """---
type: screen
slug: items
title: Items
---
# Items

## Components

### item-form

- selector: `form`
- role: form
- name: New item

### save-error

- selector: `#save-error`

## Interactions

### save-item
- on: [item-form](#item-form)
- trigger: click
- does:
  - error: expose an alert
- code: app/items.py::save_item
- verify: visible(locator="#save-error", text="could not save")
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    obligation = next(item for item in packet["obligations"]
                      if item["id"].endswith("#save-item:does:1"))
    located = obligation["checksDeclared"][0]["locates"]["locator"]
    assert located["node"] == "docs/features/acme/screens/items.md#save-error"
    # The named component's own addressing travels too, so the compiler points a driver at what
    # the check named without re-walking the graph. Verbatim as authored, code span and all —
    # unwrapping it is the compiler's job, and a packet that pre-cooked it would be deciding for
    # a driver it does not know the identity of.
    assert located["locators"]["selector"] == ["`#save-error`"]


def test_a_check_locator_that_resolves_to_nothing_is_stamped_empty(tmp_path: Path):
    """An empty target, not an absent field. A check row that simply omitted `locates` would be
    indistinguishable from one whose check takes no locator at all — and the compiler owes a gap
    for this one, which it can only owe if the packet says the reference went nowhere."""
    (tmp_path / "docs/features/acme/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/screens/items.md").write_text(
        """---
type: screen
slug: items
title: Items
---
# Items

## Components

### item-form

- selector: `form`

## Interactions

### save-item
- on: [item-form](#item-form)
- trigger: click
- does:
  - error: expose an alert
- code: app/items.py::save_item
- verify: visible(locator="#no-such-component")
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    obligation = next(item for item in packet["obligations"]
                      if item["id"].endswith("#save-item:does:1"))
    assert obligation["checksDeclared"][0]["locates"]["locator"] == {"node": "", "locators": {}}


def test_a_locator_key_undeclared_on_the_nodes_type_is_not_read():
    """`on:` is declared on `interaction`/`invocation`, never on `method` — but before 3aa,
    `_locators` read every `_LOCATOR_KEYS` member straight off a node's raw bullets with no
    reference to what its type actually declares, so an `on:` authored on a `method` node (the
    real book this generalizes from carried 205 of these) leaked through anyway. `does:` is
    both a locator *and* declared on `method`, so it still surfaces — the fix is a per-type
    filter, not a blanket refusal of the key."""
    node = {
        "type": "method",
        "bullets": {
            "does": ["writes the ledger."],
            "on": ["[item-form](#item-form)"],
        },
    }
    located = _locators(node)
    assert "on" not in located
    assert located["does"] == ["writes the ledger."]


def test_channel_is_read_as_an_endpoints_address_locator():
    """`channel:` carries `locator=True, address=True`, exactly as `method:`/`path:` do, so an
    endpoint that names a channel is found by the same two readers a routed endpoint is: the
    registry's own key set, and `_locators`, which is what a planner/compiler reads a node's
    address off of."""
    assert "channel" in registry.LOCATOR_KEYS
    node = {
        "type": "endpoint",
        "bullets": {
            "method": ["GET"],
            "path": ["/api/things"],
            "channel": ["ws://events"],
        },
    }
    located = _locators(node)
    assert located["method"] == ["GET"]
    assert located["path"] == ["/api/things"]
    assert located["channel"] == ["ws://events"]


def test_an_unstated_claim_combiner_is_stamped_on_every_child(tmp_path: Path):
    """The obligation is real and a planner still reads it; nothing may compile it.

    `doctor` refuses this book, but `qa context` is not downstream of `doctor` and still has to
    hand the packet a truthful account: the check above the list observes all of these children
    or exactly one of them, and the book does not say which.
    """
    (tmp_path / "docs/features/acme/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/screens/items.md").write_text(
        """---
type: screen
slug: items
title: Items
---
# Items

## Components

### item-form

- selector: `form`

## Interactions

### save-item
- on: [item-form](#item-form)
- trigger: click
- does:
  - request: persist the item
  - error: expose an alert
- code: app/items.py::save_item
- verify: visible(locator="#item-form")
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text("def save_item():\n    return 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    stamped = {item["id"].rsplit("#", 1)[-1]: item.get("claimCombiner")
               for item in packet["obligations"]}
    assert stamped["save-item:does:1"] == "unstated"
    assert stamped["save-item:does:2"] == "unstated"
    # The node's own contract nests nothing, so there is no word it could be missing.
    assert stamped["save-item:contract"] is None


def test_a_flows_steps_reach_the_packet_in_the_order_the_book_wrote_them(tmp_path: Path):
    """A journey is a sequence, and the packet has to carry it as one.

    Before this, every node a flow named — its `start:`, its `steps:`, its `end:`, its
    `fixture:` — arrived as one more unordered `flow-links-contract` entry under `reasons`.
    A set of links is not a sequence, so no later stage could walk the journey; it could
    only assert the end state on arrival, in a world the steps never ran in.

    The second `steps:` entry here names the very screen `start:` already named. That is the
    case the edge attribution cannot express — `via` keeps the *first* bullet an href
    appeared under, so reading the walk off `edges` would silently drop it and compile a
    journey one step short.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "docs/features/acme/flows").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/gui/screens/items.md").write_text(
        """---
type: screen
title: Items
---
# Items

- route: /items

## Components

### save-button
- role: button
- name: Save item
- code: app/items.py::save_item

## Interactions

### save-item
- on: [save-button](#save-button)
- trigger: click
- does:
  - request: persist the item
- verify: visible(locator="#saved")
- code: app/items.py::save_item
""",
        encoding="utf-8",
    )
    (tmp_path / "docs/features/acme/flows/save-and-return.md").write_text(
        """---
type: flow
title: Save and return
---
# Save and return

- start: [items](../gui/screens/items.md)
- steps:
  - [save-item](../gui/screens/items.md#save-item)
  - [items](../gui/screens/items.md)
- end: [items](../gui/screens/items.md)
- verify: visible(locator="../gui/screens/items.md#save-button")
""",
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text(
        "def save_item():\n    return 'old'\n", encoding="utf-8"
    )
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

    flow = [
        item for item in packet["obligations"]
        if item["id"].startswith("okf:docs/features/acme/flows/save-and-return.md")
    ]
    assert flow, "the flow minted no obligation to carry a walk"
    walk = [
        [(step["ref"], step["nodeType"]) for step in item["steps"]] for item in flow
    ]
    # Every obligation the flow mints carries the same walk: its `start:`, its `end:` and its
    # own `verify:` are each a claim about what these steps did.
    assert walk and all(entry == walk[0] for entry in walk)
    assert walk[0] == [
        ("docs/features/acme/gui/screens/items.md#save-item", "interaction"),
        ("docs/features/acme/gui/screens/items.md", "screen"),
    ]
    assert {step["surface"] for step in flow[0]["steps"]} == {"acme"}


def test_a_fixture_bullet_naming_its_own_emptiness_is_a_decision_the_packet_carries(
    tmp_path: Path,
):
    """An author who decided the node needs no arrangement, and one who never looked, produce
    the same empty `fixturesDeclared`. They are not the same claim, so the packet says which:
    `arrangesNothing` is stamped only by a bullet that states the emptiness and its reason, and
    `compile_plan` gaps the silent case (`unarranged-journey`) while compiling the stated one.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
- code: app/list.py::list_claims
- fixture: none, because the route reads a store it is documented as finding empty
- authorization: a holder reads only their own claims.

### count-claims
- method: GET
- path: /api/claims/count
- code: app/list.py::list_claims
- authorization: a holder counts only their own claims.
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
    stated = {
        item["id"].rsplit("#", 1)[-1]: bool(item.get("arrangesNothing"))
        for item in packet["obligations"]
    }
    # Ambient, exactly as a named arrangement written in the same place would be.
    assert stated["list-claims:contract"] is True
    assert stated["list-claims:authorization:1"] is True
    # The node next door said nothing, and silence is not the same answer.
    assert stated["count-claims:contract"] is False
    assert stated["count-claims:authorization:1"] is False
    # It is not an arrangement either — there is no fixture here to run.
    assert all(
        not item.get("fixturesDeclared")
        for item in packet["obligations"]
        if item["id"].rsplit("#", 1)[-1].startswith("list-claims")
    )


def test_a_fixture_bullet_the_parser_rejects_is_carried_not_dropped(tmp_path: Path):
    """The packet used to say only what the book successfully declared, and the lint said what
    it tried to. That division holds for a reader reporting to an author and fails for the one
    reader deciding whether to emit code: downstream, a bullet nobody wrote and a bullet that
    did not parse are the same absent row, so a typo was gapped as an author who never looked.
    The rejection now rides in the packet, with the sentence from the only reader that saw it.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
- code: app/list.py::list_claims
- fixture: Seeded Ledger — two claims on file
- authorization: a holder reads only their own claims.
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
    by_id = {item["id"].rsplit("#", 1)[-1]: item for item in packet["obligations"]}

    # No row, because nothing parsed — and the value is still here to say why there is none.
    assert "fixturesDeclared" not in by_id["list-claims:contract"]
    [rejected] = by_id["list-claims:contract"]["fixturesUnparsed"]
    assert rejected["value"] == "Seeded Ledger — two claims on file"
    assert "is not a fixture name" in rejected["problem"]
    # Ambient, the same way a parsed arrangement written in that place would be.
    assert by_id["list-claims:authorization:1"]["fixturesUnparsed"] == [rejected]


def test_a_verify_bullet_the_parser_refuses_is_carried_not_dropped(tmp_path: Path):
    """`checksDeclared` absent meant two different books: one that declared no observation, and
    one whose observation nobody could read. `compile_plan` gapped both `no-verify-declared` —
    *"the book declares no check for this obligation to prove"* — so an author who wrote a check
    and got its spelling wrong was told to write one. `ostler doctor` refuses this bullet by name
    already, so the two readers of one bullet disagreed in writing, and the reader deciding
    whether to emit code held the wrong account. The refusal now rides in the packet, with the
    class the parser assigned it, because a refusal classifies and only the parser looked.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
- code: app/list.py::list_claims
- verify: htp_status 200 for /api/claims
- authorization: a holder reads only their own claims.
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
    by_id = {item["id"].rsplit("#", 1)[-1]: item for item in packet["obligations"]}

    # Nothing parsed, so no row — and the rejected value is here to say there was one.
    assert "checksDeclared" not in by_id["list-claims:contract"]
    [refused] = by_id["list-claims:contract"]["checksUnparsed"]
    assert refused["value"] == "htp_status 200 for /api/claims"
    assert refused["kind"] and refused["problem"]


def test_a_capture_bullet_the_parser_refuses_is_carried_not_dropped(tmp_path: Path):
    """The packet builder's own docstring said a malformed `capture:` was "left for `ostler
    doctor` to report", and doctor had no capture checker at all — one comment, no finding. So
    the bullet was dropped here, reported by nobody, and the cost landed on a later bullet whose
    `$name` resolved against a fact that was never minted. The refusal rides in the packet now,
    and the checker the docstring promised exists.
    """
    (tmp_path / "docs/features/acme/http").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/http/claims.md").write_text(
        """---
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
- code: app/list.py::list_claims
- verify: http_status(200, path="/api/claims")
- capture: claim_id $.id
- authorization: a holder reads only their own claims.
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
    by_id = {item["id"].rsplit("#", 1)[-1]: item for item in packet["obligations"]}

    assert "capturesDeclared" not in by_id["list-claims:contract"]
    [refused] = by_id["list-claims:contract"]["capturesUnparsed"]
    assert refused["value"] == "claim_id $.id"
    assert "from" in refused["problem"]


_ARRANGED_SCREEN = """---
type: screen
slug: items
title: Items
---
# Items

- route: /items
- requires: none
- params: none

## Components

### name-field
- role: textbox
- name: Name
- selector: input[name="name"]
- code: app/items.py::render_form

### quantity-field
- role: textbox
- name: Quantity
- selector: input[name="quantity"]
- code: app/items.py::render_form

## Interactions

### save-item
- on: [Items](#items)
- trigger: click
- role: button
- name: Save
- code: app/items.py::save_item
- when: `name` is non-empty and `quantity` is a non-negative number
- arrange: fill(locator="#name-field", value="Widget A")
- arrange: fill(locator="#quantity-field", value="3")
- does: the item is saved
- arrange: click(locator="#name-field")
"""


def test_an_arranged_interaction_carries_its_acts_into_the_packet(tmp_path: Path):
    """A `when:` over what the user typed is state no fixture can reach, and the acts that
    establish it are the packet's only account of the world the claim below is about.

    Three things this pins. The acts bind by document order, exactly as `verify:` and
    `fixture:` do, so the two `fill`s belong to the `when:` above them and the `click` written
    below `does:` belongs to `does:` — not to all three. Their order is preserved rather than
    collapsed on a name, because filling two fields is two performances and a fixture run twice
    reaches the same state while an act performed twice does not. And each locator arrives
    resolved to the component it names (F17: the subject is a reference into the book), so the
    compiler emits a selector the book declares rather than one an author typed twice.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/gui/screens/items.md").write_text(
        _ARRANGED_SCREEN, encoding="utf-8"
    )
    (tmp_path / "app/items.py").write_text(
        "def render_form():\n    return 'old'\n\n\ndef save_item():\n    return 'old'\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text(
        "def render_form():\n    return 'new'\n\n\ndef save_item():\n    return 'new'\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    by_id = {item["id"].rsplit("#", 1)[-1]: item for item in packet["obligations"]}

    when = by_id["save-item:when:1"]
    assert [row["call"] for row in when["actsDeclared"]] == [
        'fill(locator="#name-field", value="Widget A")',
        'fill(locator="#quantity-field", value="3")',
    ]
    assert when["actsDeclared"][0]["locates"]["locator"]["node"] == (
        "docs/features/acme/gui/screens/items.md#name-field"
    )
    assert when["actsDeclared"][0]["locates"]["locator"]["locators"]["selector"] == [
        'input[name="name"]'
    ]
    # Document order, not fan-out: the act written after `does:` arranges that claim alone.
    assert [row["call"] for row in by_id["save-item:does:1"]["actsDeclared"]] == [
        'click(locator="#name-field")'
    ]
    # An arrangement is not a fixture, and neither parser is asked to read the other's value.
    assert not when.get("fixturesDeclared")
    assert not when.get("fixturesUnparsed")
    assert not when.get("actsUnparsed")


def test_an_arrange_bullet_the_act_parser_rejects_is_carried_not_dropped(tmp_path: Path):
    """The counterpart of `_unparsed_fixtures`, for the reason that one exists: downstream, a
    bullet nobody wrote and a bullet that did not parse are the same absent row, so a mistyped
    arrangement would be gapped at an author who arranged it. The refusal's `kind` rides along
    because a refusal classifies — a bare fixture name under `arrange:` is a misfiled bullet,
    not a typo in an argument.
    """
    (tmp_path / "docs/features/acme/gui/screens").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/acme/gui/screens/items.md").write_text(
        _ARRANGED_SCREEN.replace(
            '- arrange: fill(locator="#name-field", value="Widget A")',
            "- arrange: widgets-on-hand",
        ),
        encoding="utf-8",
    )
    (tmp_path / "app/items.py").write_text(
        "def render_form():\n    return 'old'\n\n\ndef save_item():\n    return 'old'\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "app/items.py").write_text(
        "def render_form():\n    return 'new'\n\n\ndef save_item():\n    return 'new'\n", encoding="utf-8"
    )

    packet = build_context(tmp_path, base=base, source_roots={"acme": ["app"]})
    by_id = {item["id"].rsplit("#", 1)[-1]: item for item in packet["obligations"]}

    when = by_id["save-item:when:1"]
    [rejected] = when["actsUnparsed"]
    assert rejected["value"] == "widgets-on-hand"
    assert rejected["kind"] == "misfiled-fixture"
    # The one that did parse is still carried: a refused sibling is not a refused bullet list.
    assert [row["call"] for row in when["actsDeclared"]] == [
        'fill(locator="#quantity-field", value="3")'
    ]


def test_a_book_rooted_below_its_checkout_sees_its_own_changed_files(tmp_path: Path):
    """A book rooted below its checkout's top level still sees what changed under it.

    `git diff` always spells its output relative to the checkout's top level, never the cwd
    it was run from; a book below that top level has to rebase those paths onto its own root
    before anything downstream — `_surface_owner`, the `code:` join, `_is_generated_unit` —
    can recognize them. This is the case `test_a_book_rooted_below_its_checkout_is_reported`
    used to name a health finding for, back when the mismatch went unhandled and every change
    under such a book read as invisible rather than as changed.
    """
    book = tmp_path / "service"
    (book / "docs/features/demo").mkdir(parents=True)
    (book / "app").mkdir()
    (book / "docs/features/demo/item.md").write_text(
        """---
type: concept
title: Item
---
# Item

- code: app/service.py::create_item
""",
        encoding="utf-8",
    )
    (book / "app/service.py").write_text("def create_item():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (book / "app/service.py").write_text("def create_item():\n    return 'new'\n", encoding="utf-8")

    packet = build_context(book, base=base)

    assert [f for f in packet["healthFindings"] if f["kind"] == "unrooted-diff-scope"] == []
    paths = [change["path"] for change in packet["changedCode"]]
    assert paths == ["app/service.py"], paths
    direct_nodes = {row["node"]: row["reasons"] for row in packet["directNodes"]}
    assert direct_nodes["docs/features/demo/item.md"][0]["ref"] == "app/service.py::create_item"


def test_a_book_rooted_at_its_checkout_reports_no_diff_scope_entry(tmp_path: Path):
    """The kind no longer fires at all, for a book at its checkout's root or below it."""
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/features/demo/item.md").write_text(
        """---
type: concept
title: Item
---
# Item

- code: app/service.py::create_item
""",
        encoding="utf-8",
    )
    (tmp_path / "app/service.py").write_text(
        "def create_item():\n    return 'old'\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    packet = build_context(tmp_path, base=base)

    assert [f for f in packet["healthFindings"] if f["kind"] == "unrooted-diff-scope"] == []


def test_changed_units_outside_the_book_root_are_not_a_unit_of_this_book(tmp_path: Path):
    """A path the top-level diff reports that falls outside the book root is not this book's
    to own — dropped from `_changed_units`'s own output, not surfaced as any kind of error."""
    from ostler.qa.context import _changed_units

    book = tmp_path / "service"
    (book / "app").mkdir(parents=True)
    (tmp_path / "other").mkdir()
    (book / "app/service.py").write_text("def create_item():\n    return 'old'\n", encoding="utf-8")
    (tmp_path / "other/tool.py").write_text("def run():\n    return 'old'\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (book / "app/service.py").write_text("def create_item():\n    return 'new'\n", encoding="utf-8")
    (tmp_path / "other/tool.py").write_text("def run():\n    return 'new'\n", encoding="utf-8")

    units = _changed_units(book, base, "WORKTREE", {})

    paths = [unit.path for unit in units]
    assert paths == ["app/service.py"], paths


def _write_navigation_environment(repo: Path) -> None:
    """The `environment:` node the tests below share — `_navigation`'s `bundleId` must reach
    both shapes it builds per surface: the screen-less stub (no `screen` nodes at all) and the
    `reach.reachability`/`UnknownStart` dict (a surface with screens, on both the success path
    and the exception path)."""
    write(repo / "docs/features/groom/ops/local.md", (
        "---\ntype: environment\nslug: local\ntitle: Local\n---\n# Local\n\n"
        "- selector: `GROOM_BIND=127.0.0.1`\n- services:\n  - dashboard: `http://127.0.0.1:8787`\n"
        "- local-only: true\n"
    ))


def test_navigation_carries_bundle_id_through_the_screenless_stub_branch(repo: Path):
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/cli/tally.md", (
        "---\ntype: cli\nslug: tally\ntitle: Tally\n---\n# Tally\n\n## Commands\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [tally](../cli/tally.md)\n"
        "- bundle-id: com.example.mobile-app\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["bundleId"] == "com.example.mobile-app"
    assert navigation["groom"]["counts"]["screens"] == 0


def test_navigation_carries_bundle_id_through_the_reachability_success_path(repo: Path):
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", (
        "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
        "- route: `/`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: web\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["bundleId"] == "com.example.mobile-app"
    assert navigation["groom"]["counts"]["screens"] == 1
    assert navigation["groom"]["counts"]["reachable"] == 1
    assert "error" not in navigation["groom"]


def test_navigation_carries_bundle_id_through_the_unknown_start_exception_path(repo: Path):
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", (
        "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
        "- route: `/dashboard`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: web\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["bundleId"] == "com.example.mobile-app"
    assert "error" in navigation["groom"]
    assert navigation["groom"]["counts"]["unreachable"] == 1


def test_navigation_carries_launch_screen_through_the_screenless_stub_branch(repo: Path):
    """A surface with no screen nodes at all takes `_navigation`'s screenless-stub branch —
    `reach.screens_of` counts every `screen` file under the surface's own directory, so a
    surface with none has nothing a `launch-screen:` could name either; the stub still carries
    `launchScreen` (here, correctly `None`, since no screen exists to resolve to) the same way
    it already carries `driver`/`bundleId` through this branch, rather than dropping the key."""
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/cli/tally.md", (
        "---\ntype: cli\nslug: tally\ntitle: Tally\n---\n# Tally\n\n## Commands\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [tally](../cli/tally.md)\n"
        "- bundle-id: com.example.mobile-app\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["launchScreen"] is None
    assert navigation["groom"]["counts"]["screens"] == 0
    assert "launchScreenError" not in navigation["groom"]


def test_navigation_carries_launch_screen_through_the_reachability_success_path(repo: Path):
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", (
        "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
        "- route: `/`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: web\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        "- launch-screen: [dashboard](../gui/screens/dashboard.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["launchScreen"] == "docs/features/groom/gui/screens/dashboard.md"
    assert navigation["groom"]["counts"]["screens"] == 1
    assert navigation["groom"]["counts"]["reachable"] == 1
    assert "launchScreenError" not in navigation["groom"]


def test_navigation_carries_launch_screen_through_the_unknown_start_exception_path(repo: Path):
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", (
        "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
        "- route: `/dashboard`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        "- driver: web\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        "- launch-screen: [dashboard](../gui/screens/dashboard.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"]["launchScreen"] == "docs/features/groom/gui/screens/dashboard.md"
    assert "error" in navigation["groom"]
    assert navigation["groom"]["counts"]["unreachable"] == 1


def test_navigation_reports_conflicting_launch_screen_error_without_raising(repo: Path):
    """A surface whose two `runbook`s both state a `launch-screen:` and disagree, with neither
    marked `walkthrough: true`, must not raise past `_navigation` — the same
    `undeclared-walkthrough-runbook` degrade `_navigation`'s driver/bundle-id handling already
    pins, now pinned for `launchScreen` too."""
    _write_navigation_environment(repo)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", (
        "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
        "- route: `/`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/gui/screens/settings.md", (
        "---\ntype: screen\nslug: settings\ntitle: Settings\n---\n# Settings\n\n"
        "- route: `/settings`\n- requires: none\n- params: none\n"
    ))
    write(repo / "docs/features/groom/ops/legacy.md", (
        "---\ntype: runbook\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        "- launch-screen: [dashboard](../gui/screens/dashboard.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    write(repo / "docs/features/groom/ops/current.md", (
        "---\ntype: runbook\nslug: current\ntitle: Current\n---\n# Current\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        "- launch-screen: [settings](../gui/screens/settings.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run --current`\n"
    ))
    navigation = _navigation(load(repo))
    assert navigation["groom"].get("launchScreen") is None
    assert navigation["groom"]["launchScreenErrorKind"] == "undeclared-walkthrough-runbook"


def test_a_features_root_absent_at_base_is_an_empty_graph_not_an_error(tmp_path: Path):
    """The features root can genuinely not exist yet at `base` — added or renamed between
    base and head — and `_graph_at_revision` must answer with the empty graph silently, the
    same way `book_context` asks for one on purpose when `base` is the empty tree. This test
    passing is itself the result: it proves the fix for the corrupted-blob case below did not
    turn this legitimate, ordinary mode into a failure.
    """
    (tmp_path / "app").mkdir()
    (tmp_path / "app/service.py").write_text("def create_item():\n    return 1\n", "utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base, no features root yet")
    base = _git(tmp_path, "rev-parse", "HEAD")

    graph = _graph_at_revision(tmp_path, base, "docs/features")

    assert graph.ui_nodes == []


def test_a_listed_path_with_no_readable_blob_raises_instead_of_shrinking(tmp_path: Path):
    """A path `ls-tree` names but whose blob the object store cannot produce is corruption,
    not "nothing to graph": the old bare `except RuntimeError: continue` dropped it and
    returned a graph that looked exactly like the legitimate empty one above. It must raise,
    naming the revision and the path, instead.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    feature = tmp_path / "docs/features/demo/item.md"
    feature.write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n\n- code: app/service.py::create_item\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    blob = _git(tmp_path, "rev-parse", f"{base}:docs/features/demo/item.md")
    object_path = tmp_path / ".git/objects" / blob[:2] / blob[2:]
    assert object_path.is_file(), object_path
    object_path.unlink()

    try:
        _graph_at_revision(tmp_path, base, "docs/features")
    except RuntimeError as exc:
        message = str(exc)
        assert base in message
        assert "docs/features/demo/item.md" in message
    else:
        raise AssertionError("expected a RuntimeError for the unreadable blob")


def test_a_filename_git_would_quote_is_not_dropped(tmp_path: Path):
    """`ls-tree` without `-z` shell-quotes a filename holding a newline, so
    `line.endswith(".md")` used to be False and the file was silently dropped before `git
    show` was ever tried. `-z` NUL-delimits instead of quoting, so the file must survive.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    weird = tmp_path / "docs/features/demo/weird\nname.md"
    weird.write_text(
        "---\ntype: concept\ntitle: Weird\n---\n# Weird\n\n- code: app/service.py::create_item\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    graph = _graph_at_revision(tmp_path, base, "docs/features")

    assert [node.id for node in graph.ui_nodes]


def test_a_nested_book_graphs_its_own_tree_not_the_hosts(tmp_path: Path):
    """`root` is the *subject's* root — `paddock/data/apps/globex`, say — not the repo
    top level; `_git`/`_git_bytes` run with `cwd=root`, so every path this module hands
    git is CWD-relative, but `<rev>:<path>` is repo-root-relative unless prefixed `./`.

    Here the host repo has its OWN `docs/features/demo/item.md` at its top level, and the
    nested book being measured has a file at the *same relative path* with different
    content. Left unprefixed: `git cat-file -e HEAD:docs/features` (cwd=service) answers
    for the host's tree and reports "present"; `git show HEAD:docs/features/demo/item.md`
    (cwd=service) then streams the HOST's blob, because that path also happens to exist
    at the repo top level. That is not a crash — it is a confident wrong answer: the
    nested book's graph is built from a file it never wrote. `./`-prefixing both calls
    (`_revision_path_arg`) makes them resolve against `cwd` instead, and the graph comes
    back from the book's own tree.
    """
    outer = tmp_path
    service = outer / "service"
    (outer / "docs/features/demo").mkdir(parents=True)
    (service / "docs/features/demo").mkdir(parents=True)
    (outer / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Host Item\n---\n# Host Item\n",
        encoding="utf-8",
    )
    (service / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Service Item\n---\n# Service Item\n",
        encoding="utf-8",
    )
    _git(outer, "init")
    _git(outer, "config", "user.email", "qa@example.com")
    _git(outer, "config", "user.name", "QA")
    _git(outer, "add", ".")
    _git(outer, "commit", "-m", "base")
    base = _git(outer, "rev-parse", "HEAD")

    graph = _graph_at_revision(service, base, "docs/features")

    assert [node.title for node in graph.ui_nodes] == ["Service Item"]


def test_a_nested_book_graphs_when_the_host_has_no_matching_path(tmp_path: Path):
    """Companion to the false-positive case above: here the host repo's own
    `docs/features` tree exists (so the presence guard reports "present" even unprefixed)
    but holds no file at the path the nested book's `docs/features` actually lists. Left
    unprefixed, `git show HEAD:docs/features/demo/item.md` (cwd=service) looks for that
    path at the repo top level, finds nothing there, and `_graph_at_revision` raises "lists
    ... but its blob is unreadable" — treating a perfectly readable nested book as
    corrupt. `./`-prefixing resolves the same call against `cwd` and the book graphs.
    """
    outer = tmp_path
    service = outer / "service"
    (outer / "docs/features").mkdir(parents=True)
    (service / "docs/features/demo").mkdir(parents=True)
    (outer / "docs/features/OTHER.md").write_text(
        "---\ntype: concept\ntitle: Other\n---\n# Other\n", encoding="utf-8"
    )
    (service / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Service Item\n---\n# Service Item\n",
        encoding="utf-8",
    )
    _git(outer, "init")
    _git(outer, "config", "user.email", "qa@example.com")
    _git(outer, "config", "user.name", "QA")
    _git(outer, "add", ".")
    _git(outer, "commit", "-m", "base")
    base = _git(outer, "rev-parse", "HEAD")

    graph = _graph_at_revision(service, base, "docs/features")

    assert [node.title for node in graph.ui_nodes] == ["Service Item"]


def test_a_book_at_the_repo_root_is_unaffected_by_the_cwd_fix(tmp_path: Path):
    """The control: a book that already sits at the repository top level — the ordinary
    case, and every other test in this file — must behave exactly as it did before the
    `./`-prefix was introduced. This test passing is the result: it is what shows the fix
    is a frame correction for the nested case, not a rewrite of the working one.
    """
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n", encoding="utf-8"
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    graph = _graph_at_revision(tmp_path, base, "docs/features")

    assert [node.title for node in graph.ui_nodes] == ["Item"]
