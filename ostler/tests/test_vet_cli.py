from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import write
from ostler import cli, doctor
from ostler.cli import _build_parser
from ostler.model import load
from ostler.vet.regions import RegionBox, RegionList
from ostler.vet.report import VetReport
from ostler.vet.run import VetOutcome, run_vet


def report_of(outcome: VetOutcome) -> VetReport:
    """The report of a run that completed — `run_vet` sets one whenever `error` is empty.

    Checking `error` here as well means a run that fails for an unrelated reason (an
    unreadable manifest, a missing regions file) fails on this line quoting the message,
    rather than on an attribute of `None` in whichever assertion the test happened to
    write first. The tests that are *about* a run error read `outcome.error` directly.
    """
    assert not outcome.error, outcome.error
    assert outcome.report is not None, "a run without an error must carry a report"
    return outcome.report


def parse(argv):
    return _build_parser().parse_args(argv)


def _write_manifest(repo: Path, elements: list[dict]) -> Path:
    path = repo / "manifest.json"
    write(path, json.dumps(elements))
    return path


def _write_regions(repo: Path, regions: list[dict]) -> Path:
    path = repo / "regions.json"
    boxes = [RegionBox.model_validate(r) for r in regions]
    write(path, RegionList.dump_json(boxes).decode("utf-8"))
    return path


def _screenshot(repo: Path) -> Path:
    path = repo / "shot.png"
    write(path, "not a real image")
    return path


NAV_ELEMENT = {"selector": "#nav", "role": "navigation",
              "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}
NAV_REGION = {"bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
             "role": "navigation", "selectors": ["#nav"]}


def test_cdp_url_and_regions_together_errors_at_argparse_level():
    with pytest.raises(SystemExit):
        parse(["vet", "shot.png", "--manifest", "m.json", "--cdp-url", "http://x",
              "--regions", "r.json", "--slug", "01-foo"])


def test_neither_cdp_url_nor_regions_errors_at_argparse_level():
    with pytest.raises(SystemExit):
        parse(["vet", "shot.png", "--manifest", "m.json", "--slug", "01-foo"])


def test_dry_run_writes_nothing(repo: Path):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)
    vet_md = repo / "docs/specs/01-foo/vet.md"

    outcome, plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    assert not outcome.error
    assert report_of(outcome).summary.status == "clean"
    assert plan.render()  # non-empty diff of would-be writes
    assert not vet_md.exists()


def test_write_creates_report_and_concept_and_stays_doctor_clean(repo: Path):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    outcome, plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    plan.apply()

    report_path = repo / "docs/specs/01-foo/vet/default-report.json"
    concept_path = repo / "docs/specs/01-foo/vet.md"
    assert report_path.exists()
    assert concept_path.exists()
    assert json.loads(report_path.read_text())["summary"]["status"] == "clean"

    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_disagreement_drives_status_and_exit_code(repo: Path):
    manifest = _write_manifest(repo, [
        {"selector": "#gone", "bbox": {"x": 500, "y": 500, "width": 10, "height": 10}},
    ])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    outcome, _plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    assert report_of(outcome).summary.status == "disagreements"
    assert report_of(outcome).summary.missingCount == 1
    assert report_of(outcome).summary.unexpectedCount == 1


def test_fully_matching_manifest_is_clean(repo: Path):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    outcome, _plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    assert report_of(outcome).summary.status == "clean"


def test_missing_regions_file_is_a_run_error(repo: Path):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    screenshot = _screenshot(repo)

    outcome, plan = run_vet(load(repo), screenshot, manifest, "01-foo",
                            regions_file=repo / "nope.json")
    assert outcome.error and "nope.json" in outcome.error
    assert plan.writes == []


def test_matched_components_get_named_crops(repo: Path):
    Image = pytest.importorskip("PIL.Image")
    screenshot = repo / "shot.png"
    Image.new("RGB", (100, 100), "white").save(screenshot)
    manifest = _write_manifest(repo, [
        {**NAV_ELEMENT, "name": "activity-inbox-mode"},
        {"selector": "#anon", "bbox": {"x": 20, "y": 20, "width": 5, "height": 5}},
    ])
    regions = _write_regions(repo, [
        NAV_REGION,
        {"bbox": {"x": 20, "y": 20, "width": 5, "height": 5}, "role": "form",
         "selectors": ["#anon"]},
    ])

    outcome, plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    plan.apply()

    vet_dir = repo / "docs/specs/01-foo/vet"
    assert (vet_dir / "default-activity-inbox-mode.png").exists()
    assert (vet_dir / "default-component-1.png").exists()  # empty-name positional fallback
    report = json.loads((vet_dir / "default-report.json").read_text())
    crops = {p["dom"]["name"]: p["crop"] for p in report["matched"]}
    assert crops["activity-inbox-mode"] == "vet/default-activity-inbox-mode.png"
    assert crops[""] == "vet/default-component-1.png"
    assert report_of(outcome).summary.status == "clean"


def test_unreadable_screenshot_leaves_matched_crops_unset(repo: Path):
    pytest.importorskip("PIL")
    manifest = _write_manifest(repo, [{**NAV_ELEMENT, "name": "nav"}])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)  # not a real PNG

    outcome, _plan = run_vet(load(repo), screenshot, manifest, "01-foo", regions_file=regions)
    assert report_of(outcome).matched[0].crop is None


def test_cli_exit_code_is_zero_when_clean(repo: Path, capsys):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    code = cli.main(["--chdir", str(repo), "vet", str(screenshot),
                     "--manifest", str(manifest), "--regions", str(regions), "--slug", "01-foo"])
    assert code == 0
    capsys.readouterr()


def test_cli_exit_code_is_one_on_disagreements(repo: Path, capsys):
    manifest = _write_manifest(repo, [
        {"selector": "#gone", "bbox": {"x": 500, "y": 500, "width": 10, "height": 10}},
    ])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    code = cli.main(["--chdir", str(repo), "vet", str(screenshot),
                     "--manifest", str(manifest), "--regions", str(regions), "--slug", "01-foo"])
    assert code == 1
    capsys.readouterr()


def test_cli_json_emits_the_report_verbatim(repo: Path, capsys):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    code = cli.main(["--chdir", str(repo), "vet", str(screenshot), "--manifest", str(manifest),
                     "--regions", str(regions), "--slug", "01-foo", "--json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["slug"] == "01-foo"
    assert out["summary"]["status"] == "clean"


def test_cli_write_flag_applies_the_plan(repo: Path, capsys):
    manifest = _write_manifest(repo, [NAV_ELEMENT])
    regions = _write_regions(repo, [NAV_REGION])
    screenshot = _screenshot(repo)

    code = cli.main(["--chdir", str(repo), "vet", str(screenshot), "--manifest", str(manifest),
                     "--regions", str(regions), "--slug", "01-foo", "--write"])
    assert code == 0
    capsys.readouterr()
    assert (repo / "docs/specs/01-foo/vet.md").exists()
