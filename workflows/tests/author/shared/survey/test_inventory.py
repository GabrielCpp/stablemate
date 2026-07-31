"""`expand_inventory` and `split_unit` — materializing the frozen unit list, and the one
sanctioned correction to it.

The exhaustiveness claim of the whole survey rests on the inventory file, so these tests
are about the claim rather than the plumbing: the list is complete by construction, it is
frozen once written, an empty or unmatched rule is an error and not a clean survey, and a
split replaces a unit *in place* so lineage stays detectable.

Ported from `surveyor/scripts/{expand-inventory,split-unit}.py`.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse_workflows.author.shared.survey import (
    expand_inventory,
    record_slug,
    split_unit,
)

Write = Callable[[Path, str], Path]
WriteJson = Callable[[Path, Any], Path]
ReadJson = Callable[[Path], Any]

INVENTORY = "docs/survey/inventory.json"
RULES = "docs/survey/units.yml"


def _tree(repo: Path) -> None:
    """A small source tree with two areas, a vendored one, and a loose file."""
    for rel in (
        "src/api/handler.py",
        "src/web/page.tsx",
        "vendor/lib/thing.py",
        "README.md",
    ):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")


# ------------------------------------------------------------------ record slugs


def test_a_record_slug_is_filename_safe_and_lowercased() -> None:
    assert record_slug("src/api/handler.py") == "src-api-handler-py"
    assert record_slug("legacy/Reports/Q1 view") == "legacy-reports-q1-view"


# --------------------------------------------------------------------- expansion


def test_folder_rules_materialize_the_unit_list(
    repo: Path, logger: logging.Logger, write: Write, read_json: ReadJson
) -> None:
    _tree(repo)
    write(repo / RULES, "rules:\n  - kind: folder\n    glob: src/*\n")

    result = expand_inventory(logger)

    assert result.expand_ok is True
    assert result.unit_count == 2
    data = read_json(repo / INVENTORY)
    assert [u["id"] for u in data["units"]] == ["src/api", "src/web"]
    assert {u["status"] for u in data["units"]} == {"pending"}
    assert {u["kind"] for u in data["units"]} == {"folder"}
    # The inventory records which rules produced it, which is what `split_unit` reads
    # back to keep split children behind the same exclude fence.
    assert data["rules"] == RULES


def test_exclude_patterns_fence_the_enumeration(
    repo: Path, logger: logging.Logger, write: Write, read_json: ReadJson
) -> None:
    _tree(repo)
    # The patterns are fnmatched against the *matched* entry's repo-relative path, so a
    # rule enumerating top-level folders is fenced by `vendor`, not by `vendor/*`.
    write(
        repo / RULES,
        "exclude:\n  - vendor\n  - .git\nrules:\n  - kind: folder\n    glob: '*'\n",
    )

    result = expand_inventory(logger)

    ids = [u["id"] for u in read_json(repo / INVENTORY)["units"]]
    assert result.expand_ok is True
    assert "vendor" not in ids
    assert "src" in ids


def test_a_command_rule_enumerates_what_it_prints(
    repo: Path, logger: logging.Logger, write: Write, read_json: ReadJson
) -> None:
    """Glob and command expansion are the two shapes; both make the list complete by
    construction, which an agent listing paths would not."""
    write(
        repo / RULES,
        "rules:\n"
        "  - kind: command\n"
        "    unit_kind: endpoint\n"
        "    command: printf 'GET /a\\nGET /b\\n'\n",
    )

    result = expand_inventory(logger)

    assert result.expand_ok is True
    units = read_json(repo / INVENTORY)["units"]
    assert [u["id"] for u in units] == ["GET /a", "GET /b"]
    assert {u["kind"] for u in units} == {"endpoint"}


def test_a_command_that_prints_nothing_is_a_rules_problem(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """An empty enumeration is never a clean survey — the whole point of the gate."""
    write(
        repo / RULES,
        "rules:\n  - kind: command\n    unit_kind: endpoint\n    command: 'true'\n",
    )

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "emitted no units" in result.expand_errors
    assert not (repo / INVENTORY).exists()


def test_a_glob_matching_nothing_is_an_error_not_an_empty_survey(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / RULES, "rules:\n  - kind: folder\n    glob: nowhere/*\n")

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "matched no folders" in result.expand_errors


def test_structural_rule_errors_are_reported_together(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """Validation is structural and complete before any expansion runs, so the planner's
    rework turn sees every problem at once rather than the first one."""
    write(
        repo / RULES,
        "rules:\n  - kind: sideways\n    glob: src/*\n  - kind: file\n    glob: ''\n",
    )

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "rules[0] kind 'sideways'" in result.expand_errors
    assert "rules[1] (file) missing non-empty `glob`" in result.expand_errors


def test_a_command_rule_must_say_what_a_line_is(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / RULES, "rules:\n  - kind: command\n    command: echo hi\n")

    result = expand_inventory(logger)

    assert "missing non-empty `unit_kind`" in result.expand_errors


def test_units_colliding_on_a_record_slug_are_rejected(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """Two ids sharing a slug would share one finding record, so per-unit coverage would
    be a claim about a file that two units overwrite in turn."""
    (repo / "a.b").write_text("x\n", encoding="utf-8")
    (repo / "a-b").write_text("x\n", encoding="utf-8")
    write(repo / RULES, "rules:\n  - kind: file\n    glob: 'a*'\n")

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "collide on record slug" in result.expand_errors


def test_a_missing_rules_file_waits_for_the_planner(
    repo: Path, logger: logging.Logger
) -> None:
    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "no rules file" in result.expand_errors


def test_an_existing_inventory_is_consumed_verbatim(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """The freeze, from the other side: rules that would enumerate something else are
    not even read, and the counts in the note come from the file on disk."""
    write_json(
        repo / INVENTORY,
        {
            "version": 1,
            "units": [
                {"id": "kept/one", "path": "kept/one", "kind": "folder", "status": "pending"},
                {"id": "kept/two", "path": "kept/two", "kind": "folder", "status": "assessed"},
            ],
        },
    )
    _tree(repo)
    write(repo / RULES, "rules:\n  - kind: folder\n    glob: src/*\n")

    result = expand_inventory(logger)

    assert result.expand_ok is True
    assert result.unit_count == 2
    assert "1 still pending" in result.inventory_note
    # Untouched: the frozen list is the coverage baseline.
    assert "src/api" not in (repo / INVENTORY).read_text(encoding="utf-8")


def test_an_unparseable_inventory_stops_rather_than_re_expanding(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """Re-expanding over a corrupt baseline would replace the coverage claim silently,
    so the node refuses and names the file to fix."""
    write(repo / INVENTORY, "{ this is not json\n")

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "frozen coverage baseline" in result.expand_errors


def test_an_inventory_without_a_units_list_is_the_same_refusal(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / INVENTORY, '{"version": 1}\n')

    result = expand_inventory(logger)

    assert result.expand_ok is False
    assert "not parseable JSON with a `units` list" in result.expand_errors


# ----------------------------------------------------------------------- splitting


def test_a_split_replaces_the_unit_in_place(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    """In place, and only that unit: the rest of the frozen list is untouched, which is
    what keeps the coverage claim alive across the correction."""
    _tree(repo)
    write_json(
        repo / INVENTORY,
        {
            "version": 1,
            "rules": RULES,
            "units": [
                {"id": "README.md", "path": "README.md", "kind": "file", "status": "clean"},
                {"id": "src", "path": "src", "kind": "folder", "status": "pending"},
                {"id": "vendor", "path": "vendor", "kind": "folder", "status": "blocked"},
            ],
        },
    )
    write(repo / RULES, "rules:\n  - kind: folder\n    glob: '*'\n")

    result = split_unit(logger, INVENTORY, "src")

    assert result.split_ok is True
    assert result.children_count == 2
    units = read_json(repo / INVENTORY)["units"]
    assert [u["id"] for u in units] == ["README.md", "src/api", "src/web", "vendor"]
    # The children start pending, and every child path extends the parent's — which is
    # how `verify_records` tells a split from a silent drop.
    assert [u["status"] for u in units[1:3]] == ["pending", "pending"]


def test_split_children_honor_the_rules_excludes(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    _tree(repo)
    (repo / "src/api/__pycache__").mkdir()
    write_json(
        repo / INVENTORY,
        {
            "version": 1,
            "rules": RULES,
            "units": [{"id": "src/api", "path": "src/api", "kind": "folder", "status": "pending"}],
        },
    )
    write(
        repo / RULES,
        "exclude:\n  - '*/__pycache__'\nrules:\n  - kind: folder\n    glob: src/*\n",
    )

    result = split_unit(logger, INVENTORY, "src/api")

    ids = [u["id"] for u in read_json(repo / INVENTORY)["units"]]
    assert result.split_ok is True
    assert ids == ["src/api/handler.py"]


def test_only_folder_units_can_split(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """A file or command unit has no children: the assessor assesses it or blocks it."""
    _tree(repo)
    write_json(
        repo / INVENTORY,
        {
            "version": 1,
            "units": [
                {"id": "README.md", "path": "README.md", "kind": "file", "status": "pending"}
            ],
        },
    )

    result = split_unit(logger, INVENTORY, "README.md")

    assert result.split_ok is False
    assert "only folder units can split" in result.split_errors


def test_a_folder_with_no_splittable_children_says_so(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    (repo / "empty").mkdir()
    write_json(
        repo / INVENTORY,
        {
            "version": 1,
            "units": [{"id": "empty", "path": "empty", "kind": "folder", "status": "pending"}],
        },
    )

    result = split_unit(logger, INVENTORY, "empty")

    assert result.split_ok is False
    assert "no splittable children" in result.split_errors


def test_splitting_an_unknown_unit_is_reported_not_raised(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"version": 1, "units": []})

    result = split_unit(logger, INVENTORY, "ghost")

    assert result.split_ok is False
    assert "not found" in result.split_errors


def test_split_requires_both_arguments(repo: Path, logger: logging.Logger) -> None:
    assert "both required" in split_unit(logger, "", "src").split_errors
    assert "both required" in split_unit(logger, INVENTORY, "  ").split_errors
