"""The Register: records on a shelf in the artifacts dir, one listing line each, found by id or handle."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pydantic
import pytest

from ostler import doctor, ids, path as path_mod, register
from ostler.api import Ostler
from ostler.cli import main
from ostler.model import load


def run(root: Path, *argv: str) -> int:
    return main(["-C", str(root), *argv])


def artifacts() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def record(**over: object) -> register.Record:
    fields: dict[str, object] = {
        "id": "acme-1", "repo": "api-service", "area": "billing", "pattern": "extract-module",
        "filed_by": "coder", "summary": "Extract the invoice rounding rules",
    }
    return register.Record.model_validate({**fields, **over})


def test_a_record_survives_the_trip_through_record_md(tmp_path: Path) -> None:
    filed = record(symbols=["billing/rounding.py", "Invoice.total"], source_story="acme-9",
                   body="The slice worked without it.\n\n- one\n- two", reason="kept")
    target = tmp_path / "record.md"
    target.write_text(filed.render(), encoding="utf-8")

    assert register.Record.read(target) == filed
    assert target.read_text(encoding="utf-8").startswith("---\nid: acme-1\nrepo: api-service\n")


@pytest.mark.parametrize("over", [
    {"repo": ""}, {"area": ""}, {"repo": "Api Service"}, {"area": "billing/rounding"},
    {"area": "../escape"}, {"summary": ""}, {"summary": "two\nlines"}, {"id": ""},
])
def test_a_record_without_a_repository_or_area_is_refused(over: dict) -> None:
    with pytest.raises(pydantic.ValidationError):
        record(**over)


def test_write_lays_the_record_under_repo_area_id_in_the_artifacts_dir(tmp_path: Path) -> None:
    graph = load(tmp_path)

    written = register.write(graph, record())

    assert written.ok
    expected = artifacts() / "backlog/api-service/billing/acme-1/record.md"
    assert written.paths == [expected] and expected.is_file()
    assert path_mod.register_root(graph) == artifacts() / "backlog"
    assert not (tmp_path / "docs/backlog").exists()
    assert (artifacts() / ".git").exists()


def test_write_refuses_an_id_that_is_already_taken(tmp_path: Path) -> None:
    graph = load(tmp_path)
    register.write(graph, record())
    before = (artifacts() / "backlog/api-service/billing/acme-1/record.md").read_text()

    again = register.write(graph, record(repo="web-app", area="ui", summary="Something else"))

    assert not again.ok and "acme-1" in again.message
    assert (artifacts() / "backlog/api-service/billing/acme-1/record.md").read_text() == before
    assert not (artifacts() / "backlog/web-app").exists()


def test_the_listing_has_one_line_per_record_closed_ones_included(tmp_path: Path) -> None:
    graph = load(tmp_path)
    register.write(graph, record(id="acme-2", repo="web-app", area="ui", pattern="widen-api",
                                 summary="Widen the form API"))
    register.write(graph, record(id="acme-1", status="done", reason="landed"))
    register.write(graph, record(id="acme-3", status="dropped", reason="stale", area="auth"))

    lines = register.listing(register.records(graph).records)

    assert lines == [
        "acme-3\tapi-service\tauth\tdropped\textract-module\tExtract the invoice rounding rules",
        "acme-1\tapi-service\tbilling\tdone\textract-module\tExtract the invoice rounding rules",
        "acme-2\tweb-app\tui\topen\twiden-api\tWiden the form API",
    ]


def test_a_short_handle_locates_the_records_folder(tmp_path: Path) -> None:
    graph = load(tmp_path)
    minted = ids.allocate(graph, "acme")
    register.write(graph, record(id=minted))

    handle = ids.table(ids.known(graph))[minted]

    assert handle != minted
    assert register.locate(graph, handle) == artifacts() / f"backlog/api-service/billing/{minted}"
    assert register.locate(graph, minted) == artifacts() / f"backlog/api-service/billing/{minted}"
    assert register.locate(graph, "acme-nothing") is None


def test_known_ids_include_every_record_on_the_shelf(tmp_path: Path) -> None:
    register.write(load(tmp_path), record())

    assert "acme-1" in ids.known(load(tmp_path))


def test_open_records_are_the_open_ones_of_one_repository(tmp_path: Path) -> None:
    graph = load(tmp_path)
    register.write(graph, record(id="acme-1"))
    register.write(graph, record(id="acme-2", status="done"))
    register.write(graph, record(id="acme-3", repo="web-app"))

    assert [r.id for r in register.open_records(graph, "api-service")] == ["acme-1"]


def test_an_unparsable_record_is_skipped_by_the_listing_and_named_by_the_doctor(
    tmp_path: Path,
) -> None:
    graph = load(tmp_path)
    register.write(graph, record())
    broken = artifacts() / "backlog/api-service/billing/acme-2/record.md"
    broken.parent.mkdir(parents=True)
    broken.write_text("---\nid: acme-2\nrepo: api-service\n---\nno area, no summary\n")

    read = register.records(graph)

    assert [r.id for r in read.records] == ["acme-1"]
    assert read.unreadable == (broken,)
    findings = [f for f in doctor.run(load(tmp_path)).findings if f.code == "register-record-unreadable"]
    assert len(findings) == 1 and str(broken) in findings[0].message


def test_the_doctor_is_silent_over_a_good_shelf(tmp_path: Path) -> None:
    register.write(load(tmp_path), record())

    assert not [f for f in doctor.run(load(tmp_path)).findings
                if f.code == "register-record-unreadable"]


def test_file_record_mints_an_id_and_writes_it(tmp_path: Path) -> None:
    okf = Ostler(tmp_path)

    filing = okf.file_record(repo="api-service", area="billing", pattern="extract-module",
                             summary="Extract the rounding rules", filed_by="coder")

    assert filing.ok and filing.record is not None and filing.path is not None
    assert filing.record.id and filing.record.id in ids.known(okf.reload().graph)
    assert filing.path == okf.register_root() / "api-service/billing" / filing.record.id / "record.md"
    assert filing.path.is_file()


def test_file_record_without_an_area_files_nothing(tmp_path: Path) -> None:
    okf = Ostler(tmp_path)

    filing = okf.file_record(repo="api-service", area="", pattern="x", summary="s", filed_by="coder")

    assert not filing.ok and filing.record is None
    assert not (artifacts() / "backlog").exists()


def test_backlog_list_prints_one_line_per_record(tmp_path: Path, capsys) -> None:
    graph = load(tmp_path)
    register.write(graph, record(id="acme-1"))
    register.write(graph, record(id="acme-2", repo="web-app", area="ui", pattern="widen-api",
                                 summary="Widen the form API"))
    capsys.readouterr()

    assert run(tmp_path, "backlog", "list") == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert all(token in lines[0] for token in
               ("api-service", "billing", "extract-module", "Extract the invoice rounding rules"))
    assert all(token in lines[1] for token in ("web-app", "ui", "widen-api", "Widen the form API"))


def test_backlog_list_filters_by_repo_and_status(tmp_path: Path, capsys) -> None:
    graph = load(tmp_path)
    register.write(graph, record(id="acme-1"))
    register.write(graph, record(id="acme-2", status="done"))
    register.write(graph, record(id="acme-3", repo="web-app", area="ui"))
    capsys.readouterr()

    assert run(tmp_path, "backlog", "list", "--repo", "api-service", "--status", "open") == 0
    lines = capsys.readouterr().out.splitlines()

    assert len(lines) == 1 and "acme-1" in lines[0]


def test_backlog_list_json_emits_the_records(tmp_path: Path, capsys) -> None:
    register.write(load(tmp_path), record())
    capsys.readouterr()

    assert run(tmp_path, "backlog", "list", "--json") == 0

    rows = json.loads(capsys.readouterr().out)
    assert [(r["id"], r["repo"], r["area"], r["pattern"]) for r in rows] == [
        ("acme-1", "api-service", "billing", "extract-module")]


def test_backlog_list_over_an_empty_shelf_says_none(tmp_path: Path, capsys) -> None:
    capsys.readouterr()

    assert run(tmp_path, "backlog", "list") == 0

    assert capsys.readouterr().out.strip() == "(none)"
