"""The writer and workflow read one compile-readiness verdict on the pages a story touched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.cli import main
from ostler.qa.plan_source import Gap
from ostler.qa.readiness import cmd_compile_gaps, defect_gaps, format_gap
from test_qa_compile import _SCREEN, _arrival_navigation, _navigation_context, _page_obligation, _visible

NAME_ID = f"okf:{_SCREEN}#error-alert:name:1"
ROLE_ID = f"okf:{_SCREEN}#error-alert:role:1"


def _packet(*, with_checks: bool) -> dict:
    obligations = [
        _page_obligation(
            oid,
            f"{_SCREEN}#error-alert",
            locators={"role": ["alert"], "name": ["Error"]},
            checks=[_visible("alert:Error")] if with_checks else [],
            kind=oid.split(":")[-2],
        )
        | {"nodeType": "component"}
        for oid in (NAME_ID, ROLE_ID)
    ]
    return _navigation_context(*obligations, navigation=_arrival_navigation())


def _write_packet(root: Path, *, with_checks: bool = False) -> Path:
    spec = root / "spec"
    spec.mkdir()
    (spec / "qa-okf-context.json").write_text(json.dumps(_packet(with_checks=with_checks)), encoding="utf-8")
    return spec


def test_component_obligations_are_defects_but_placeholders_and_discharged_preconditions_are_not() -> None:
    gaps = [
        Gap(NAME_ID, "no-verify-declared", "declare a check"),
        Gap(f"okf:{_SCREEN}:contract", "no-verify-declared", "placeholder"),
        Gap(f"okf:{_SCREEN}#idle:contract", "precondition-discharged-by-arrangement", "arranged"),
    ]

    assert [format_gap(gap) for gap in defect_gaps(gaps, (_SCREEN,))] == [
        f"no-verify-declared {NAME_ID}: declare a check"
    ]


def test_compile_gaps_reads_the_same_missing_component_checks_the_workflow_rejects(tmp_path: Path) -> None:
    spec = _write_packet(tmp_path)

    result = cmd_compile_gaps(spec, story="STORY-1", pages=(_SCREEN,))

    assert not result.ok
    assert result.status == "failed"
    assert [gap["ref"] for gap in result.data["gaps"]] == [NAME_ID, ROLE_ID]
    lines = result.message.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"no-verify-declared {NAME_ID}: the book declares no check")
    assert lines[1].startswith(f"no-verify-declared {ROLE_ID}: the book declares no check")


def test_compile_gaps_clears_when_the_component_checks_exist(tmp_path: Path) -> None:
    spec = _write_packet(tmp_path, with_checks=True)

    result = cmd_compile_gaps(spec, story="STORY-1", pages=(_SCREEN,))

    assert result.ok
    assert result.data["gaps"] == []


def test_compile_gaps_ignores_another_pages_defects(tmp_path: Path) -> None:
    spec = _write_packet(tmp_path)

    result = cmd_compile_gaps(spec, story="STORY-1", pages=("docs/services/other/screen.md",))

    assert result.ok
    assert result.data["gaps"] == []


@pytest.mark.parametrize("json_output", [False, True])
def test_the_cli_exposes_the_workflow_verdict(tmp_path: Path, json_output: bool, capsys: pytest.CaptureFixture[str]) -> None:
    _write_packet(tmp_path)
    argv = [
        "-C", str(tmp_path), "qa", "compile-gaps", "--spec", "spec", "--story", "STORY-1",
        "--page", _SCREEN,
    ]

    status = main([*argv, *(["--json"] if json_output else [])])

    assert status == 1
    output = capsys.readouterr().out
    if json_output:
        assert [gap["ref"] for gap in json.loads(output)["gaps"]] == [NAME_ID, ROLE_ID]
    else:
        lines = output.splitlines()
        assert len(lines) == 2
        assert lines[0].startswith(f"no-verify-declared {NAME_ID}: the book declares no check")
        assert lines[1].startswith(f"no-verify-declared {ROLE_ID}: the book declares no check")
