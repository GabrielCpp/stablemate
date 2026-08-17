"""`ostler qa tools list` — the CLI surface over `ostler.qa.tools.catalog`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from ostler import cli
from ostler.cli import _build_parser


@dataclass
class _GraphStub:
    root: Path


def _run(root: Path, argv: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str]:
    args = _build_parser().parse_args(argv)
    code = cli._cmd_qa(_GraphStub(root=root), args)
    return code, capsys.readouterr().out


def test_tools_list_reports_resolved_builtin(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    (tmp_path / "agents.yml").write_text("qa:\n  tools: [tesseract]\n", encoding="utf-8")

    code, out = _run(tmp_path, ["qa", "tools", "list"], capsys)

    assert code in (0, 1)  # tesseract may or may not be installed on the test host
    assert "tesseract" in out


def test_tools_list_json_reports_undefined_tool_as_error(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    (tmp_path / "agents.yml").write_text("qa:\n  tools: [ocr-diff]\n", encoding="utf-8")

    code, out = _run(tmp_path, ["qa", "tools", "list", "--json"], capsys)

    assert code == 1
    payload = json.loads(out)
    assert payload["tools"] == []
    assert len(payload["errors"]) == 1
    assert "ocr-diff" in payload["errors"][0]


def test_tools_list_empty_with_no_opt_in(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    code, out = _run(tmp_path, ["qa", "tools", "list", "--json"], capsys)

    assert code == 0
    payload = json.loads(out)
    # `status` comes from the shared `QaOutcome` envelope every qa command answers in.
    assert payload == {"tools": [], "errors": [], "status": "passed"}
