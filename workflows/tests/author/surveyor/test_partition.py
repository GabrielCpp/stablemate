"""`validate_partition` and `emit_artifacts` — the last two links in the surveyor's exhaustiveness chain."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from ostler import Ostler
from ostler.register import Record
from workhorse_workflows.author.surveyor.nodes import emit_artifacts, validate_partition

Write = Callable[[Path, str], Path]
WriteJson = Callable[[Path, Any], Path]
ReadJson = Callable[[Path], Any]

PARTITION = "docs/survey/partition.yaml"
INVENTORY = "docs/survey/inventory.json"
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


def _filed(repo: Path) -> list[Record]:
    return list(Ostler(repo).records().records)


def _subjects(artifacts: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(artifacts), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def _status(artifacts: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(artifacts), "status", "--porcelain", "--", ":!.gitignore"],
        capture_output=True, text=True, check=True,
    ).stdout


def _setup(
    write: Write,
    write_json: WriteJson,
    repo: Path,
    clusters: list[dict],
    units: list[dict],
) -> None:
    write(repo / PARTITION, yaml.safe_dump({"clusters": clusters}, sort_keys=False))
    write_json(repo / INVENTORY, {"version": 1, "units": units})




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
    """The whole reason this node exists: a unit with findings and no cluster would fall out of the generated backlog with nothing looking wrong."""
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
    assert "silently drop out of the filed records" in result.partition_errors


def test_clean_units_need_no_cluster(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """No findings, no remediation work — so a clean unit in a cluster is the error, not a clean unit outside one."""
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
    """Clusters partition the frozen list."""
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

    assert "must be a kebab-case slug (it names the cluster in the survey artifacts)" in errors
    assert "missing non-empty `title`" in errors
    assert "strategy 'vibes' not one of ['dedicated', 'mechanical']" in errors
    assert "`remediation_pattern` must be a kebab-case slug" in errors
    assert "must list at least one unit" in errors
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




def test_one_survey_record_per_cluster_is_filed_for_the_surveyed_repository(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
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
    filed = {r.summary: r for r in _filed(repo)}
    assert set(filed) == {
        "Remediate missing-error-handling",
        "Remediate datepicker-keyboard-model",
    }
    for record in filed.values():
        assert (record.repo, record.pattern, record.filed_by, record.status) == (
            "acme", record.pattern, "survey", "open",
        )
    mechanical = filed["Remediate missing-error-handling"]
    assert mechanical.pattern == "missing-error-handling"
    assert mechanical.area == "src"
    assert mechanical.id != "survey-missing-error-handling"
    assert "2 unit(s), mechanical checklist" in mechanical.body
    assert "`src/api`" in mechanical.body and "`src/web`" in mechanical.body
    assert "`missing-error-handling`" in mechanical.body
    assert "1 unit(s), dedicated" in filed["Remediate datepicker-keyboard-model"].body
    assert not (repo / "docs/backlog.md").exists()


def test_units_under_one_directory_give_that_directory_as_the_area(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    paths = ["src/lib/components/button.ts", "src/lib/components/card.ts"]
    _setup(write, write_json, repo, [_cluster("c", paths)], [_unit(p) for p in paths])

    emit_artifacts(logger)

    assert [r.area for r in _filed(repo)] == ["components"]


def test_units_in_unrelated_trees_give_the_general_area(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    paths = ["src/api/routes.ts", "tools/build/run.ts"]
    _setup(write, write_json, repo, [_cluster("c", paths)], [_unit(p) for p in paths])

    emit_artifacts(logger)

    assert [r.area for r in _filed(repo)] == ["general"]


def test_the_record_pattern_is_the_cluster_remediation_pattern(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    _setup(
        write, write_json, repo,
        [_cluster("c", ["src/a.ts"], remediation_pattern="missing-error-handling")],
        [_unit("src/a.ts")],
    )

    emit_artifacts(logger)

    assert [r.pattern for r in _filed(repo)] == ["missing-error-handling"]


def test_the_record_symbols_are_the_cluster_units(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    paths = ["src/a.ts", "src/b.ts"]
    _setup(write, write_json, repo, [_cluster("c", paths)], [_unit(p) for p in paths])

    emit_artifacts(logger)

    assert [list(r.symbols) for r in _filed(repo)] == [paths]


def test_every_record_of_one_emit_lands_in_one_artifacts_commit(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("first-fix", ["src/api"]), _cluster("second-fix", ["src/web"])],
        [_unit("src/api"), _unit("src/web")],
    )

    emit_artifacts(logger)

    assert _subjects(artifacts)[:2] == ["chore(acme): file 2 survey records", "init"]
    assert _status(artifacts) == ""


def test_cluster_notes_ride_along_in_the_record_body(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("x-y", ["src/api"], notes="do the api\nfirst")],
        [_unit("src/api")],
    )

    emit_artifacts(logger)

    (record,) = _filed(repo)
    assert "do the api first" in record.body


def test_a_rerun_with_unchanged_clusters_files_nothing_and_adds_no_commit(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    _setup(
        write,
        write_json,
        repo,
        [_cluster("first-fix", ["src/api"]), _cluster("second-fix", ["src/web"])],
        [_unit("src/api"), _unit("src/web")],
    )
    emit_artifacts(logger)
    before = (sorted(r.id for r in _filed(repo)), _subjects(artifacts))

    result = emit_artifacts(logger)

    assert result.emit_ok is True
    assert (sorted(r.id for r in _filed(repo)), _subjects(artifacts)) == before


def test_a_rerun_files_only_the_cluster_that_is_new(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    units = [_unit("src/api"), _unit("src/web")]
    _setup(write, write_json, repo, [_cluster("first-fix", ["src/api"])], units)
    emit_artifacts(logger)
    (first,) = _filed(repo)

    _setup(
        write,
        write_json,
        repo,
        [_cluster("first-fix", ["src/api"]), _cluster("second-fix", ["src/web"])],
        units,
    )
    emit_artifacts(logger)

    filed = _filed(repo)
    assert sorted(r.summary for r in filed) == ["Remediate first-fix", "Remediate second-fix"]
    assert first.id in {r.id for r in filed}
    assert _subjects(artifacts)[:3] == ["chore(acme): file 1 survey records"] * 2 + ["init"]


def test_a_rerun_leaves_alone_a_record_another_filer_holds(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    held = Ostler(repo).file_record(
        repo="acme", area="billing", pattern="extract-module",
        summary="Remediate first-fix", filed_by="coder",
    )
    assert held.ok, held
    _setup(write, write_json, repo, [_cluster("first-fix", ["src/api"])], [_unit("src/api")])

    emit_artifacts(logger)

    assert sorted(r.filed_by for r in _filed(repo)) == ["coder", "survey"]


def test_a_closed_record_does_not_hold_back_a_cluster_that_comes_back(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, artifacts: Path
) -> None:
    _setup(write, write_json, repo, [_cluster("first-fix", ["src/api"])], [_unit("src/api")])
    emit_artifacts(logger)
    (first,) = _filed(repo)
    assert Ostler(repo).close_record(first.id, "dropped", "not worth it").ok

    emit_artifacts(logger)

    assert sorted(r.status for r in _filed(repo)) == ["dropped", "open"]


def test_the_manifest_carries_every_unit_and_the_records_that_cover_it(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson,
    artifacts: Path,
) -> None:
    """Every unit, not just the clustered ones: the manifest is the frozen list with the traceability hop attached, and a unit with no work says so by carrying no records."""
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
    by_summary = {r.summary: r.id for r in _filed(repo)}
    handling, naming = by_summary["Remediate missing-error-handling"], by_summary["Remediate naming"]
    by_id = {u["id"]: u for u in manifest["units"]}
    assert set(by_id) == {"src/api", "src/web", "README.md"}
    assert by_id["src/api"]["bullets"] == [handling, naming]
    assert by_id["src/web"]["bullets"] == [handling]
    assert by_id["src/api"]["clusters"] == ["missing-error-handling", "naming"]
    assert by_id["README.md"]["bullets"] == []
    assert by_id["README.md"]["kind"] == "file"
    assert "3 unit(s)" in result.emit_note


def test_an_explicit_order_key_sequences_the_records_a_unit_names(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson,
    artifacts: Path,
) -> None:
    """Ordering hints are the partitioner's other job, and ids break ties so the emission is deterministic across runs."""
    _setup(
        write,
        write_json,
        repo,
        [
            _cluster("zebra", ["src/api"], order=2),
            _cluster("aardvark", ["src/api"], order=1),
        ],
        [_unit("src/api")],
    )

    emit_artifacts(logger)

    by_summary = {r.summary: r.id for r in _filed(repo)}
    unit = read_json(repo / MANIFEST)["units"][0]
    assert unit["bullets"] == [by_summary["Remediate aardvark"], by_summary["Remediate zebra"]]
    assert unit["clusters"] == ["aardvark", "zebra"]


def test_a_rerun_names_the_record_it_already_holds_in_the_manifest(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson,
    artifacts: Path,
) -> None:
    _setup(write, write_json, repo, [_cluster("first-fix", ["src/api"])], [_unit("src/api")])
    emit_artifacts(logger)
    (first,) = _filed(repo)

    emit_artifacts(logger)

    assert read_json(repo / MANIFEST)["units"][0]["bullets"] == [first.id]


def test_emission_refuses_when_the_partition_is_unreadable(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """`emit_artifacts` runs after the gate passed, so an unreadable partition here means the chain was skipped, so it says so rather than filing nothing quietly."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})

    result = emit_artifacts(logger)

    assert result.emit_ok is False
    assert "run the partition gate first" in result.emit_errors
    assert _filed(repo) == []


def test_emission_refuses_when_the_inventory_is_unreadable(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / PARTITION, yaml.safe_dump({"clusters": [_cluster("x-y", ["src/api"])]}))

    result = emit_artifacts(logger)

    assert result.emit_ok is False
    assert "could not be read" in result.emit_errors


def test_the_survey_directory_travels_with_the_parameters(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson, read_json: ReadJson,
    artifacts: Path,
) -> None:
    partition = "docs/survey/legacy-vs-new/partition.yaml"
    inventory = "docs/survey/legacy-vs-new/inventory.json"
    manifest = "docs/survey/legacy-vs-new/unit-manifest.json"
    write(repo / partition, yaml.safe_dump({"clusters": [_cluster("x-y", ["legacy/q1"])]}))
    write_json(repo / inventory, {"units": [_unit("legacy/q1")]})

    check = validate_partition(logger, partition=partition, inventory=inventory)
    result = emit_artifacts(
        logger,
        partition=partition,
        inventory=inventory,
        unit_manifest=manifest,
    )

    assert check.partition_ok is True
    assert result.emit_ok is True
    assert [(r.area, r.pattern) for r in _filed(repo)] == [("legacy", "x-y")]
    assert read_json(repo / manifest)["inventory"] == inventory
    assert json.loads((repo / manifest).read_text(encoding="utf-8"))["units"][0]["id"] == (
        "legacy/q1"
    )
