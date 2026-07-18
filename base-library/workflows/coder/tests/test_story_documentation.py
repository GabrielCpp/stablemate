"""Deterministic hard-gate tests for per-story OKF documentation."""

from __future__ import annotations

import json
import logging
import runpy
import sys
from pathlib import Path

from ostler import Ostler

from conftest import WORKFLOW


SCRIPT = WORKFLOW.parent / "scripts" / "verify-story-documentation.py"


def _packet(path: Path, *, reason: str = "changed-code") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "changedCode": [
                    {
                        "path": "src/view.py",
                        "basePath": "src/view.py",
                        "headPath": "src/view.py",
                    }
                ],
                "directNodes": [
                    {
                        "node": "docs/features/acme/gui/screens/home.md",
                        "reasons": [
                            {
                                "kind": reason,
                                "ref": (
                                    "acme:src/view.py"
                                    if reason == "surface-owner"
                                    else "src/view.py::render"
                                ),
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _run(
    tmp_path: Path,
    monkeypatch,
    capsys,
    *,
    doctor: dict | None = None,
    nodes: list[str] | None = None,
    context_mode: str = "local",
) -> dict:
    namespace = runpy.run_path(str(SCRIPT), run_name="story_documentation_gate")
    monkeypatch.setattr(
        Ostler,
        "doctor",
        lambda self: doctor or {"findings": []},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            str(tmp_path),
            "docs/specs/s-1",
            "documented",
            "passed",
            "passed",
            context_mode,
            json.dumps(nodes or ["docs/features/acme/gui/screens/home.md"]),
        ],
    )
    namespace["main"](logging.getLogger("test-story-documentation"))
    return json.loads(capsys.readouterr().out)["documentation_gate"]


def test_documentation_gate_accepts_direct_grounding_and_clean_doctor(
    tmp_path, monkeypatch, capsys
):
    _packet(tmp_path / "docs/specs/s-1/qa-okf-context.json")

    result = _run(tmp_path, monkeypatch, capsys)

    assert result["status"] == "passed"
    assert result["changed_code_count"] == 1


def test_semantic_multi_repo_mode_does_not_require_docs_root_git_context(
    tmp_path, monkeypatch, capsys
):
    result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        context_mode="semantic",
        nodes=["docs/features/acme/gui/screens/home.md"],
    )

    assert result["status"] == "passed"


def test_documentation_gate_rejects_surface_only_ownership(tmp_path, monkeypatch, capsys):
    _packet(
        tmp_path / "docs/specs/s-1/qa-okf-context.json",
        reason="surface-owner",
    )

    result = _run(tmp_path, monkeypatch, capsys)

    assert result["status"] == "invalid"
    assert "only broad surface ownership" in result["notes"]


def test_documentation_gate_rejects_file_owner_for_changed_symbols(
    tmp_path, monkeypatch, capsys
):
    packet_path = tmp_path / "docs/specs/s-1/qa-okf-context.json"
    _packet(packet_path, reason="file-owner")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["changedCode"][0]["headSymbols"] = ["NewPanel"]
    packet["directNodes"][0]["reasons"][0]["ref"] = "src/view.py"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    result = _run(tmp_path, monkeypatch, capsys)

    assert result["status"] == "invalid"
    assert "only broad surface ownership" in result["notes"]


def test_documentation_gate_requires_every_changed_symbol(tmp_path, monkeypatch, capsys):
    packet_path = tmp_path / "docs/specs/s-1/qa-okf-context.json"
    _packet(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["changedCode"][0]["headSymbols"] = ["ExistingPanel", "NewPanel"]
    packet["directNodes"][0]["reasons"][0]["ref"] = (
        "src/view.py::ExistingPanel"
    )
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    result = _run(tmp_path, monkeypatch, capsys)

    assert result["status"] == "invalid"
    assert "only broad surface ownership" in result["notes"]


def test_documentation_gate_pairs_renamed_paths_with_their_own_symbols(
    tmp_path, monkeypatch, capsys
):
    packet_path = tmp_path / "docs/specs/s-1/qa-okf-context.json"
    _packet(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["changedCode"][0].update(
        {
            "path": "src/new.py",
            "basePath": "src/old.py",
            "headPath": "src/new.py",
            "baseSymbols": ["OldName"],
            "headSymbols": ["NewName"],
        }
    )
    packet["directNodes"][0]["reasons"] = [
        {"kind": "changed-code", "ref": "src/old.py::OldName"},
        {"kind": "changed-code", "ref": "src/new.py::NewName"},
    ]
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    result = _run(tmp_path, monkeypatch, capsys)

    assert result["status"] == "passed"


def test_documentation_gate_rejects_doctor_errors(tmp_path, monkeypatch, capsys):
    _packet(tmp_path / "docs/specs/s-1/qa-okf-context.json")
    report = {
        "findings": [
            {
                "severity": "error",
                "code": "missing-required-section",
                "path": "docs/features/acme/gui/screens/home.md",
                "line": 8,
                "message": "screen is missing Components",
            }
        ]
    }

    result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        doctor=report,
        nodes=["docs/features/acme/gui/screens/home.md#current-panel"],
    )

    assert result["status"] == "invalid"
    assert "missing-required-section" in result["notes"]


def test_documentation_gate_ignores_unrelated_preexisting_doctor_errors(
    tmp_path, monkeypatch, capsys
):
    _packet(tmp_path / "docs/specs/s-1/qa-okf-context.json")
    report = {
        "findings": [
            {
                "severity": "error",
                "code": "missing-code-symbol",
                "path": "docs/features/globex/concepts/legacy.md",
                "line": 5,
                "message": "legacy symbol moved",
            }
        ]
    }

    result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        doctor=report,
        nodes=["docs/features/acme/gui/screens/home.md#current-panel"],
    )

    assert result["status"] == "passed"


def test_semantic_mode_defers_external_code_grounding_to_independent_review(
    tmp_path, monkeypatch, capsys
):
    report = {
        "findings": [
            {
                "severity": "error",
                "code": "dangling-code-ref",
                "path": "docs/features/acme/gui/screens/home.md",
                "line": 8,
                "message": "external service file is not beneath the docs root",
            }
        ]
    }

    result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        doctor=report,
        context_mode="semantic",
    )

    assert result["status"] == "passed"


def test_documentation_gate_ignores_unrelated_sibling_node_error(
    tmp_path, monkeypatch, capsys
):
    packet_path = tmp_path / "docs/specs/s-1/qa-okf-context.json"
    _packet(packet_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["directNodes"][0]["node"] = (
        "docs/features/acme/gui/screens/home.md#current-panel"
    )
    packet["directNodes"].append(
        {
            "node": "docs/features/acme/gui/screens/home.md",
            "reasons": [
                {
                    "kind": "contains-impacted-node",
                    "ref": "docs/features/acme/gui/screens/home.md#current-panel",
                }
            ],
        }
    )
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    screen = tmp_path / "docs/features/acme/gui/screens/home.md"
    screen.parent.mkdir(parents=True)
    screen.write_text(
        "---\ntype: screen\nslug: home\ntitle: Home\n---\n# Home\n\n"
        "## Components\n\n### current-panel\n- role: region\n- name: Current\n"
        "- keyboard: none\n- states: ready\n\n"
        "### legacy-panel\n- role: region\n- name: Legacy\n",
        encoding="utf-8",
    )
    report = {
        "findings": [
            {
                "severity": "error",
                "code": "missing-required-bullet",
                "path": "docs/features/acme/gui/screens/home.md",
                "line": 16,
                "message": "legacy panel is missing keyboard",
            }
        ]
    }

    result = _run(
        tmp_path,
        monkeypatch,
        capsys,
        doctor=report,
        nodes=["docs/features/acme/gui/screens/home.md#current-panel"],
    )

    assert result["status"] == "passed"
