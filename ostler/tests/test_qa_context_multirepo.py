from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

from ostler import doctor
from ostler.model import load
from ostler.qa.context import build_context, cmd_context, validate_context
from ostler.qa.source_context import SourceRepository, SourceScope
from ostler.provenance import source_freshness
from ostler.source_snapshots import catalog_path


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
    (docs / "docs/features/billing").mkdir(parents=True)
    story = docs / "docs/epics/billing/stories/create-invoice/story.md"
    story.parent.mkdir(parents=True)
    story.write_text(
        "---\nid: BILL-01ABCDEF\nexternalKey: TEAM-123\nslug: create-invoice\n"
        "type: story\n---\n# Create invoice\n",
        encoding="utf-8",
    )
    (source / "src").mkdir(parents=True)
    (docs / "docs/features/billing/create.md").write_text(
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
        "externalKey": "TEAM-123",
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
    assert source_freshness(load(docs), packet, {"api-service": source})[0]["status"] == "fresh"

    _git(source, "add", ".")
    _git(source, "commit", "-m", "record story work")
    assert source_freshness(load(docs), packet, {"api-service": source})[0]["status"] == "fresh"

    implementation.write_text(
        "def create_invoice():\n    return 'newer'\n", encoding="utf-8"
    )
    freshness = source_freshness(load(docs), packet, {"api-service": source})[0]
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
    freshness = source_freshness(load(docs), refreshed, {"api-service": source})[0]
    assert freshness["status"] == "stale"


def test_external_file_owner_reason_keeps_repository_qualification(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    (docs / "docs/features/billing").mkdir(parents=True)
    (source / "src").mkdir(parents=True)
    (docs / "docs/features/billing/create.md").write_text(
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
    (docs / "docs/features/billing").mkdir(parents=True)
    (docs / "docs/features/billing/create.md").write_text(
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


def test_source_catalog_grounds_external_ref_without_live_checkout(tmp_path: Path) -> None:
    docs = tmp_path / "product-docs"
    source = tmp_path / "api-service"
    (docs / "docs/features/billing").mkdir(parents=True)
    (source / "src").mkdir(parents=True)
    (docs / "docs/features/billing/create.md").write_text(
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
        docs / "docs/specs/story",
        base=docs_base,
        repositories=(repository,),
    )

    assert outcome.ok, outcome.message
    assert catalog_path(docs).is_file()
    shutil.rmtree(source)
    grounding = {
        finding.code
        for finding in doctor.run(load(docs)).findings
        if finding.code in {
            "dangling-repository-ref",
            "dangling-code-ref",
            "missing-code-symbol",
        }
    }
    assert grounding == set()
