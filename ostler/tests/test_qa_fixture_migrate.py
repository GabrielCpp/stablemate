"""`ostler qa fixtures migrate` — one-shot, mechanical `qa: {fixtures:}` to fixture-node.

Every case below is static: no fixture command is ever run, only resolved and written into
a node file. The three refusals (`declared` errors, an unresolved tool, a destination
collision) all fire before anything is written, on purpose — a partial migration would
leave some fixtures declared twice, in agents.yml and as a node, with nothing saying which
one a plan should trust.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ostler import cli
from ostler.cli import _build_parser
from ostler.cli import main
from ostler.model import load
from ostler.qa import book_fixtures, fixtures

from conftest import write
from test_doctor_fixture_grammar import RUNBOOK, RUNBOOK_PATH

ONE_FIXTURE = """\
qa:
  tools: [node]
  fixtures:
    three-identities:
      tool: node
      args: ["auth/seed.mjs", "--holders=2"]
      provides: "the adjuster, holder A and holder B exist in the auth emulator"
"""

_CFG = {"qa_tools": {"node": {"command": "node"}}}


def _agents_yml(root: Path, body: str) -> None:
    (root / "agents.yml").write_text(body, encoding="utf-8")


def test_a_well_formed_fixture_is_written_as_a_run_step(tmp_path: Path) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)

    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures", cfg=_CFG)

    assert result.ok, result.message
    written = tmp_path / "docs/features/acme/fixtures/three-identities.md"
    assert written.is_file()
    body = written.read_text(encoding="utf-8")
    assert "title: Three identities" in body
    assert "- kind: run" in body
    assert "- run: node auth/seed.mjs --holders=2" in body
    # Neither old vocabulary carries over mechanically — the prose survives as a comment.
    assert "provides:" not in body.split("## Steps")[1]
    assert "the adjuster, holder A and holder B exist in the auth emulator" in body
    assert result.data["paths"] == ["docs/features/acme/fixtures/three-identities.md"]


def test_no_fixtures_declared_is_a_no_op(tmp_path: Path) -> None:
    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures")

    assert result.ok
    assert not (tmp_path / "docs/features/acme/fixtures").exists()


def test_a_malformed_declaration_refuses_before_writing_anything(tmp_path: Path) -> None:
    _agents_yml(tmp_path, "qa:\n  tools: [node]\n  fixtures:\n    seeded: 'node auth/seed.mjs'\n")

    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures", cfg=_CFG)

    assert not result.ok
    assert not (tmp_path / "docs/features/acme/fixtures").exists()


def test_an_unresolved_tool_refuses_before_writing_anything(tmp_path: Path) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)

    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures")  # no cfg — node undefined

    assert not result.ok
    assert "three-identities" in result.message
    assert "node" in result.message
    assert not (tmp_path / "docs/features/acme/fixtures").exists()


def test_an_existing_destination_file_is_never_overwritten(tmp_path: Path) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)
    dest = tmp_path / "docs/features/acme/fixtures"
    dest.mkdir(parents=True)
    (dest / "three-identities.md").write_text("hand-written\n", encoding="utf-8")

    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures", cfg=_CFG)

    assert not result.ok
    assert "three-identities" in result.message
    assert (dest / "three-identities.md").read_text(encoding="utf-8") == "hand-written\n"


def test_an_out_dir_outside_the_repo_root_refuses_cleanly(tmp_path: Path) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-fixtures"

    result = fixtures.migrate(tmp_path, str(outside), cfg=_CFG)

    assert not result.ok
    assert str(outside) in result.message or "outside" in result.message
    assert not outside.exists()


def test_a_migrated_node_round_trips_through_book_fixtures_and_doctor_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """The shape sub-item b must not quietly break: a migrated node reads back as one run
    step with the exact resolved command, and a repo with a stack to bring up (a runbook)
    still reports zero doctor findings against it.
    """
    _agents_yml(tmp_path, ONE_FIXTURE)
    write(tmp_path / RUNBOOK_PATH, RUNBOOK)

    result = fixtures.migrate(tmp_path, "docs/features/acme/fixtures", cfg=_CFG)
    assert result.ok, result.message
    [written_path] = result.data["paths"]

    graph = load(tmp_path)
    resolved = book_fixtures.resolved(graph)

    [step] = resolved["three-identities"]["steps"]
    assert step["command"] == "node auth/seed.mjs --holders=2"
    assert step["cwd"] == str(tmp_path.resolve())
    assert step["timeout"] == 600.0

    code = main(["-C", str(tmp_path), "doctor", "--no-index",
                 "--path", written_path, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["findings"] == []


@dataclass
class _GraphStub:
    root: Path


def _run(root: Path, argv: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str]:
    args = _build_parser().parse_args(argv)
    code = cli._cmd_qa(_GraphStub(root=root), args)
    return code, capsys.readouterr().out


def test_cli_migrate_reports_an_unresolved_tool(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _agents_yml(tmp_path, ONE_FIXTURE)

    code, out = _run(
        tmp_path,
        ["qa", "fixtures", "migrate", "--in", "docs/features/acme/fixtures"],
        capsys,
    )

    assert code == 1  # no [qa_tools.node] configured on the test host
    assert "node" in out
    assert not (tmp_path / "docs/features/acme/fixtures").exists()


def test_cli_migrate_json_envelope_carries_status(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    code, out = _run(
        tmp_path,
        ["qa", "fixtures", "migrate", "--in", "docs/features/acme/fixtures", "--json"],
        capsys,
    )

    assert code == 0  # nothing declared — a no-op success
    payload = json.loads(out)
    assert payload["status"] == "passed"
