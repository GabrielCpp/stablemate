"""Tests for local versus multi-repo documentation context selection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from workhorse.testing import make_git_repo

from conftest import WORKFLOW


SCRIPT = WORKFLOW.parent / "scripts" / "classify-documentation-context.py"


def _run(docs_root: Path, roots: list[str]) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(docs_root), json.dumps(roots)],
        cwd=docs_root,
        env={**os.environ, "AGENT_REPO_DIR": str(docs_root)},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_local_service_root_is_normalized_relative_to_docs_worktree(tmp_path):
    make_git_repo(tmp_path)
    service = tmp_path / "services/api"
    service.mkdir(parents=True)

    result = _run(tmp_path, [f"api={service}"])

    assert result["documentation_context_mode"] == "local"
    assert json.loads(result["documentation_source_roots_json"]) == [
        "api=services/api"
    ]


def test_external_service_root_uses_semantic_review_mode(tmp_path):
    docs = tmp_path / "docs-repo"
    service = tmp_path / "api-service"
    docs.mkdir()
    service.mkdir()
    make_git_repo(docs)
    make_git_repo(service)

    result = _run(docs, [f"api={service}"])

    assert result["documentation_context_mode"] == "semantic"
    assert json.loads(result["documentation_source_roots_json"]) == []
