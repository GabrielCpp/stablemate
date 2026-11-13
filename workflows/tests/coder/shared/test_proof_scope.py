"""What a leftover change reopens: nothing, or the whole proof."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared.proof_scope import inert_paths, scope


def test_the_storys_own_markdown_is_inert_and_nothing_else_is(tmp_path: Path) -> None:
    dirty = [
        "repo:docs/epics/E/stories/S/story.md",
        "repo:docs/epics/E/stories/S/notes.md",
        "repo:docs/epics/E/stories/S/data.json",
        "repo:docs/epics/E/stories/S/sub/deep.md",
        "repo:src/app.py",
        "other:docs/epics/E/stories/S/story.md",
    ]

    inert = inert_paths("repo", tmp_path, "docs/epics/E/stories/S/story.md", dirty)

    assert inert == {
        "repo:docs/epics/E/stories/S/story.md",
        "repo:docs/epics/E/stories/S/notes.md",
    }


def test_only_inert_paths_reopen_nothing() -> None:
    assert scope(["repo:story.md"], {"repo:story.md"}).kind == "inert"
    assert scope([], set()).kind == "inert"


def test_any_product_leftover_reruns_the_whole_proof() -> None:
    result = scope(["repo:src/a.py", "repo:story.md"], {"repo:story.md"})

    assert result.kind == "whole"
    assert result.reasons == ["repo:src/a.py: changed after the passing QA saw it"]
