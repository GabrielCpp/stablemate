"""The parity survey's two ends: `load_parity_config`, the freeze, and the emitter.

Same shape as the surveyor's tests — real nodes against a real directory tree, with the
`repo` fixture standing the test in the consuming repo. `launch_repo_root()` falls back
to the working directory just as `survey_repo_root()` does, so that one fixture pins both.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.parity_surveyor.nodes.parity import (
    PARITY_BEGIN,
    PARITY_HEADING,
    emit_parity_backlog,
    expand_parity_inventory,
    load_parity_config,
    parity_slug,
)


def _entry(area: str = "billing", slug: str = "invoices", **over: Any) -> dict[str, Any]:
    """One baseline surface, as the legacy inventory records it."""
    return {"area": area, "slug": slug, "title": "Invoices", "route": "/invoices", **over}


def _record(status: str = "assessed", **over: Any) -> str:
    """A finding record's front matter. JSON is valid YAML, so no serializer is needed."""
    front: dict[str, Any] = {"status": status, **over}
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Parity finding\n"


# ── load_parity_config ──────────────────────────────────────────────────────


def test_config_derives_every_path_under_the_survey_dir(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "docs/legacy/inventory.json", "{}")
    (repo / "docs/features").mkdir(parents=True)

    cfg = load_parity_config(logger, baseline="docs/legacy/inventory.json")

    assert cfg.repo_root == str(repo)
    assert cfg.baseline_inventory == "docs/legacy/inventory.json"
    assert cfg.target_features == "docs/features"
    assert cfg.survey_dir == "docs/survey/legacy-vs-new"
    assert cfg.inventory == "docs/survey/legacy-vs-new/inventory.json"
    assert cfg.findings_dir == "docs/survey/legacy-vs-new/findings"
    assert cfg.unit_manifest == "docs/survey/legacy-vs-new/unit-manifest.json"
    assert cfg.backlog == "docs/backlog.md"
    assert cfg.epics_dir == "docs/epics"


def test_config_honours_an_overridden_survey_dir(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "base.json", "{}")
    (repo / "book").mkdir()

    cfg = load_parity_config(
        logger,
        baseline="base.json",
        target="book",
        survey_dir="docs/parity",
        backlog="TODO.md",
        epics="docs/work",
    )

    assert (cfg.target_features, cfg.backlog, cfg.epics_dir) == ("book", "TODO.md", "docs/work")
    assert cfg.inventory == "docs/parity/inventory.json"
    assert cfg.findings_dir == "docs/parity/findings"


def test_config_blank_overrides_fall_back_to_the_defaults(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """The script took `sys.argv[n] or <default>`, so an empty positional meant "default"."""
    write(repo / "base.json", "{}")
    (repo / "docs/features").mkdir(parents=True)

    cfg = load_parity_config(logger, baseline="base.json", target="", survey_dir="  ")

    assert cfg.target_features == "docs/features"
    assert cfg.survey_dir == "docs/survey/legacy-vs-new"


def test_config_fails_without_a_baseline_inventory(
    logger: logging.Logger, repo: Path
) -> None:
    """A parity survey with no baseline has nothing to be exhaustive about."""
    (repo / "docs/features").mkdir(parents=True)

    with pytest.raises(WorkflowFailed, match="baseline inventory not found: docs/legacy.json"):
        load_parity_config(logger, baseline="docs/legacy.json")


def test_config_names_an_empty_baseline_as_empty(logger: logging.Logger, repo: Path) -> None:
    (repo / "docs/features").mkdir(parents=True)

    with pytest.raises(WorkflowFailed, match=r"baseline inventory not found: \(empty\)"):
        load_parity_config(logger, baseline="")


def test_config_fails_without_a_target_feature_book(
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    """With no target book every legacy surface would be reported as missing."""
    write(repo / "base.json", "{}")

    with pytest.raises(WorkflowFailed, match="target feature book not found: docs/features"):
        load_parity_config(logger, baseline="base.json")


# ── expand_parity_inventory ─────────────────────────────────────────────────


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


# ── emit_parity_backlog ─────────────────────────────────────────────────────


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
    return emit_parity_backlog(
        logger,
        inventory="inv.json",
        findings_dir="findings",
        backlog="docs/backlog.md",
        unit_manifest="manifest.json",
    )


def test_emit_writes_one_bullet_per_uncovered_surface(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None]
) -> None:
    parity_survey(
        [_unit(), _unit(area="admin", slug="users")],
        {
            "legacy/billing/invoices": _record(
                findings=[{"description": "no invoice list in the new app"}]
            ),
            "legacy/admin/users": _record(findings=[{"description": "no user admin screen"}]),
        },
    )

    result = _emit(repo, logger)

    assert result.emit_ok
    assert result.bullet_count == 2
    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert "- [legacy-parity-billing-invoices] no invoice list in the new app" in body
    assert "- [legacy-parity-admin-users] no user admin screen" in body


def test_emit_suppresses_a_surface_a_new_feature_already_owns(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
) -> None:
    """The suppression is the assessor's one judgment, and it stays auditable: the unit is
    still in the manifest, with the owner that suppressed it."""
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
        "wrote 1 missing-surface bullet(s); suppressed 1 already-owned surface(s)"
    )
    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert "would have been a gap" not in body
    by_id = {u["id"]: u for u in read_json(repo / "manifest.json")["units"]}
    assert by_id["legacy/billing/invoices"] == {
        "id": "legacy/billing/invoices",
        "path": "docs/legacy/billing/invoices.md",
        "status": "assessed",
        "existingOwner": "FEAT-12 invoices",
        "bullet": "",
    }
    assert by_id["legacy/billing/refunds"]["bullet"] == "legacy-parity-billing-refunds"


def test_emit_skips_a_unit_that_is_not_assessed(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
) -> None:
    """`clean` means the new app covers it; `blocked` means nobody could tell yet. Neither
    is a backlog bullet, and neither counts as a suppression."""
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
        "wrote 0 missing-surface bullet(s); suppressed 0 already-owned surface(s)"
    )
    statuses = {u["id"]: u["status"] for u in read_json(repo / "manifest.json")["units"]}
    assert statuses == {"legacy/billing/invoices": "clean", "legacy/billing/statements": "blocked"}


def test_emit_flattens_a_multiline_description_to_one_bullet(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None]
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

    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert "- [legacy-parity-billing-invoices] no invoice list and no export\n" in body


def test_emit_uses_only_the_first_finding(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None]
) -> None:
    """One surface, one gap: the bullet is the surface being missing, not each detail."""
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
    assert "second" not in (repo / "docs/backlog.md").read_text(encoding="utf-8")


def test_emit_tolerates_an_assessed_record_with_no_findings(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None]
) -> None:
    """`validate_record` already rejects this; the emitter still must not crash on it."""
    parity_survey([_unit()], {"legacy/billing/invoices": _record()})

    result = _emit(repo, logger)

    assert result.bullet_count == 1
    assert "- [legacy-parity-billing-invoices] \n" in (
        repo / "docs/backlog.md"
    ).read_text(encoding="utf-8")


def test_emit_creates_a_backlog_when_none_exists(
    logger: logging.Logger, repo: Path, parity_survey: Callable[..., None]
) -> None:
    parity_survey(
        [_unit()], {"legacy/billing/invoices": _record(findings=[{"description": "gap"}])}
    )

    _emit(repo, logger)

    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert body.startswith(f"# Backlog\n\n{PARITY_HEADING}\n\n{PARITY_BEGIN}\n")


def test_emit_appends_its_own_heading_to_an_existing_backlog(
    logger: logging.Logger,
    repo: Path,
    write: Callable[[Path, str], Path],
    parity_survey: Callable[..., None],
) -> None:
    """A repo can carry both surveys' sections: the parity fence is its own marker pair,
    so an existing surveyor section is neither replaced nor read."""
    parity_survey(
        [_unit()], {"legacy/billing/invoices": _record(findings=[{"description": "gap"}])}
    )
    write(
        repo / "docs/backlog.md",
        "# Backlog\n\n## Survey findings\n\n"
        "<!-- surveyor:begin — generated; do not edit inside this fence -->\n"
        "- [survey-a11y-labels] label the icon buttons\n"
        "<!-- surveyor:end -->\n",
    )

    _emit(repo, logger)

    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert "- [survey-a11y-labels] label the icon buttons" in body
    assert "<!-- surveyor:end -->" in body
    assert body.index("## Survey findings") < body.index(PARITY_HEADING)


def test_re_emitting_replaces_only_the_parity_fence(
    logger: logging.Logger,
    repo: Path,
    write: Callable[[Path, str], Path],
    write_json: Callable[[Path, Any], Path],
    parity_survey: Callable[..., None],
) -> None:
    parity_survey(
        [_unit()], {"legacy/billing/invoices": _record(findings=[{"description": "first pass"}])}
    )
    _emit(repo, logger)
    write(
        repo / "docs/backlog.md",
        (repo / "docs/backlog.md").read_text(encoding="utf-8")
        + "\n## Filed by hand\n\n- [manual-1] something an operator wrote\n",
    )
    write(
        repo / "findings/legacy-billing-invoices.md",
        _record(findings=[{"description": "second pass"}]),
    )

    _emit(repo, logger)

    body = (repo / "docs/backlog.md").read_text(encoding="utf-8")
    assert body.count(PARITY_BEGIN) == 1
    assert body.count(PARITY_HEADING) == 1
    assert "second pass" in body
    assert "first pass" not in body
    assert "- [manual-1] something an operator wrote" in body


def test_emit_manifest_carries_the_baseline_and_every_unit(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
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
    logger: logging.Logger, repo: Path, write: Callable[[Path, str], Path]
) -> None:
    write(repo / "inv.json", "{ not json")

    result = _emit(repo, logger)

    assert not result.emit_ok
    assert result.emit_errors
    assert not (repo / "docs/backlog.md").exists()
    assert not (repo / "manifest.json").exists()


def test_emit_raises_on_a_missing_finding_record(
    logger: logging.Logger, repo: Path, write_json: Callable[[Path, Any], Path]
) -> None:
    """A FINDING, kept literal from the script: the record read is unguarded, so a unit
    with no record crashes the node instead of being reported as incomplete coverage.
    `verify_records` runs before this and catches it — but only if the flow ordered them
    that way. Recorded for the deletion loop rather than fixed here, because guarding it
    would change behavior the YAML engine still exhibits."""
    write_json(repo / "inv.json", {"version": 1, "units": [_unit()]})

    with pytest.raises(OSError):
        _emit(repo, logger)


def test_emit_treats_a_record_with_no_front_matter_as_no_status(
    logger: logging.Logger,
    repo: Path,
    parity_survey: Callable[..., None],
    read_json: Callable[[Path], Any],
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
) -> None:
    """Nothing is hardcoded: the config node derives these, and the node just uses them."""
    write_json(repo / "elsewhere/inv.json", {"version": 1, "units": [_unit()]})
    write(
        repo / "elsewhere/f/legacy-billing-invoices.md",
        _record(findings=[{"description": "gap"}]),
    )

    result = emit_parity_backlog(
        logger,
        inventory="elsewhere/inv.json",
        findings_dir="elsewhere/f",
        backlog="TODO.md",
        unit_manifest="elsewhere/manifest.json",
    )

    assert result.emit_ok
    assert "- [legacy-parity-billing-invoices] gap" in (repo / "TODO.md").read_text(
        encoding="utf-8"
    )
    assert (repo / "elsewhere/manifest.json").is_file()
