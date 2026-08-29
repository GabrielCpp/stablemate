"""Preparation contracts for story-aware multi-repository OKF builds."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.okf_builder.main.nodes.incremental import (
    check_incremental_context,
)
from workhorse_workflows.okf_builder.main.nodes.prepare import prepare
from workhorse_workflows.okf_builder.shared.schemas import SourceRequest


def test_external_story_key_seeds_one_qualified_changed_function(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, source, workspace, request, story_id = incremental_repos("case", True)

    result = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )

    assert result.ostler_ok, result.prepare_error
    assert result.mode == "incremental"
    assert result.story_id == story_id
    assert result.source_checkouts == {"api-service": str(source)}
    assert len(result.initial_items) == 1
    item = result.initial_items[0]
    assert item["kind"] == "change"
    assert item["requeue"] is True
    context = json.loads(item["context"])
    assert context["repository"] == "api-service"
    assert context["refs"] == [
        "repo://api-service/src/service.py::create_invoice"
    ]
    assert context["directNodes"]
    assert context["story"]["acceptanceCriteria"] == [
        {
            "id": "ac:1",
            "requirement": "AC-1: Creating an invoice returns its identifier.",
            "kind": "behavioral",
        }
    ]


def test_story_content_changes_do_not_share_worklist_memory(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, _source, workspace, request, _story_id = incremental_repos("case", True)
    first = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )
    story_file = Path(first.story_path)
    story_file.write_text(
        story_file.read_text(encoding="utf-8") + "\nA clarified constraint.\n",
        encoding="utf-8",
    )

    second = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )

    assert first.scope_id != second.scope_id
    assert first.worklist_path != second.worklist_path
    assert Path(first.worklist_path).is_file()
    assert Path(second.worklist_path).is_file()


def test_source_content_changes_do_not_share_worklist_memory(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, source, workspace, request, _story_id = incremental_repos("case", True)
    first = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )
    (source / "src/service.py").write_text(
        "def create_invoice():\n    return 'newer'\n", encoding="utf-8"
    )

    second = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )

    assert first.scope_id != second.scope_id
    assert first.worklist_path != second.worklist_path


def test_two_source_roots_in_one_repository_share_one_repository_context(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, source, workspace, request, _story_id = incremental_repos("case", False)
    second = source / "worker/jobs.py"
    second.parent.mkdir(parents=True)
    second.write_text("def dispatch_invoice():\n    return 'old'\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "add worker"], cwd=source, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (source / "src/service.py").write_text(
        "def create_invoice():\n    return 'new'\n", encoding="utf-8"
    )
    second.write_text("def dispatch_invoice():\n    return 'new'\n", encoding="utf-8")
    sources = (
        request.model_copy(update={"base": base}),
        SourceRequest(
            repo="api-service",
            surface="billing-worker",
            root="worker",
            base=base,
        ),
    )

    result = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=sources,
    )

    assert result.ostler_ok, result.prepare_error
    assert len(result.packet["repositories"]) == 1
    assert result.packet["repositories"][0]["scopes"] == [
        {"surface": "billing", "root": "src"},
        {"surface": "billing-worker", "root": "worker"},
    ]
    assert len(result.packet["changedUnits"]) == 2


def test_unmapped_change_is_seeded_instead_of_rejected(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, _source, workspace, request, _story_id = incremental_repos("case", True)
    (docs / "docs/features/billing/concepts/create-invoice.md").unlink()
    subprocess.run(["git", "add", "-A"], cwd=docs, check=True)
    subprocess.run(
        ["git", "commit", "-qm", "remove stale mapping"], cwd=docs, check=True
    )

    result = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )

    assert result.ostler_ok, result.prepare_error
    assert len(result.initial_items) == 1
    context = json.loads(result.initial_items[0]["context"])
    assert context["healthFindings"][0]["kind"] == "unmapped-change"


def test_deleted_source_unit_is_seeded_for_documentation_cleanup(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, source, workspace, request, _story_id = incremental_repos("case", False)
    (source / "src/service.py").unlink()

    result = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )

    assert result.ostler_ok, result.prepare_error
    assert len(result.initial_items) == 1
    context = json.loads(result.initial_items[0]["context"])
    assert context["deleted"] is True
    assert context["refs"] == [
        "repo://api-service/src/service.py::create_invoice"
    ]


def test_incremental_check_requeues_doctor_error_on_affected_document(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, _source, workspace, request, story_id = incremental_repos("case", True)
    prepared = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )
    concept = docs / "docs/features/billing/concepts/create-invoice.md"
    concept.write_text(
        concept.read_text(encoding="utf-8")
        + "\n- code: `repo://api-service/src/service.py::missing`\n",
        encoding="utf-8",
    )

    result = check_incremental_context(
        logger,
        str(docs),
        prepared.spec_path,
        story_id,
        prepared.story_path,
        (request,),
        prepared.source_checkouts,
        prepared.baseline_doctor_errors,
    )

    assert not result.clean
    assert result.signature
    assert any(item["kind"] == "fix:missing-code-symbol" for item in result.items)


def test_incremental_check_requeues_body_only_source_drift(
    incremental_repos: Callable[
        [str, bool], tuple[Path, Path, Path, SourceRequest, str]
    ],
    logger: logging.Logger,
) -> None:
    docs, source, workspace, request, story_id = incremental_repos("case", True)
    prepared = prepare(
        logger,
        docs_path=str(docs),
        repo_dir=str(docs),
        service="billing",
        story="TEAM-123",
        workspace_file=str(workspace),
        sources=(request,),
    )
    (source / "src/service.py").write_text(
        "def create_invoice():\n    return 'changed after documentation'\n",
        encoding="utf-8",
    )

    result = check_incremental_context(
        logger,
        str(docs),
        prepared.spec_path,
        story_id,
        prepared.story_path,
        (request,),
        prepared.source_checkouts,
        prepared.baseline_doctor_errors,
    )

    refresh = next(item for item in result.items if item["kind"] == "refresh:source")
    assert not result.clean
    assert refresh["target"] == "api-service"
    assert json.loads(refresh["context"])["status"] == "stale"


def test_bulk_prepare_keeps_the_legacy_worklist_scope(
    booked: Path, logger: logging.Logger
) -> None:
    result = prepare(logger, service="acme")

    assert result.mode == "bulk"
    assert result.scope_id == "bulk"
    assert Path(result.worklist_path).name == "acme.worklist.json"
