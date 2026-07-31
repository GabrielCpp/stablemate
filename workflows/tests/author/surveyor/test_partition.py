"""`validate_partition` and `emit_artifacts` — the last two links in the surveyor's
exhaustiveness chain.

The partitioner is an agent doing genuine synthesis, so these tests are about the one
property that must survive that judgment: clustering may reorganize the findings any way it
likes, but it may not lose one. Then `emit_artifacts` turns the validated clusters into
author's existing input, idempotently, without touching anything a human wrote.

Ported from `surveyor/scripts/{validate-partition,emit-artifacts}.py`.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from workhorse_workflows.author.surveyor.nodes import emit_artifacts, validate_partition
from workhorse_workflows.author.surveyor.nodes.partition import SECTION_BEGIN, SECTION_END

Write = Callable[[Path, str], Path]
WriteJson = Callable[[Path, Any], Path]
ReadJson = Callable[[Path], Any]

PARTITION = "docs/survey/partition.yaml"
INVENTORY = "docs/survey/inventory.json"
BACKLOG = "docs/backlog.md"
MANIFEST = "docs/survey/unit-manifest.json"


def _cluster(cid: str, units: list[str], **over: Any) -> dict:
    cluster = {
        "id": cid,
        "title": f"Remediate {cid}",
        "remediation_pattern": cid,
        "strategy": "mechanical",
        "units": units,
    }
    cluster.update(over)
    return cluster


def _unit(unit_id: str, status: str = "assessed", **over: Any) -> dict:
    unit = {"id": unit_id, "path": unit_id, "kind": "folder", "status": status}
    unit.update(over)
    return unit


def _setup(
    write: Write,
    write_json: WriteJson,
    repo: Path,
    clusters: list[dict],
    units: list[dict],
) -> None:
    write(repo / PARTITION, yaml.safe_dump({"clusters": clusters}, sort_keys=False))
    write_json(repo / INVENTORY, {"version": 1, "units": units})


# --------------------------------------------------------------- validate_partition


def test_a_partition_covering_every_assessed_unit_is_valid(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("missing-error-handling", ["src/api", "src/web"])],
        [_unit("src/api"), _unit("src/web"), _unit("README.md", "clean")],
    )

    result = validate_partition(logger)

    assert result.partition_ok is True
    assert result.partition_errors == ""


def test_an_assessed_unit_in_no_cluster_is_the_gate(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """The whole reason this node exists: a unit with findings and no cluster would fall
    out of the generated backlog with nothing looking wrong."""
    _setup(
        write,
        write_json,
        repo,
        [_cluster("missing-error-handling", ["src/api"])],
        [_unit("src/api"), _unit("src/web")],
    )

    result = validate_partition(logger)

    assert result.partition_ok is False
    assert "assessed unit 'src/web' appears in NO cluster" in result.partition_errors
    assert "silently drop out of the generated backlog" in result.partition_errors


def test_clean_units_need_no_cluster(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """No findings, no remediation work — so a clean unit in a cluster is the error, not a
    clean unit outside one."""
    _setup(
        write,
        write_json,
        repo,
        [_cluster("missing-error-handling", ["src/api"])],
        [_unit("src/api"), _unit("src/web", "clean"), _unit("src/cli", "blocked")],
    )

    assert validate_partition(logger).partition_ok is True


def test_a_cluster_may_not_invent_a_unit(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """Clusters partition the frozen list. A unit that is not in it was never assessed, so
    a story built on it would have no evidence behind it."""
    _setup(
        write,
        write_json,
        repo,
        [_cluster("missing-error-handling", ["src/api", "src/ghost"])],
        [_unit("src/api")],
    )

    errors = validate_partition(logger).partition_errors

    assert "names unit 'src/ghost' which is not in the inventory" in errors
    assert "they never invent units" in errors


def test_a_cluster_naming_a_non_assessed_unit_is_rejected(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("missing-error-handling", ["src/api", "src/web"])],
        [_unit("src/api"), _unit("src/web", "clean")],
    )

    errors = validate_partition(logger).partition_errors

    assert "whose status is 'clean' — only `assessed` units carry work" in errors


def test_every_structural_cluster_error_is_reported_together(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [
            {
                "id": "Not A Slug",
                "title": "   ",
                "strategy": "vibes",
                "remediation_pattern": "Nope",
                "units": [],
            }
        ],
        [_unit("src/api")],
    )

    errors = validate_partition(logger).partition_errors

    assert "must be a kebab-case slug (it becomes the backlog bullet's [id])" in errors
    assert "missing non-empty `title`" in errors
    assert "strategy 'vibes' not one of ['dedicated', 'mechanical']" in errors
    assert "`remediation_pattern` must be a kebab-case slug" in errors
    assert "must list at least one unit" in errors
    # And the orphan sweep still runs — a structural failure does not hide a lost unit.
    assert "assessed unit 'src/api' appears in NO cluster" in errors


def test_duplicate_cluster_ids_are_rejected(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """Two clusters with one id would emit two bullets sharing a traceability handle."""
    _setup(
        write,
        write_json,
        repo,
        [_cluster("same-id", ["src/api"]), _cluster("same-id", ["src/web"])],
        [_unit("src/api"), _unit("src/web")],
    )

    assert "duplicate id 'same-id'" in validate_partition(logger).partition_errors


def test_a_missing_partition_file_waits_for_the_partitioner(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})

    result = validate_partition(logger)

    assert result.partition_ok is False
    assert "the partitioner must write it" in result.partition_errors


def test_an_unparseable_partition_file_is_named_as_such(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})
    write(repo / PARTITION, "clusters:\n  - id: [unclosed\n")

    assert "not valid YAML" in validate_partition(logger).partition_errors


def test_an_empty_clusters_list_is_not_a_partition(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})
    write(repo / PARTITION, "clusters: []\n")

    assert (
        "must carry a non-empty `clusters:` list" in validate_partition(logger).partition_errors
    )


def test_a_missing_inventory_stops_the_gate(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / PARTITION, yaml.safe_dump({"clusters": [_cluster("x", ["src/api"])]}))

    assert "could not be read" in validate_partition(logger).partition_errors


# ------------------------------------------------------------------- emit_artifacts


def test_one_bullet_per_cluster_lands_in_the_fenced_section(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [
            _cluster("missing-error-handling", ["src/api", "src/web"]),
            _cluster("datepicker-keyboard-model", ["src/cli"], strategy="dedicated"),
        ],
        [_unit("src/api"), _unit("src/web"), _unit("src/cli")],
    )

    result = emit_artifacts(logger)

    assert result.emit_ok is True
    assert result.bullet_count == 2
    text = (repo / BACKLOG).read_text(encoding="utf-8")
    assert SECTION_BEGIN in text and SECTION_END in text
    assert "- [survey-missing-error-handling] Remediate missing-error-handling (" in text
    # The bullet carries the hints author needs to keep a mechanical cluster as one story.
    assert "2 unit(s), mechanical checklist — keep as ONE story with a per-unit checklist" in text
    assert "1 unit(s), dedicated)" in text


def test_cluster_notes_ride_along_as_a_hint(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("x-y", ["src/api"], notes="do the api\nfirst")],
        [_unit("src/api")],
    )

    emit_artifacts(logger)

    # Flattened to one line: the bullet is one line of markdown.
    assert "do the api first)" in (repo / BACKLOG).read_text(encoding="utf-8")


def test_an_explicit_order_key_sequences_the_bullets(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """Ordering hints are the partitioner's other job; ids break ties so the emission is
    deterministic across runs."""
    _setup(
        write,
        write_json,
        repo,
        [
            _cluster("zebra", ["src/api"], order=2),
            _cluster("aardvark", ["src/web"], order=1),
        ],
        [_unit("src/api"), _unit("src/web")],
    )

    emit_artifacts(logger)

    text = (repo / BACKLOG).read_text(encoding="utf-8")
    assert text.index("survey-aardvark") < text.index("survey-zebra")


def test_re_emitting_replaces_the_section_and_nothing_else(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """The idempotence property. A human-curated backlog and coder's own filed section sit
    outside the fence, and a second survey run must not disturb them."""
    write(
        repo / BACKLOG,
        "# Backlog\n\n- [hand-written] something a human wants\n\n"
        "## Filed by coder\n\n- [coder-1] a defect coder found\n",
    )
    _setup(write, write_json, repo, [_cluster("first-pass", ["src/api"])], [_unit("src/api")])
    emit_artifacts(logger)

    _setup(write, write_json, repo, [_cluster("second-pass", ["src/api"])], [_unit("src/api")])
    emit_artifacts(logger)

    text = (repo / BACKLOG).read_text(encoding="utf-8")
    assert "- [hand-written] something a human wants" in text
    assert "- [coder-1] a defect coder found" in text
    assert "survey-first-pass" not in text
    assert text.count("survey-second-pass") == 1
    assert text.count(SECTION_BEGIN) == 1


def test_a_backlog_that_does_not_exist_yet_is_created(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(write, write_json, repo, [_cluster("x-y", ["src/api"])], [_unit("src/api")])

    emit_artifacts(logger)

    text = (repo / BACKLOG).read_text(encoding="utf-8")
    assert text.startswith("# Backlog\n\n## Survey findings\n")


def test_the_manifest_carries_every_unit_and_what_covers_it(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    """Every unit, not just the clustered ones — the manifest is the frozen list with the
    traceability hop attached, and a unit with no work says so by carrying no bullets."""
    _setup(
        write,
        write_json,
        repo,
        [
            _cluster("missing-error-handling", ["src/api", "src/web"]),
            _cluster("naming", ["src/api"], strategy="dedicated"),
        ],
        [_unit("src/api"), _unit("src/web"), _unit("README.md", "clean", kind="file")],
    )

    result = emit_artifacts(logger)

    manifest = read_json(repo / MANIFEST)
    assert manifest["version"] == 1
    assert manifest["generatedBy"] == "surveyor"
    assert manifest["inventory"] == INVENTORY
    by_id = {u["id"]: u for u in manifest["units"]}
    assert set(by_id) == {"src/api", "src/web", "README.md"}
    # One unit covered by two clusters keeps both handles.
    assert by_id["src/api"]["bullets"] == ["survey-missing-error-handling", "survey-naming"]
    assert by_id["src/api"]["clusters"] == ["missing-error-handling", "naming"]
    assert by_id["README.md"]["bullets"] == []
    assert by_id["README.md"]["kind"] == "file"
    assert "3 unit(s)" in result.emit_note


def test_emission_refuses_when_the_partition_is_unreadable(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """`emit_artifacts` runs after the gate passed, so an unreadable partition here means
    the chain was skipped — it says so rather than writing an empty backlog section."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})

    result = emit_artifacts(logger)

    assert result.emit_ok is False
    assert "run the partition gate first" in result.emit_errors
    assert not (repo / BACKLOG).exists()


def test_emission_refuses_when_the_inventory_is_unreadable(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / PARTITION, yaml.safe_dump({"clusters": [_cluster("x-y", ["src/api"])]}))

    result = emit_artifacts(logger)

    assert result.emit_ok is False
    assert "could not be read" in result.emit_errors


def test_the_survey_directory_travels_with_the_parameters(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson
) -> None:
    partition = "docs/survey/legacy-vs-new/partition.yaml"
    inventory = "docs/survey/legacy-vs-new/inventory.json"
    backlog = "docs/legacy-backlog.md"
    manifest = "docs/survey/legacy-vs-new/unit-manifest.json"
    write(repo / partition, yaml.safe_dump({"clusters": [_cluster("x-y", ["legacy/q1"])]}))
    write_json(repo / inventory, {"units": [_unit("legacy/q1")]})

    check = validate_partition(logger, partition=partition, inventory=inventory)
    result = emit_artifacts(
        logger,
        partition=partition,
        inventory=inventory,
        backlog=backlog,
        unit_manifest=manifest,
    )

    assert check.partition_ok is True
    assert result.emit_ok is True
    assert "survey-x-y" in (repo / backlog).read_text(encoding="utf-8")
    assert read_json(repo / manifest)["inventory"] == inventory
    assert json.loads((repo / manifest).read_text(encoding="utf-8"))["units"][0]["id"] == (
        "legacy/q1"
    )
