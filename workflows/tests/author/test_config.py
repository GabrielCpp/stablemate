from __future__ import annotations

import logging
from pathlib import Path

import workhorse_workflows
from workhorse_workflows.author.main.nodes.config import load_config


def test_author_config_never_invents_a_surface_inventory(tmp_path: Path) -> None:
    backlog = tmp_path / "docs/backlog.md"
    backlog.parent.mkdir(parents=True)
    backlog.write_text("# Backlog\n", encoding="utf-8")
    survey_manifest = tmp_path / "docs/survey/unit-manifest.json"
    survey_manifest.parent.mkdir(parents=True)
    survey_manifest.write_text("{}\n", encoding="utf-8")
    (tmp_path / "agents.yml").write_text(
        "template:\n  surface_manifest: docs/features/inventory.json\n",
        encoding="utf-8",
    )

    config = load_config(logging.getLogger("test.author"), repo_dir=str(tmp_path))

    assert "surface_manifest" not in config.model_dump()
    assert not (tmp_path / "docs/features/inventory.json").exists()


def test_design_prompt_has_no_inventory_write_contract() -> None:
    # Both flows that design a mockup ship their own copy of the envelope, and a write
    # contract reintroduced in either one is the defect this guards.
    author = Path(workhorse_workflows.__file__).parent / "author"
    copies = sorted(author.glob("*/prompts/design-mockup.md"))
    assert copies, "no flow ships design-mockup.md"

    for path in copies:
        prompt = path.read_text(encoding="utf-8")

        assert "surface_manifest" not in prompt, path
        assert "inventory.json" not in prompt, path
        assert "manifest entry" not in prompt, path
