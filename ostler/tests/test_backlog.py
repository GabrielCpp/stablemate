from __future__ import annotations

from pathlib import Path

from ostler import backlog
from ostler.model import load


def test_create_backlog_item_persists_full_generated_id(tmp_path: Path) -> None:
    result = backlog.create(load(tmp_path), "Ship draft recovery", section="Scope", prefix="acme")

    assert result.ok
    assert result.entity_id.startswith("acme-")
    assert len(result.entity_id.split("-", 1)[1]) == 26
    text = (tmp_path / "docs/backlog.md").read_text(encoding="utf-8")
    assert f"- [{result.entity_id}] Ship draft recovery" in text
    assert backlog.items(load(tmp_path)) == [(result.entity_id, "Ship draft recovery")]


def test_adopt_names_every_bullet_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "docs/backlog.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "# Backlog\n\n"
        "1. Document the API integration\n\n"
        "## Decisions to Preserve\n\n"
        "- Preserve API-only browser access\n\n"
        "## Scope Items\n\n"
        "- Ship draft recovery across\n"
        "  interrupted browser sessions\n"
        "  - Preserve ten snapshots\n"
        "- [LEGACY-1] Keep named work\n\n"
        "## Filed by coder\n\n"
        "- Fix an adjacent defect\n\n"
        "## Open Questions\n\n"
        "- Choose the publisher\n",
        encoding="utf-8",
    )

    first = backlog.adopt(load(tmp_path), prefix="acme")
    adopted = path.read_text(encoding="utf-8")
    second = backlog.adopt(load(tmp_path), prefix="acme")

    assert first.ok and "adopted 6" in first.message
    assert second.ok and "adopted 0" in second.message
    assert path.read_text(encoding="utf-8") == adopted
    items = backlog.items(load(tmp_path))
    assert [text for _, text in items] == [
        "Document the API integration",
        "Preserve API-only browser access",
        "Ship draft recovery across\ninterrupted browser sessions",
        "Preserve ten snapshots",
        "Keep named work",
        "Fix an adjacent defect",
        "Choose the publisher",
    ]
    generated = [item_id for item_id, _ in items if item_id != "LEGACY-1"]
    assert all(item_id.startswith("acme-") and len(item_id.split("-", 1)[1]) == 26
               for item_id in generated)
    assert "  - [acme-" in adopted
    assert "1. [acme-" in adopted


def test_adopt_follows_the_configured_backlog_and_nothing_else(tmp_path: Path) -> None:
    """`docRoots:` moves the list, and adoption follows it — there is no path argument.

    The override this replaces could name a file outside the graph, so ids were minted into
    a list `ostler backlog` and `doctor` never read. Configuring it is the whole fix: one
    record of the location, and every reader on it.
    """
    (tmp_path / "ostler.yml").write_text(
        "organization:\n  docRoots:\n    backlog: docs/intake/worklist.md\n", encoding="utf-8"
    )
    custom = tmp_path / "docs/intake/worklist.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("# Backlog\n\n## Scope\n\n- Ship it\n", encoding="utf-8")

    result = backlog.adopt(load(tmp_path), prefix="acme")

    assert result.ok and "adopted 1" in result.message
    assert "[acme-" in custom.read_text(encoding="utf-8")
    assert not (tmp_path / "docs/backlog.md").exists()


def test_prune_refuses_to_discard_an_independently_identified_nested_item(
    tmp_path: Path,
) -> None:
    path = tmp_path / "docs/backlog.md"
    path.parent.mkdir(parents=True)
    original = (
        "# Backlog\n\n"
        "- [ACME-parent] Ship draft recovery\n"
        "  - [ACME-child] Preserve ten snapshots\n"
    )
    path.write_text(original, encoding="utf-8")

    result = backlog.prune(load(tmp_path), "ACME-parent")

    assert not result.ok
    assert "nested items" in result.message
    assert path.read_text(encoding="utf-8") == original
