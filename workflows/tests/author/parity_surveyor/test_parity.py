"""The parity survey's two ends: `load_parity_config`, the freeze, and the emitter."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from ostler import Ostler
from ostler.register import Record
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.parity_surveyor.nodes.parity import (
    emit_parity_records,
    expand_parity_inventory,
    load_parity_config,
    parity_slug,
)
from _epics import epics_root


def _entry(area: str = "billing", slug: str = "invoices", **over: Any) -> dict[str, Any]:
    """One baseline surface, as the legacy inventory records it."""
    return {"area": area, "slug": slug, "title": "Invoices", "route": "/invoices", **over}


def _record(status: str = "assessed", **over: Any) -> str:
    """A finding record's front matter."""
    front: dict[str, Any] = {"status": status, **over}
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Parity finding\n"




def test_config_derives_every_path_under_the_survey_dir(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "docs/legacy/inventory.json", "{}")
    (repo / "docs/services").mkdir(parents=True)

    cfg = load_parity_config(logger, baseline="docs/legacy/inventory.json")

    assert cfg.repo_root == str(repo)
    assert cfg.baseline_inventory == "docs/legacy/inventory.json"
    assert cfg.target_services == "docs/services"
    assert cfg.survey_dir == "docs/survey/legacy-vs-new"
    assert cfg.inventory == "docs/survey/legacy-vs-new/inventory.json"
    assert cfg.findings_dir == "docs/survey/legacy-vs-new/findings"
    assert cfg.unit_manifest == "docs/survey/legacy-vs-new/unit-manifest.json"
    assert cfg.epics_dir == str(epics_root())


def test_config_honours_an_overridden_survey_dir(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "base.json", "{}")
    (repo / "docs/services").mkdir(parents=True)

    cfg = load_parity_config(
        logger,
        baseline="base.json",
        survey_dir="docs/parity",
    )

    assert (cfg.target_services, cfg.epics_dir) == ("docs/services", str(epics_root()))
    assert cfg.inventory == "docs/parity/inventory.json"
    assert cfg.findings_dir == "docs/parity/findings"


def test_config_blank_overrides_fall_back_to_the_defaults(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """The script took `sys.argv[n] or <default>`, so an empty positional meant "default"."""
    write(repo / "base.json", "{}")
    (repo / "docs/services").mkdir(parents=True)

    cfg = load_parity_config(logger, baseline="base.json", survey_dir="  ")

    assert cfg.target_services == "docs/services"
    assert cfg.survey_dir == "docs/survey/legacy-vs-new"


def test_config_fails_without_a_baseline_inventory(
    logger: logging.Logger, repo: Path
) -> None:
    """A parity survey with no baseline has nothing to be exhaustive about."""
    (repo / "docs/services").mkdir(parents=True)

    with pytest.raises(WorkflowFailed, match="baseline inventory not found: docs/legacy.json"):
        load_parity_config(logger, baseline="docs/legacy.json")


def test_config_names_an_empty_baseline_as_empty(logger: logging.Logger, repo: Path) -> None:
    (repo / "docs/services").mkdir(parents=True)

    with pytest.raises(WorkflowFailed, match=r"baseline inventory not found: \(empty\)"):
        load_parity_config(logger, baseline="")


def test_config_fails_without_a_target_feature_book(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """With no target book every legacy surface would be reported as missing."""
    write(repo / "base.json", "{}")

    with pytest.raises(WorkflowFailed, match="target feature book not found: docs/services"):
        load_parity_config(logger, baseline="base.json")




def test_expand_freezes_one_unit_per_baseline_surface(
    logger: logging.Logger,
    repo: Path,
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
) -> None:
    write_json(
        repo / "docs/legacy/inventory.json",
        {"entries": [_entry(), _entry(area="admin", slug="users", title="Users")]},
    )

    result = expand_parity_inventory(
        logger, baseline="docs/legacy/inventory.json", inventory="docs/parity/inventory.json"
    )

    assert result.expand_ok
    assert result.unit_count == 2
    assert result.inventory_note == "froze 2 baseline surfaces"
    frozen = read_json(repo / "docs/parity/inventory.json")
    assert frozen["version"] == 1
    assert frozen["baseline"] == "docs/legacy/inventory.json"
    assert frozen["units"][0] == {
        "id": "legacy/billing/invoices",
        "path": "docs/legacy/billing/invoices.md",
        "kind": "legacy-surface",
        "status": "pending",
        "area": "billing",
        "slug": "invoices",
        "title": "Invoices",
        "route": "/invoices",
    }
    assert frozen["units"][1]["id"] == "legacy/admin/users"


def test_expand_skips_surfaces_the_rewrite_already_owns(
    logger: logging.Logger,
    repo: Path,
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
) -> None:
    """`rewriteSurface: true` is out of scope by construction — only the literal True."""
    write_json(
        repo / "base.json",
        {
            "entries": [
                _entry(),
                _entry(slug="statements", rewriteSurface=True),
                _entry(slug="refunds", rewriteSurface=False),
                "not a mapping",
            ]
        },
    )

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert result.unit_count == 2
    ids = [u["id"] for u in read_json(repo / "inv.json")["units"]]
    assert ids == ["legacy/billing/invoices", "legacy/billing/refunds"]


def test_expand_defaults_the_title_to_the_slug(
    logger: logging.Logger,
    repo: Path,
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
) -> None:
    write_json(repo / "base.json", {"entries": [{"area": "admin", "slug": "users"}]})

    expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    unit = read_json(repo / "inv.json")["units"][0]
    assert (unit["title"], unit["route"]) == ("users", "")


def test_expand_consumes_an_already_frozen_inventory_verbatim(
    logger: logging.Logger,
    repo: Path,
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
) -> None:
    """The freeze is the coverage baseline: a resume re-deriving it would break the claim."""
    write_json(repo / "base.json", {"entries": [_entry(), _entry(slug="refunds")]})
    write_json(repo / "inv.json", {"version": 1, "units": [{"id": "legacy/kept/one"}]})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert result.expand_ok
    assert result.unit_count == 1
    assert result.inventory_note == "inventory frozen at inv.json"
    assert [u["id"] for u in read_json(repo / "inv.json")["units"]] == ["legacy/kept/one"]


def test_expand_reports_an_unreadable_frozen_inventory(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "inv.json", "{ not json")

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert result.expand_errors.startswith("frozen inventory is invalid:")


def test_expand_reports_a_frozen_inventory_with_no_units_key(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    write_json(repo / "inv.json", {"version": 1})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert "frozen inventory is invalid" in result.expand_errors


def test_expand_reports_a_missing_baseline(logger: logging.Logger, repo: Path) -> None:
    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert result.expand_errors.startswith("baseline inventory is invalid:")
    assert not (repo / "inv.json").exists()


def test_expand_reports_a_baseline_whose_entries_are_not_a_list(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    write_json(repo / "base.json", {"entries": {"billing": "invoices"}})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert "entries is not a list" in result.expand_errors


def test_expand_refuses_an_entry_with_no_area_or_slug(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    """A unit id built from a blank field would collide with every other blank one."""
    write_json(repo / "base.json", {"entries": [_entry(), _entry(slug="  ")]})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert result.expand_errors == "every baseline entry must have non-empty area and slug"
    assert not (repo / "inv.json").exists()


def test_expand_refuses_a_duplicate_surface(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    write_json(repo / "base.json", {"entries": [_entry(), _entry(title="Invoices again")]})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert result.expand_errors == "duplicate baseline surface: legacy/billing/invoices"
    assert not (repo / "inv.json").exists()


def test_expand_refuses_a_baseline_that_is_entirely_rewritten(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    """Zero units is not a survey of zero size, it is a survey with nothing to prove."""
    write_json(repo / "base.json", {"entries": [_entry(rewriteSurface=True)]})

    result = expand_parity_inventory(logger, baseline="base.json", inventory="inv.json")

    assert not result.expand_ok
    assert result.expand_errors == "baseline inventory contains no non-rewrite surfaces"
    assert not (repo / "inv.json").exists()




@pytest.fixture
def parity_survey(
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
) -> Callable[..., None]:
    """Freeze a unit list and lay down one finding record per unit."""

    def _setup(units: list[dict[str, Any]], records: dict[str, str]) -> None:
        write_json(repo / "inv.json", {"version": 1, "baseline": "base.json", "units": units})
        for uid, text in records.items():
            write(repo / "findings" / f"{parity_slug(uid)}.md", text)

    return _setup


def _unit(area: str = "billing", slug: str = "invoices") -> dict[str, Any]:
    return {
        "id": f"legacy/{area}/{slug}",
        "path": f"docs/legacy/{area}/{slug}.md",
        "kind": "legacy-surface",
        "status": "assessed",
        "area": area,
        "slug": slug,
    }


def _emit(repo: Path, logger: logging.Logger) -> Any:
    return emit_parity_records(
        logger,
        inventory="inv.json",
        findings_dir="findings",
        unit_manifest="manifest.json",
    )


def _filed(repo: Path) -> list[Record]:
    return list(Ostler(repo).records().records)


def _subjects(artifacts: Path) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(artifacts), "log", "--format=%s"], capture_output=True, text=True, check=True
    ).stdout.splitlines()


def test_emit_files_one_parity_record_per_uncovered_surface(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit(), _unit(area="admin", slug="users")],
        {
            "legacy/billing/invoices": _record(
                findings=[{
                    "description": "no invoice list in the new app",
                    "effort": "small",
                    "evidence": ["invoices.php:12", "graph search found no invoice screen"],
                }]
            ),
            "legacy/admin/users": _record(findings=[{"description": "no user admin screen"}]),
        },
    )

    result = _emit(repo, logger)

    assert result.emit_ok
    assert result.bullet_count == 2
    filed = {r.summary: r for r in _filed(repo)}
    assert set(filed) == {"no invoice list in the new app", "no user admin screen"}
    invoices = filed["no invoice list in the new app"]
    assert (invoices.repo, invoices.area, invoices.pattern) == ("acme", "billing", "untriaged")
    assert (invoices.filed_by, invoices.status) == ("parity", "open")
    assert invoices.id != "legacy-parity-billing-invoices"
    assert "`legacy/billing/invoices`" in invoices.body
    assert "invoices.php:12" in invoices.body and "graph search found no invoice screen" in invoices.body
    assert filed["no user admin screen"].area == "admin"
    assert not (repo / "docs/backlog.md").exists()


def test_emit_commits_every_record_of_one_emit_in_one_artifacts_commit(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit(), _unit(slug="refunds")],
        {
            "legacy/billing/invoices": _record(findings=[{"description": "no invoice list"}]),
            "legacy/billing/refunds": _record(findings=[{"description": "no refund flow"}]),
        },
    )

    _emit(repo, logger)

    assert _subjects(artifacts) == ["init"]


def test_emit_suppresses_a_surface_a_new_feature_already_owns(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
    artifacts: Path,
) -> None:
    """The suppression is the assessor's one judgment, and it stays auditable: the unit is still in the manifest, with the owner that suppressed it."""
    parity_survey(
        [_unit(), _unit(slug="refunds")],
        {
            "legacy/billing/invoices": _record(
                existing_owner="FEAT-12 invoices",
                findings=[{"description": "would have been a gap"}],
            ),
            "legacy/billing/refunds": _record(findings=[{"description": "no refund flow"}]),
        },
    )

    result = _emit(repo, logger)

    assert result.bullet_count == 1
    assert result.emit_note == (
        "filed 1 missing-surface record(s); suppressed 1 already-owned surface(s)"
    )
    (refunds,) = _filed(repo)
    assert refunds.summary == "no refund flow"
    by_id = {u["id"]: u for u in read_json(repo / "manifest.json")["units"]}
    assert by_id["legacy/billing/invoices"] == {
        "id": "legacy/billing/invoices",
        "path": "docs/legacy/billing/invoices.md",
        "status": "assessed",
        "existingOwner": "FEAT-12 invoices",
        "bullet": "",
    }
    assert by_id["legacy/billing/refunds"]["bullet"] == refunds.id


def test_a_surface_with_an_existing_owner_files_nothing_and_commits_nothing(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit()],
        {
            "legacy/billing/invoices": _record(
                existing_owner="FEAT-12", findings=[{"description": "would have been a gap"}]
            )
        },
    )

    result = _emit(repo, logger)

    assert result.emit_ok and result.bullet_count == 0
    assert _filed(repo) == []
    assert _subjects(artifacts) == ["init"]


def test_emit_skips_a_unit_that_is_not_assessed(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
    artifacts: Path,
) -> None:
    """`clean` means the new app covers it; `blocked` means nobody could tell yet."""
    parity_survey(
        [_unit(), _unit(slug="statements")],
        {
            "legacy/billing/invoices": _record("clean"),
            "legacy/billing/statements": _record("blocked", gap="no legacy access"),
        },
    )

    result = _emit(repo, logger)

    assert result.bullet_count == 0
    assert result.emit_note == (
        "filed 0 missing-surface record(s); suppressed 0 already-owned surface(s)"
    )
    assert _filed(repo) == []
    statuses = {u["id"]: u["status"] for u in read_json(repo / "manifest.json")["units"]}
    assert statuses == {"legacy/billing/invoices": "clean", "legacy/billing/statements": "blocked"}


def test_emit_flattens_a_multiline_description_to_a_one_line_summary(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit()],
        {
            "legacy/billing/invoices": _record(
                findings=[{"description": "no invoice list\n  and no export\n"}]
            )
        },
    )

    _emit(repo, logger)

    (record,) = _filed(repo)
    assert record.summary == "no invoice list and no export"


def test_emit_uses_only_the_first_finding(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    """One surface, one gap: the record is the surface being missing, not each detail."""
    parity_survey(
        [_unit()],
        {
            "legacy/billing/invoices": _record(
                findings=[{"description": "first"}, {"description": "second"}]
            )
        },
    )

    result = _emit(repo, logger)

    assert result.bullet_count == 1
    (record,) = _filed(repo)
    assert record.summary == "first"
    assert "second" not in record.body


def test_emit_tolerates_an_assessed_record_with_no_findings(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    """`validate_record` already rejects this; the emitter still must not crash on it."""
    parity_survey([_unit()], {"legacy/billing/invoices": _record()})

    result = _emit(repo, logger)

    assert result.bullet_count == 1
    (record,) = _filed(repo)
    assert "legacy/billing/invoices" in record.summary


def test_emit_takes_the_area_as_one_lowercase_kebab_segment(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit(area="Billing & Co")],
        {"legacy/Billing & Co/invoices": _record(findings=[{"description": "gap"}])},
    )

    _emit(repo, logger)

    (record,) = _filed(repo)
    assert record.area == "billing-co"


def test_a_rerun_with_unchanged_findings_files_nothing_and_adds_no_commit(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    parity_survey(
        [_unit(), _unit(slug="refunds")],
        {
            "legacy/billing/invoices": _record(findings=[{"description": "no invoice list"}]),
            "legacy/billing/refunds": _record(findings=[{"description": "no refund flow"}]),
        },
    )
    _emit(repo, logger)
    before = (sorted(r.id for r in _filed(repo)), _subjects(artifacts))

    result = _emit(repo, logger)

    assert result.emit_ok
    assert (sorted(r.id for r in _filed(repo)), _subjects(artifacts)) == before


def test_a_rerun_files_only_the_surface_that_is_new(
    logger: logging.Logger,
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
    read_json: Callable[[Path], Any],
    artifacts: Path,
) -> None:
    write_json(repo / "inv.json", {"version": 1, "baseline": "base.json", "units": [_unit()]})
    write(repo / "findings/legacy-billing-invoices.md", _record(findings=[{"description": "no invoice list"}]))
    _emit(repo, logger)
    (first,) = _filed(repo)

    write_json(
        repo / "inv.json", {"version": 1, "baseline": "base.json", "units": [_unit(), _unit(slug="refunds")]}
    )
    write(repo / "findings/legacy-billing-refunds.md", _record(findings=[{"description": "no refund flow"}]))
    _emit(repo, logger)

    filed = {r.summary: r.id for r in _filed(repo)}
    assert set(filed) == {"no invoice list", "no refund flow"}
    assert filed["no invoice list"] == first.id
    by_id = {u["id"]: u["bullet"] for u in read_json(repo / "manifest.json")["units"]}
    assert by_id == {
        "legacy/billing/invoices": first.id,
        "legacy/billing/refunds": filed["no refund flow"],
    }
    assert _subjects(artifacts) == ["init"]


def test_a_survey_record_with_the_same_summary_does_not_hold_back_a_parity_record(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None], artifacts: Path
) -> None:
    held = Ostler(repo).file_record(
        repo="acme", area="billing", pattern="untriaged", summary="no invoice list", filed_by="survey",
    )
    assert held.ok, held
    parity_survey([_unit()], {"legacy/billing/invoices": _record(findings=[{"description": "no invoice list"}])})

    _emit(repo, logger)

    assert sorted(r.filed_by for r in _filed(repo)) == ["parity", "survey"]


def test_emit_manifest_carries_the_baseline_and_every_unit(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
    artifacts: Path,
) -> None:
    parity_survey(
        [_unit(), _unit(slug="refunds")],
        {
            "legacy/billing/invoices": _record(findings=[{"description": "gap"}]),
            "legacy/billing/refunds": _record("clean"),
        },
    )

    _emit(repo, logger)

    manifest = read_json(repo / "manifest.json")
    assert manifest["version"] == 1
    assert manifest["generatedBy"] == "parity-surveyor"
    assert manifest["baseline"] == "base.json"
    assert [u["id"] for u in manifest["units"]] == [
        "legacy/billing/invoices",
        "legacy/billing/refunds",
    ]


def test_emit_reports_an_unreadable_inventory_without_writing_anything(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path], artifacts: Path
) -> None:
    write(repo / "inv.json", "{ not json")

    result = _emit(repo, logger)

    assert not result.emit_ok
    assert result.emit_errors
    assert _filed(repo) == []
    assert not (repo / "manifest.json").exists()


def test_emit_raises_on_a_missing_finding_record(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    """A FINDING, kept literal from the script: the record read is unguarded, so a unit with no record crashes the node instead of being reported as incomplete coverage."""
    write_json(repo / "inv.json", {"version": 1, "units": [_unit()]})

    with pytest.raises(OSError):
        _emit(repo, logger)


def test_emit_treats_a_record_with_no_front_matter_as_no_status(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
    artifacts: Path,
) -> None:
    parity_survey([_unit()], {"legacy/billing/invoices": "# Just a heading\n"})

    result = _emit(repo, logger)

    assert result.bullet_count == 0
    assert read_json(repo / "manifest.json")["units"][0]["status"] == ""


def test_emit_paths_all_travel_with_parameters(
    logger: logging.Logger,
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
    artifacts: Path,
) -> None:
    """Nothing is hardcoded: the config node derives these, and the node just uses them."""
    write_json(repo / "elsewhere/inv.json", {"version": 1, "units": [_unit()]})
    write(
        repo / "elsewhere/f/legacy-billing-invoices.md",
        _record(findings=[{"description": "gap"}]),
    )

    result = emit_parity_records(
        logger,
        inventory="elsewhere/inv.json",
        findings_dir="elsewhere/f",
        unit_manifest="elsewhere/manifest.json",
    )

    assert result.emit_ok
    assert [r.summary for r in _filed(repo)] == ["gap"]
    assert (repo / "elsewhere/manifest.json").is_file()
