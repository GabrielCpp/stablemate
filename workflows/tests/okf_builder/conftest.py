"""Shared fixtures for the okf-builder port's tests.

The build is a measurement instrument — `ostler doctor` over the book and a computed
join of the book's `code:` citations against an inventory walked from source — so a
useful fixture is a *real* repo whose source and whose book actually correspond. That is
what `booked` is: one module declaring one function, and one concept doc citing it. Two
units, both covered, doctor green.

`dirty` is the same repo plus a doc citing a symbol nothing declares, which is the
cheapest way to make doctor emit an **error** that is neither auto-repairable by
`ostler fmt` nor in `AUTO_WAIVABLE` — the two arms the convergence loop branches on.

Everything else follows the author suite: nodes run for real against the repo the test
stands in, and only the agent turn is ever scripted.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ostler import Ostler

from workhorse_workflows.okf_builder.shared.schemas import SourceRequest

#: The book, the source subtree and the package all share this name — `prepare` defaults
#: `source_path` to `service`, so a one-input run resolves `<repo>/acme`.
SERVICE = "acme"

SOURCE = '''"""The billing service."""


def charge(amount):
    """Charge an amount."""
    return amount
'''

#: A minimal OKF concept. The `- code:` bullet is the citation the coverage join reads
#: and the reference `ostler doctor` grounds against the source file.
CONCEPT = """---
type: concept
slug: {slug}
title: {title}
---
# {title}

- code: `acme/service.py::{symbol}`

{prose}
"""


@pytest.fixture
def logger() -> logging.Logger:
    """The `logger` every node takes first. Diagnostics only — nothing asserts on it."""
    return logging.getLogger("test.okf_builder")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real git repo, pinned as the consuming repo for the duration of the test.

    Pinned by *chdir*, not by an environment variable: `docs_root` resolves the explicit
    `docs_path`, else walks up from `repo_dir`, else from the working directory — so
    standing in the repo is what a node called with neither input sees.
    """
    root = tmp_path / "acme"
    root.mkdir()
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL)
    # The smallest installed skill `prepare._references_ok` accepts: the references corpus
    # is a run precondition (a build whose prompts point at pages that do not exist is
    # blocked, not degraded), so a repo without it never gets past `start`.
    references = root / ".claude/skills/ostler-okf/references"
    (references / "node-types").mkdir(parents=True)
    (references / "node-types" / "concept.md").write_text("# concept\n", encoding="utf-8")
    (references / "bullet-grammar.md").write_text("# bullet grammar\n", encoding="utf-8")
    (references / "check-vocabulary.md").write_text("# checks\n", encoding="utf-8")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def write() -> Callable[[Path, str], Path]:
    """Write text to a path, creating parents. Returns the path, for one-liners."""

    def _write(path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def read_json() -> Callable[[Path], Any]:
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    return _read_json


@pytest.fixture
def booked(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """A repo whose one-function source is exactly covered by its one-doc book.

    Committed, because `ostler` and the checkpoint's `fmt` both read a working tree and
    because a build that starts from an uncommitted book is not the state a real run
    resumes into.
    """
    write(repo / "acme/service.py", SOURCE)
    write(
        repo / f"docs/features/{SERVICE}/concepts/charge.md",
        CONCEPT.format(slug="charge", title="Charge", symbol="charge", prose="Charging."),
    )
    _commit(repo, "seed")
    return repo


@pytest.fixture
def dirty(booked: Path, write: Callable[[Path, str], Path]) -> Path:
    """`booked` plus a doc citing `acme/service.py::refund`, which nothing declares.

    `ostler doctor` reports it as a `missing-code-symbol` **error** — grounded (the
    repair's value must come out of the source, not off the finding) and not in
    `waivers.AUTO_WAIVABLE`, so a stalled loop ends the run rather than papering over
    it. One fixture, both arms.
    """
    write(
        booked / f"docs/features/{SERVICE}/concepts/refund.md",
        CONCEPT.format(slug="refund", title="Refund", symbol="refund", prose="Refunding."),
    )
    _commit(booked, "a doc citing a symbol that does not exist")
    return booked


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["git", "commit", "-qm", message], cwd=repo, check=True, stdout=subprocess.DEVNULL
    )


@pytest.fixture
def incremental_repos(
    tmp_path: Path, write: Callable[[Path, str], Path]
) -> Callable[[str, bool], tuple[Path, Path, Path, SourceRequest, str]]:
    """Create independently-versioned docs/source repos for one story diff."""

    def make(
        name: str = "case", changed: bool = True
    ) -> tuple[Path, Path, Path, SourceRequest, str]:
        docs = tmp_path / name / "product-docs"
        source = tmp_path / name / "api-service"
        docs.mkdir(parents=True)
        source.mkdir(parents=True)
        for root in (docs, source):
            for args in (
                ("init", "-q", "-b", "main"),
                ("config", "user.email", "test@example.com"),
                ("config", "user.name", "Test"),
            ):
                subprocess.run(
                    ["git", *args], cwd=root, check=True, stdout=subprocess.DEVNULL
                )

        references = docs / ".claude/skills/ostler-okf/references"
        write(references / "node-types/concept.md", "# concept\n")
        write(references / "bullet-grammar.md", "# bullets\n")
        write(references / "check-vocabulary.md", "# checks\n")

        okf = Ostler(docs)
        created_epic = okf.create_epic("billing", "Billing", prefix="BILL")
        assert created_epic.ok
        created_story = okf.create_story("billing", "create-invoice", "Create invoice")
        assert created_story.ok
        found = okf.graph.find_story("create-invoice")
        assert found is not None
        story = found[1]
        assert story.story_md is not None
        story.story_md.write_text(
            story.story_md.read_text(encoding="utf-8")
            .replace("slug: create-invoice", "externalKey: TEAM-123\nslug: create-invoice")
            .replace(
                "## Context\n",
                "## Context\n\nAn operator creates an invoice from the billing surface.\n",
            )
            .replace(
                "## Acceptance Criteria\n",
                "## Acceptance Criteria\n\n- AC-1: Creating an invoice returns its identifier.\n",
            ),
            encoding="utf-8",
        )
        write(
            docs / "docs/features/billing/concepts/create-invoice.md",
            """---
type: concept
title: Create invoice
---
# Create invoice

- code: `repo://api-service/src/service.py::create_invoice`
""",
        )
        _commit(docs, "seed docs")

        implementation = write(
            source / "src/service.py",
            "def create_invoice():\n    return 'old'\n",
        )
        _commit(source, "seed source")
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if changed:
            implementation.write_text(
                "def create_invoice():\n    return 'new'\n", encoding="utf-8"
            )

        workspace = tmp_path / name / "product.code-workspace"
        workspace.write_text(
            json.dumps(
                {
                    "folders": [
                        {"name": "product-docs", "path": "product-docs"},
                        {"name": "api-service", "path": "api-service"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return (
            docs,
            source,
            workspace,
            SourceRequest(repo="api-service", surface="billing", root="src", base=base),
            story.eid,
        )

    return make
