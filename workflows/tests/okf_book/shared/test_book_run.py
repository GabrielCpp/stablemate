"""The run brings up the stack its own book declares, not the first stack another book declares."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from workhorse_workflows.kit.qa import runner
from workhorse_workflows.okf_book.shared.book_run import bring_up

PREVIEW = (
    "---\ntype: environment\nslug: preview\ntitle: Preview\n---\n# Preview\n\n"
    "- selector: local-only\n- local-only: true\n"
)
WEB_STACK = Path("docs/features/web-app/ops/web-app-stack.md")


def _split_environments(repo: Path) -> Path:
    _ = (repo / WEB_STACK.parent / "preview.md").write_text(PREVIEW, encoding="utf-8")
    stack = repo / WEB_STACK
    text = stack.read_text(encoding="utf-8")
    _ = stack.write_text(text.replace("[local](../../api-service/ops/local.md)", "[preview](preview.md)"), encoding="utf-8")
    return repo


@pytest.fixture
def brought_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sources: list[str] = []

    def _bring_up(manifests: list[dict[str, object]], **_kwargs: object) -> list[dict[str, str]]:
        sources.extend(str(manifest.get("source", "")) for manifest in manifests)
        return [{"ready": "yes"}]

    monkeypatch.setattr(runner.runbook, "bring_up_stacks", _bring_up)
    return sources


def test_a_service_brings_up_the_stack_its_own_book_declares(app: Callable[[str], Path], brought_up: list[str]) -> None:
    repo = _split_environments(app("globex"))

    readiness = bring_up(logging.getLogger(__name__), repo, "web-app")

    assert readiness.serving
    assert brought_up == [WEB_STACK.as_posix()]


def test_another_service_leaves_that_stack_down(app: Callable[[str], Path], brought_up: list[str]) -> None:
    repo = _split_environments(app("globex"))

    _ = bring_up(logging.getLogger(__name__), repo, "api-service")

    assert "docs/features/api-service/ops/api-service-stack.md" in brought_up
    assert WEB_STACK.as_posix() not in brought_up
