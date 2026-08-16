"""`ostler.qa.tools` — the opt-in/definition split for QA tools.

A name is opted in via `agents.yml`'s `qa: {tools: [...]}`, then resolved to a command
either from `[qa_tools.<name>]` in the stablemate config or, for the two built-ins,
from `BUILTIN_TOOLS`. Every case below exercises one edge of that split: opted in but
undefined, opted in and overridden, opted in and resolved but missing from PATH.
"""

from __future__ import annotations

from pathlib import Path

from ostler.qa import tools


def _write_agents_yml(root: Path, names: list[str]) -> None:
    joined = ", ".join(names)
    (root / "agents.yml").write_text(f"qa:\n  tools: [{joined}]\n", encoding="utf-8")


def test_opted_in_tools_reads_agents_yml(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["tesseract", "ocr-diff"])
    assert tools.opted_in_tools(tmp_path) == {"tesseract", "ocr-diff"}


def test_opted_in_tools_empty_when_no_config_file(tmp_path: Path) -> None:
    assert tools.opted_in_tools(tmp_path) == set()


def test_opted_in_tools_prefers_ostler_yml_over_agents_yml(tmp_path: Path) -> None:
    (tmp_path / "ostler.yml").write_text("qa:\n  tools: [tesseract]\n", encoding="utf-8")
    _write_agents_yml(tmp_path, ["convert"])
    assert tools.opted_in_tools(tmp_path) == {"tesseract"}


def test_catalog_resolves_builtin_with_no_config(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["tesseract"])
    specs, errors = tools.catalog(tmp_path, cfg={})
    assert errors == []
    assert specs["tesseract"].command == "tesseract"
    assert specs["tesseract"].builtin is True


def test_catalog_lets_machine_config_override_a_builtins_command(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["convert"])
    cfg = {"qa_tools": {"convert": {"command": "magick", "description": "ImageMagick 7"}}}
    specs, errors = tools.catalog(tmp_path, cfg=cfg)
    assert errors == []
    assert specs["convert"].command == "magick"
    assert specs["convert"].builtin is True


def test_catalog_resolves_a_user_declared_tool(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["ocr-diff"])
    cfg = {"qa_tools": {"ocr-diff": {"command": "ocr-diff-cli", "description": "compare OCR output"}}}
    specs, errors = tools.catalog(tmp_path, cfg=cfg)
    assert errors == []
    assert specs["ocr-diff"].command == "ocr-diff-cli"
    assert specs["ocr-diff"].builtin is False


def test_catalog_errors_on_opted_in_name_with_no_definition(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["ocr-diff"])
    specs, errors = tools.catalog(tmp_path, cfg={})
    assert specs == {}
    assert len(errors) == 1
    assert "ocr-diff" in errors[0]
    assert "no [qa_tools.ocr-diff] table" in errors[0]


def test_catalog_errors_on_qa_tools_entry_missing_command(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["ocr-diff"])
    cfg = {"qa_tools": {"ocr-diff": {"description": "no command field"}}}
    specs, errors = tools.catalog(tmp_path, cfg=cfg)
    assert specs == {}
    assert len(errors) == 1
    assert "no `command`" in errors[0]


def test_preflight_errors_reports_missing_binary(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["ocr-diff"])
    cfg = {"qa_tools": {"ocr-diff": {"command": "definitely-not-a-real-binary-xyz"}}}
    errors = tools.preflight_errors(tmp_path, cfg=cfg)
    assert len(errors) == 1
    assert "not on PATH" in errors[0]


def test_preflight_errors_empty_when_tool_resolves_and_is_on_path(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["sh-tool"])
    cfg = {"qa_tools": {"sh-tool": {"command": "sh"}}}
    assert tools.preflight_errors(tmp_path, cfg=cfg) == []


def test_preflight_errors_empty_with_no_opt_in(tmp_path: Path) -> None:
    assert tools.preflight_errors(tmp_path, cfg={}) == []


def test_resolved_commands_maps_name_to_command(tmp_path: Path) -> None:
    _write_agents_yml(tmp_path, ["tesseract", "ocr-diff"])
    cfg = {"qa_tools": {"ocr-diff": {"command": "ocr-diff-cli"}}}
    assert tools.resolved_commands(tmp_path, cfg=cfg) == {
        "tesseract": "tesseract",
        "ocr-diff": "ocr-diff-cli",
    }
