"""`validate_record` and `verify_records` — the two gates that let everything downstream
trust the finding records.

`validate_record` is the per-unit gate: deterministic, no judgment call, and it is what
decides whether the bounded fix loop runs again. `verify_records` is the coverage gate,
and these tests are about the claim it makes rather than its plumbing — every frozen unit
accounted for, no contradiction between an inventory status and its record, a blocked unit
still an open gap until someone owns it, and no unit quietly gone from the frozen list
since the last commit.

Ported from `surveyor/scripts/{validate-record,verify-records}.py`. Both scripts carried a
copy of the same ruleset with different wording, and the port keeps both, so the wording is
part of what these tests pin.
"""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse_workflows.author.shared.survey import validate_record, verify_records

Write = Callable[[Path, str], Path]
WriteJson = Callable[[Path, Any], Path]

INVENTORY = "docs/survey/inventory.json"
FINDINGS = "docs/survey/findings"


def _finding(**over: Any) -> dict:
    finding = {
        "description": "the handler swallows the error",
        "remediation_pattern": "surface-handler-errors",
        "effort": "small",
        "evidence": "src/api/handler.py:42 returns 200 on a failed write",
    }
    finding.update(over)
    return finding


def _record(unit_id: str, status: str, **over: Any) -> str:
    front: dict[str, Any] = {"type": "survey-finding", "unit": unit_id, "status": status}
    if status == "assessed":
        front["findings"] = [_finding()]
    if status == "blocked":
        front["openGaps"] = ["no local reproduction of the failing request"]
    front.update(over)
    # A JSON object is valid YAML, which keeps these fixtures from needing a serializer.
    return f"---\n{json.dumps(front, indent=2)}\n---\n\n# Survey finding: {unit_id}\n"


def _unit(unit_id: str, status: str = "pending", **over: Any) -> dict:
    unit = {"id": unit_id, "path": unit_id, "kind": "folder", "status": status}
    unit.update(over)
    return unit


def _commit(repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=repo, check=True)


# ------------------------------------------------------------------ validate_record


def test_a_complete_assessed_record_validates(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", _record("src/api", "assessed"))

    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert result.record_ok is True
    assert result.record_errors == ""


def test_a_clean_record_needs_no_findings(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", _record("src/api", "clean"))

    assert validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_ok is True


def test_a_record_for_another_unit_is_rejected(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """The single most damaging way a record can be wrong: coverage would be claimed for a
    unit nobody looked at."""
    write(repo / FINDINGS / "src-api.md", _record("src/web", "assessed"))

    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert result.record_ok is False
    assert "must describe its own inventory unit" in result.record_errors


def test_a_missing_record_is_reported_not_raised(
    repo: Path, logger: logging.Logger
) -> None:
    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert result.record_ok is False
    assert "the assessor must write it" in result.record_errors


def test_a_record_with_no_front_matter_cannot_be_parsed(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", "# Survey finding\n\nlooks fine to me\n")

    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert result.record_ok is False
    assert "no leading `---` YAML front-matter block" in result.record_errors


def test_an_unclosed_front_matter_fence_is_named_as_such(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", "---\ntype: survey-finding\nunit: src/api\n")

    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert "not closed by a second `---` fence" in result.record_errors


def test_front_matter_that_is_not_a_mapping_is_rejected(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", "---\n- one\n- two\n---\n")

    result = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api")

    assert "front-matter must be a mapping" in result.record_errors


def test_every_structural_error_in_a_finding_is_reported_together(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """One rework turn, every problem — the fix loop is bounded, so a gate that reported
    one error at a time would burn the budget on plumbing."""
    write(
        repo / FINDINGS / "src-api.md",
        _record(
            "src/api",
            "assessed",
            findings=[
                _finding(
                    description="  ",
                    remediation_pattern="Not A Slug",
                    effort="enormous",
                    evidence="",
                )
            ],
        ),
    )

    errors = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors

    assert "findings[0] missing non-empty `description`" in errors
    assert "must be a kebab-case slug (the partitioner clusters on it)" in errors
    assert "findings[0] effort 'enormous' not one of" in errors
    assert "is a guess, not a finding" in errors


def test_assessed_with_no_findings_is_a_contradiction(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", _record("src/api", "assessed", findings=[]))

    errors = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors

    assert "use `clean` when there is genuinely nothing to do" in errors


def test_clean_with_findings_is_the_other_contradiction(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / FINDINGS / "src-api.md", _record("src/api", "clean", findings=[_finding()]))

    errors = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors

    assert "a clean unit with findings is a contradiction; use `assessed`" in errors


def test_a_blocked_record_must_name_its_gap(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """`blocked` is never a bare shrug: the operator gate reads `openGaps`, so an empty one
    is the same as no answer."""
    write(repo / FINDINGS / "src-api.md", _record("src/api", "blocked", openGaps=[]))

    errors = validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors

    assert "record WHY the unit cannot be assessed" in errors


def test_a_disposition_is_only_accepted_and_only_on_blocked(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(
        repo / FINDINGS / "src-api.md",
        _record("src/api", "blocked", disposition="waived"),
    )
    assert (
        "the only recognized value is"
        in validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors
    )

    write(
        repo / FINDINGS / "src-api.md",
        _record("src/api", "clean", disposition="accepted"),
    )
    assert (
        "only makes sense on a `blocked` record"
        in validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_errors
    )


def test_an_accepted_disposition_on_a_blocked_record_validates(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    """The one sanctioned way a blocked unit stops being an open gap."""
    write(
        repo / FINDINGS / "src-api.md",
        _record("src/api", "blocked", disposition="accepted"),
    )

    assert validate_record(logger, f"{FINDINGS}/src-api.md", "src/api").record_ok is True


def test_validation_needs_both_of_its_arguments(
    repo: Path, logger: logging.Logger
) -> None:
    result = validate_record(logger, "", "src/api")

    assert result.record_ok is False
    assert "both required" in result.record_errors


# ------------------------------------------------------------------- verify_records


def test_a_fully_covered_survey_holds(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(
        repo / INVENTORY,
        {"units": [_unit("src/api", "assessed"), _unit("src/web", "clean")]},
    )
    write(repo / FINDINGS / "src-api.md", _record("src/api", "assessed"))
    write(repo / FINDINGS / "src-web.md", _record("src/web", "clean"))

    result = verify_records(logger)

    assert result.holds is True
    assert result.nothing_surveyed is False
    assert result.verify_errors == ""
    assert result.verify_report == (
        "survey coverage: 2 unit(s) — 1 assessed, 1 clean, 0 blocked, 0 pending; "
        "0 problem(s)"
    )


def test_no_inventory_means_nothing_was_surveyed(
    repo: Path, logger: logging.Logger
) -> None:
    """The script's third `verify_ok` value. It lets the flow through like `yes` does, but
    it is not the same claim, so the port keeps it as its own field."""
    result = verify_records(logger)

    assert result.holds is True
    assert result.nothing_surveyed is True
    assert "nothing was surveyed" in result.verify_report


def test_an_unreadable_inventory_does_not_hold(
    repo: Path, logger: logging.Logger, write: Write
) -> None:
    write(repo / INVENTORY, '{"units": "all of them"}\n')

    result = verify_records(logger)

    assert result.holds is False
    assert "not parseable JSON with a `units` list" in result.verify_errors
    assert result.verify_report == "inventory unreadable"


def test_a_pending_unit_is_never_waved_through(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    """The gate exists for exactly this: a unit re-pended by an operator (or never picked
    up) must send the loop back around instead of passing as covered."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api")]})

    result = verify_records(logger)

    assert result.holds is False
    assert result.verify_errors.startswith("the survey's coverage claim does not hold yet:")
    assert "[pending] 'src/api'" in result.verify_errors
    assert "0 assessed, 0 clean, 0 blocked, 1 pending; 1 problem(s)" in result.verify_report


def test_a_done_unit_with_no_record_is_a_gap(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "assessed")]})

    result = verify_records(logger)

    assert "[missing-record] 'src/api'" in result.verify_errors
    assert f"{FINDINGS}/src-api.md" in result.verify_errors


def test_an_invalid_record_is_reported_with_the_compact_wording(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """`verify_records` carries its own copy of the ruleset, worded for one line of an
    operator's report rather than for the assessor being asked to fix it. Two wordings is
    the ported behavior, not an accident to deduplicate."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "assessed")]})
    write(
        repo / FINDINGS / "src-api.md",
        _record("src/api", "assessed", findings=[_finding(evidence="")]),
    )

    errors = verify_records(logger).verify_errors

    assert "[invalid-record] 'src/api': findings[0] missing `evidence`" in errors
    # The strict wording belongs to `validate_record`, and stays there.
    assert "is a guess, not a finding" not in errors


def test_a_malformed_record_is_reported_with_the_parse_error(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "clean")]})
    write(repo / FINDINGS / "src-api.md", "nothing structured here\n")

    errors = verify_records(logger).verify_errors

    assert "[invalid-record] 'src/api': record has no leading `---`" in errors


def test_an_inventory_status_and_its_record_must_agree(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """One claim, two files. Divergence here is how a blocked unit would launder itself
    into the coverage count."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "clean")]})
    write(repo / FINDINGS / "src-api.md", _record("src/api", "assessed"))

    errors = verify_records(logger).verify_errors

    assert "[status-mismatch] 'src/api'" in errors
    assert "one claim, two files, they must agree" in errors


def test_a_blocked_unit_stays_an_open_gap_until_someone_owns_it(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "blocked")]})
    write(repo / FINDINGS / "src-api.md", _record("src/api", "blocked"))

    result = verify_records(logger)

    assert result.holds is False
    assert "[blocked] 'src/api' is an OPEN gap" in result.verify_errors
    assert "no local reproduction of the failing request" in result.verify_errors


def test_an_accepted_disposition_closes_the_blocked_gap(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """A blocked unit does not block the survey forever — but only a recorded, reasoned
    acceptance clears it, and the report still counts it as blocked."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "blocked")]})
    write(
        repo / FINDINGS / "src-api.md",
        _record("src/api", "blocked", disposition="accepted"),
    )

    result = verify_records(logger)

    assert result.holds is True
    assert "0 assessed, 0 clean, 1 blocked, 0 pending" in result.verify_report


def test_a_status_outside_the_unit_vocabulary_is_reported(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "probably-fine")]})

    assert "[bad-status] 'src/api' has status 'probably-fine'" in (
        verify_records(logger).verify_errors
    )


def test_an_entry_with_no_id_is_reported(
    repo: Path, logger: logging.Logger, write_json: WriteJson
) -> None:
    write_json(repo / INVENTORY, {"units": [{"path": "src/api", "status": "clean"}]})

    assert "[malformed-unit]" in verify_records(logger).verify_errors


def test_a_unit_dropped_since_the_commit_is_a_regression(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """The reconcile-shaped check. Shrinking the frozen list is how an exhaustive survey
    turns into a partial one without anything looking wrong."""
    write_json(
        repo / INVENTORY,
        {"units": [_unit("src/api", "clean"), _unit("src/web", "clean")]},
    )
    write(repo / FINDINGS / "src-api.md", _record("src/api", "clean"))
    write(repo / FINDINGS / "src-web.md", _record("src/web", "clean"))
    _commit(repo, "freeze the inventory")

    write_json(repo / INVENTORY, {"units": [_unit("src/api", "clean")]})

    result = verify_records(logger)

    assert result.holds is False
    assert "[dropped-unit] 'src/web' was in the committed inventory (HEAD)" in (
        result.verify_errors
    )


def test_a_split_is_lineage_not_a_drop(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """`split_unit` legitimately removes a parent, and the children's paths are the proof
    — which is why this check reads paths and not just ids."""
    write_json(repo / INVENTORY, {"units": [_unit("src", "pending")]})
    _commit(repo, "freeze the inventory")

    write_json(
        repo / INVENTORY,
        {"units": [_unit("src/api", "clean"), _unit("src/web", "clean")]},
    )
    write(repo / FINDINGS / "src-api.md", _record("src/api", "clean"))
    write(repo / FINDINGS / "src-web.md", _record("src/web", "clean"))

    result = verify_records(logger)

    assert result.holds is True
    assert "dropped-unit" not in result.verify_errors


def test_the_shrinkage_check_fails_open_with_no_committed_baseline(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """Nothing committed, nothing to compare. The gate reports on what it can see rather
    than inventing a verdict about what it cannot — the repo fixture has no commits."""
    write_json(repo / INVENTORY, {"units": [_unit("src/api", "clean")]})
    write(repo / FINDINGS / "src-api.md", _record("src/api", "clean"))

    result = verify_records(logger)

    assert result.holds is True


def test_the_survey_directory_travels_with_the_parameters(
    repo: Path, logger: logging.Logger, write: Write, write_json: WriteJson
) -> None:
    """The parity surveyor runs this same gate over its own survey dir."""
    inventory = "docs/survey/legacy-vs-new/inventory.json"
    findings = "docs/survey/legacy-vs-new/findings"
    write_json(repo / inventory, {"units": [_unit("legacy/reports/q1", "clean")]})
    write(repo / findings / "legacy-reports-q1.md", _record("legacy/reports/q1", "clean"))

    result = verify_records(logger, inventory=inventory, findings_dir=findings)

    assert result.holds is True
    assert "1 unit(s)" in result.verify_report
