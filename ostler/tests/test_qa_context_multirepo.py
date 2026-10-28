from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import epics_root
from ostler import doctor
from ostler.model import load
from ostler.qa.context import (
    EMPTY_TREE_SHA,
    book_context,
    build_context,
    cmd_context,
    cmd_context_refresh,
    validate_context,
)
from ostler.qa.source_context import SourceRepository, SourceScope
from ostler.provenance import source_freshness


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _init(root: Path) -> str:
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.com")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "base")
    return _git(root, "rev-parse", "HEAD")


def test_external_source_repository_maps_qualified_code_ref(tmp_path: Path) -> None:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    (docs / "docs/services/billing").mkdir(parents=True)
    story = epics_root() / "billing/stories/create-invoice/story.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "---\nid: BILL-01ABCDEF\nslug: create-invoice\n"
        "type: story\n---\n# Create invoice\n",
        encoding="utf-8",
    )
    (source / "src").mkdir(parents=True)
    (docs / "docs/services/billing/create.md").write_text(
        """---
type: concept
title: Create invoice
---
# Create invoice

- code: `repo://api-service/src/service.py::create_invoice`
""",
        encoding="utf-8",
    )
    implementation = source / "src/service.py"
    implementation.write_text(
        "def create_invoice():\n    return 'old'\n", encoding="utf-8"
    )
    docs_base = _init(docs)
    source_base = _init(source)
    implementation.write_text(
        "def create_invoice():\n    return 'new'\n", encoding="utf-8"
    )

    repository = SourceRepository(
        id="api-service",
        checkout=str(source),
        base=source_base,
        scopes=(SourceScope(surface="billing", root="src"),),
    )
    outcome = cmd_context(
        docs,
        docs / "docs/specs/create-invoice",
        base=docs_base,
        story_file=story,
        repositories=(repository,),
    )
    packet = outcome.data

    assert validate_context(packet) == []
    assert packet["version"] == 2
    assert packet["story"] == {
        "id": "BILL-01ABCDEF",
        "slug": "create-invoice",
    }
    stored_repository = packet["repositories"][0]
    assert stored_repository["id"] == "api-service"
    assert stored_repository["baseSha"] == source_base
    assert stored_repository["headAnchorSha"] == source_base
    assert stored_repository["sourceFingerprint"]
    assert stored_repository["scopes"] == [{"surface": "billing", "root": "src"}]
    assert packet["changedUnits"] == packet["changedCode"]
    assert packet["changedUnits"][0]["id"] == "repo://api-service/src/service.py"
    assert packet["changedUnits"][0]["headSymbols"] == ["create_invoice"]
    assert packet["directNodes"][0]["reasons"] == [
        {
            "kind": "changed-code",
            "ref": "repo://api-service/src/service.py::create_invoice",
            "key": "code",
        }
    ]
    assert not packet["healthFindings"]
    assert source_freshness(packet, {"api-service": source})[0]["status"] == "fresh"

    _git(source, "add", ".")
    _git(source, "commit", "-m", "record story work")
    assert source_freshness(packet, {"api-service": source})[0]["status"] == "fresh"

    implementation.write_text(
        "def create_invoice():\n    return 'newer'\n", encoding="utf-8"
    )
    freshness = source_freshness(packet, {"api-service": source})[0]
    assert freshness["status"] == "stale"
    assert "scoped source content differs" in freshness["reasons"][-1]
    report = doctor.cmd_doctor(load(docs)).data
    assert not [finding for finding in report["findings"] if finding["severity"] == "error"]

    refreshed = cmd_context(
        docs,
        docs / "docs/specs/create-invoice",
        base=docs_base,
        story_file=story,
        repositories=(repository,),
    ).data
    (source / "src/helper.py").write_text("value = 1\n", encoding="utf-8")
    freshness = source_freshness(refreshed, {"api-service": source})[0]
    assert freshness["status"] == "stale"


def test_external_file_owner_reason_keeps_repository_qualification(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    (docs / "docs/services/billing").mkdir(parents=True)
    (source / "src").mkdir(parents=True)
    (docs / "docs/services/billing/create.md").write_text(
        "---\ntype: concept\ntitle: Create invoice\n---\n# Create invoice\n\n"
        "- code: `repo://api-service/src/service.py`\n",
        encoding="utf-8",
    )
    implementation = source / "src/service.py"
    implementation.write_text("value = 'old'\n", encoding="utf-8")
    docs_base = _init(docs)
    source_base = _init(source)
    implementation.write_text("value = 'new'\n", encoding="utf-8")

    packet = build_context(
        docs,
        base=docs_base,
        repositories=(
            SourceRepository(
                id="api-service",
                checkout=str(source),
                base=source_base,
                scopes=(SourceScope(surface="billing", root="src"),),
            ),
        ),
    )

    assert packet["directNodes"][0]["reasons"] == [
        {
            "kind": "file-owner",
            "ref": "repo://api-service/src/service.py",
            "key": "code",
        }
    ]


def test_identical_paths_in_two_repositories_do_not_cross_map(tmp_path: Path) -> None:
    docs = tmp_path / "product-docs"
    first = tmp_path / "api-service"
    second = tmp_path / "web-app"
    (docs / "docs/services/billing").mkdir(parents=True)
    (docs / "docs/services/billing/create.md").write_text(
        """---
type: concept
title: Create invoice
---
# Create invoice

- code: `repo://api-service/src/service.py::create_invoice`
""",
        encoding="utf-8",
    )
    docs_base = _init(docs)
    repositories = []
    for repo_id, checkout in (("api-service", first), ("web-app", second)):
        (checkout / "src").mkdir(parents=True)
        code = checkout / "src/service.py"
        code.write_text("def create_invoice():\n    return 'old'\n", encoding="utf-8")
        base = _init(checkout)
        code.write_text("def create_invoice():\n    return 'new'\n", encoding="utf-8")
        repositories.append(SourceRepository(
            id=repo_id,
            checkout=str(checkout),
            base=base,
            scopes=(SourceScope(surface="billing", root="src"),),
        ))

    packet = build_context(docs, base=docs_base, repositories=tuple(repositories))

    changed_reasons = [
        reason
        for reason in packet["directNodes"][0]["reasons"]
        if reason["kind"] == "changed-code"
    ]
    assert [reason["ref"] for reason in changed_reasons] == [
        "repo://api-service/src/service.py::create_invoice"
    ]




def test_a_whole_book_context_maps_a_source_repository_from_the_empty_tree(tmp_path: Path) -> None:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    (docs / "docs/services/billing").mkdir(parents=True)
    (source / "src").mkdir(parents=True)
    (docs / "docs/services/billing/create.md").write_text(
        "---\ntype: concept\ntitle: Create invoice\n---\n# Create invoice\n\n"
        "- code: `repo://api-service/src/service.py::create_invoice`\n",
        encoding="utf-8",
    )
    (source / "src/service.py").write_text("def create_invoice():\n    return 1\n", encoding="utf-8")
    _init(docs)
    _init(source)
    repository = SourceRepository(
        id="api-service",
        checkout=str(source),
        base=EMPTY_TREE_SHA,
        scopes=(SourceScope(surface="billing", root="src/service.py"),),
    )

    packet = book_context(docs, repositories=(repository,), books=["docs/services/billing"])

    assert validate_context(packet) == []
    assert packet["repositories"][0]["base"] == EMPTY_TREE_SHA
    assert packet["repositories"][0]["baseSha"] == ""
    assert [unit["id"] for unit in packet["changedUnits"]] == ["repo://api-service/src/service.py"]
    assert source_freshness(packet, {"api-service": source})[0]["status"] == "fresh"


def test_a_refresh_rebuilds_from_the_recorded_scope_after_the_story_moves(tmp_path: Path) -> None:
    docs = tmp_path / "product-docs"
    (docs / "docs/services/billing").mkdir(parents=True)
    story = epics_root() / "billing/stories/create-invoice/story.md"
    story.parent.mkdir(parents=True)
    story.write_text("---\nid: BILL-01ABCDEF\nslug: create-invoice\ntype: story\n---\n# Create\n",
                     encoding="utf-8")
    (docs / "docs/services/billing/create.md").write_text(
        "---\ntype: concept\ntitle: Create invoice\n---\n# Create invoice\n\n"
        "- code: `src/service.py::create_invoice`\n",
        encoding="utf-8",
    )
    (docs / "src").mkdir()
    (docs / "src/service.py").write_text("def create_invoice():\n    return 'old'\n",
                                         encoding="utf-8")
    (docs / "src/other.py").write_text("value = 0\n", encoding="utf-8")
    base = _init(docs)
    (docs / "src/service.py").write_text("def create_invoice():\n    return 'new'\n",
                                         encoding="utf-8")
    (docs / "src/other.py").write_text("value = 1\n", encoding="utf-8")
    spec = docs / "docs/specs/create-invoice"
    built = cmd_context(
        docs,
        spec,
        base=base,
        source_roots={"billing": ["src"]},
        story_file=story,
        exclude_paths=["src/other.py"],
    )
    story.write_text(story.read_text(encoding="utf-8") + "\nRevised.\n", encoding="utf-8")

    refreshed = cmd_context_refresh(docs, spec)

    assert refreshed.status != "invalid", refreshed.message
    assert refreshed.data["inputs"] == built.data["inputs"]
    assert refreshed.data["inputs"]["excludePaths"] == ["src/other.py"]
    assert refreshed.data["changedCode"] == built.data["changedCode"]
    assert refreshed.data["storyFile"]["sha256"] != built.data["storyFile"]["sha256"]


def test_a_refresh_of_a_packet_without_recorded_inputs_is_refused(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text('{"version": 1}', encoding="utf-8")

    outcome = cmd_context_refresh(tmp_path, spec)

    assert outcome.status == "invalid"
    assert "ostler qa context --base" in outcome.message
