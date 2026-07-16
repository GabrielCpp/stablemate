"""Tests for the coder workflow's Ostler QA command adapters and four-state routing.

The adapters now drive ostler through the in-process ``ostler`` Python API via the
``qa_cli`` helpers (``qa_run`` / ``qa_context`` / ``qa_validate`` /
``qa_context_validate``), each returning ``(returncode, payload, stderr)``. These
tests stub those helpers with canned tuples and drive each adapter's ``main()``
in-process, so they exercise the adapter's *routing* (status normalization, notes,
emit shape) without a real QA run — the same seam the old PATH-shim faked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))  # so the adapters' `from qa_cli import …` resolves


def _load(script: str):
    name = script.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_main(mod, argv: list[str], capsys) -> dict:
    old_argv = sys.argv
    sys.argv = argv
    try:
        mod.main()
    finally:
        sys.argv = old_argv
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("status", ["passed", "failed", "blocked", "invalid"])
def test_run_adapter_preserves_all_expected_statuses(monkeypatch, capsys, status):
    mod = _load("run-qa-plan.py")
    monkeypatch.setattr(
        mod, "qa_run",
        lambda plan, spec_dir: (0 if status == "passed" else 1,
                                {"status": status, "notes": f"runner {status}"}, ""))
    out = _run_main(mod, ["run-qa-plan.py", "/spec"], capsys)
    assert out["qa_result"]["status"] == status


def test_run_adapter_normalizes_unknown_status_to_invalid(monkeypatch, capsys):
    mod = _load("run-qa-plan.py")
    monkeypatch.setattr(mod, "qa_run", lambda plan, spec_dir: (1, {"status": "weird"}, ""))
    out = _run_main(mod, ["run-qa-plan.py", "/spec"], capsys)
    assert out["qa_result"]["status"] == "invalid"


def test_build_context_forwards_inputs_and_normalizes_exit_one(monkeypatch, capsys):
    mod = _load("build-qa-okf-context.py")
    seen = {}

    def fake_qa_context(spec_dir, *, base, head, features_root, story_file, source_roots, docs_root):
        seen.update(base=base, head=head, source_roots=source_roots, story_file=story_file)
        return 1, {"status": "invalid", "healthFindings": ["unmapped"]}, ""

    monkeypatch.setattr(mod, "qa_context", fake_qa_context)
    out = _run_main(
        mod,
        ["build-qa-okf-context.py", "/spec", "/story.md", "docs/features",
         json.dumps(["api=/api", "web=/web"]), "base-ref", "WORKTREE", "/docs"],
        capsys,
    )
    assert out["qa_context_build"]["status"] == "invalid"
    assert seen["base"] == "base-ref" and seen["head"] == "WORKTREE"
    assert seen["source_roots"] == ["api=/api", "web=/web"]
    assert seen["story_file"] == "/story.md"


def test_build_context_passes_when_clean(monkeypatch, capsys):
    mod = _load("build-qa-okf-context.py")
    monkeypatch.setattr(
        mod, "qa_context",
        lambda *a, **k: (0, {"healthFindings": []}, ""))
    out = _run_main(
        mod,
        ["build-qa-okf-context.py", "/spec", "", "", "[]", "HEAD", "WORKTREE", "/docs"],
        capsys,
    )
    assert out["qa_context_build"]["status"] == "passed"


def test_context_and_plan_validation_normalize_invalid(monkeypatch, capsys):
    ctx_mod = _load("validate-qa-okf-context.py")
    monkeypatch.setattr(
        ctx_mod, "qa_context_validate",
        lambda spec_dir: (1, {"status": "invalid", "problems": ["bad context"]}, ""))
    ctx = _run_main(ctx_mod, ["validate-qa-okf-context.py", "/spec", "passed"], capsys)
    assert ctx["qa_context_result"]["status"] == "invalid"

    plan_mod = _load("validate-qa-plan.py")
    monkeypatch.setattr(
        plan_mod, "qa_validate",
        lambda plan, spec_dir: (1, {"status": "invalid"}, ""))
    plan = _run_main(plan_mod, ["validate-qa-plan.py", "/spec"], capsys)
    assert plan["qa_plan_validation"]["status"] == "invalid"


def test_context_validation_passes_only_when_all_green(monkeypatch, capsys):
    mod = _load("validate-qa-okf-context.py")
    monkeypatch.setattr(
        mod, "qa_context_validate",
        lambda spec_dir: (0, {"status": "passed", "problems": []}, ""))
    out = _run_main(mod, ["validate-qa-okf-context.py", "/spec", "passed"], capsys)
    assert out["qa_context_result"]["status"] == "passed"
