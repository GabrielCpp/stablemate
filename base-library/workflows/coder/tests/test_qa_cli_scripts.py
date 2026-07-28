"""Tests for the coder workflow's Ostler QA command adapters and four-state routing.

The adapters drive ostler through the in-process ``ostler`` Python API via the
``qa_cli`` helpers (``qa_run`` / ``qa_context`` / ``qa_validate`` /
``qa_context_validate``), each returning ``(returncode, payload, stderr)``. These
tests stub those helpers with canned tuples and drive each adapter's ``main()``
in-process, so they exercise the adapter's *routing* (status normalization, notes,
emit shape) without a real QA run — the same seam the old PATH-shim faked.

The stub goes on the ``qa_cli`` module itself, never on the adapter module: an
adapter binds the helper inside ``main()`` (``qa_cli = fresh_import("qa_cli", ...)``)
and calls it as ``qa_cli.qa_run(...)``, so it has no module-level name to patch.
See the ``qa_cli`` fixture for the one condition that makes patching it stick.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import pytest
from conftest import _qa_cli_module, script_dir_on_path

SCRIPTS = Path(__file__).parent.parent / "scripts"


@pytest.fixture(name="qa_cli")
def qa_cli_fixture(monkeypatch):
    """The ``qa_cli`` module the adapter under test will actually call.

    ``fresh_import`` normally purges ``sys.modules`` and re-imports, so ``main()``
    would receive a *new* module object and silently drop anything stubbed onto this
    one. ``WORKHORSE_FRESH_IMPORT=0`` turns the purge off — the same thing
    ``workhorse.testing.WorkflowRun`` does for whole-workflow runs — which is what
    makes the returned module the one ``main()`` sees.
    """
    monkeypatch.setenv("WORKHORSE_FRESH_IMPORT", "0")
    return _qa_cli_module()


def _load(script: str):
    name = script.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / script)
    mod = importlib.util.module_from_spec(spec)
    with script_dir_on_path(SCRIPTS):
        spec.loader.exec_module(mod)
    return mod


def _run_main(mod, argv: list[str], capsys) -> dict:
    old_argv = sys.argv
    sys.argv = argv
    try:
        # The adapter imports `qa_cli` from its own script dir inside main(), so the
        # dir has to be importable for exactly that window — see script_dir_on_path.
        with script_dir_on_path(SCRIPTS):
            mod.main(logging.getLogger("test"))
    finally:
        sys.argv = old_argv
    return json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("status", ["passed", "failed", "blocked", "invalid"])
def test_run_adapter_preserves_all_expected_statuses(monkeypatch, capsys, qa_cli, status):
    mod = _load("run-qa-plan.py")
    monkeypatch.setattr(
        qa_cli, "qa_run",
        lambda plan, spec_dir, **kwargs: (0 if status == "passed" else 1,
                                          {"status": status, "notes": f"runner {status}"}, ""))
    out = _run_main(mod, ["run-qa-plan.py", "/spec"], capsys)
    assert out["qa_result"]["status"] == status


def test_run_adapter_normalizes_unknown_status_to_invalid(monkeypatch, capsys, qa_cli):
    mod = _load("run-qa-plan.py")
    monkeypatch.setattr(
        qa_cli, "qa_run", lambda plan, spec_dir, **kwargs: (1, {"status": "weird"}, ""))
    out = _run_main(mod, ["run-qa-plan.py", "/spec"], capsys)
    assert out["qa_result"]["status"] == "invalid"


def test_build_context_forwards_inputs_and_normalizes_exit_one(monkeypatch, capsys, qa_cli):
    mod = _load("build-qa-okf-context.py")
    seen = {}

    def fake_qa_context(spec_dir, *, base, head, features_root, story_file, source_roots, docs_root):
        seen.update(base=base, head=head, source_roots=source_roots, story_file=story_file)
        return 1, {"status": "invalid", "healthFindings": ["unmapped"]}, ""

    monkeypatch.setattr(qa_cli, "qa_context", fake_qa_context)
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


def test_build_context_passes_when_clean(monkeypatch, capsys, qa_cli):
    mod = _load("build-qa-okf-context.py")
    monkeypatch.setattr(
        qa_cli, "qa_context",
        lambda *a, **k: (0, {"healthFindings": []}, ""))
    out = _run_main(
        mod,
        ["build-qa-okf-context.py", "/spec", "", "", "[]", "HEAD", "WORKTREE", "/docs"],
        capsys,
    )
    assert out["qa_context_build"]["status"] == "passed"


def test_context_adapters_support_isolated_flow_output_keys(monkeypatch, capsys, qa_cli):
    build = _load("build-qa-okf-context.py")
    monkeypatch.setattr(qa_cli, "qa_context", lambda *args, **kwargs: (0, {}, ""))
    built = _run_main(
        build,
        [
            "build-qa-okf-context.py",
            "/spec",
            "",
            "",
            "[]",
            "HEAD",
            "WORKTREE",
            "/docs",
            "documentation_context_build",
        ],
        capsys,
    )
    assert built["documentation_context_build"]["status"] == "passed"

    validate = _load("validate-qa-okf-context.py")
    monkeypatch.setattr(
        qa_cli,
        "qa_context_validate",
        lambda spec_dir, **kwargs: (0, {"status": "passed", "problems": []}, ""),
    )
    validated = _run_main(
        validate,
        [
            "validate-qa-okf-context.py",
            "/spec",
            "passed",
            "documentation_context_result",
        ],
        capsys,
    )
    assert validated["documentation_context_result"]["status"] == "passed"


def test_detect_okf_fails_closed_when_feature_tree_is_unreadable(
    tmp_path, monkeypatch, capsys
):
    mod = _load("detect-okf-docs.py")
    (tmp_path / "docs/features").mkdir(parents=True)

    class BrokenOstler:
        def __init__(self, _root):
            pass

        @property
        def graph(self):
            raise ValueError("malformed graph")

    monkeypatch.setattr(mod, "Ostler", BrokenOstler)
    monkeypatch.setattr(sys, "argv", ["detect-okf-docs.py", str(tmp_path)])

    with pytest.raises(SystemExit) as exc:
        mod.main(logging.getLogger("test"))

    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["has_okf"] == "invalid"
    assert out["features_root"] == str(tmp_path / "docs/features")


def test_detect_okf_accepts_configured_greenfield_feature_root(
    tmp_path, monkeypatch, capsys
):
    mod = _load("detect-okf-docs.py")
    (tmp_path / "ostler.yml").write_text("docRoots: {}\n", encoding="utf-8")
    custom = tmp_path / "knowledge/features"

    class Graph:
        doc_roots = {"features": custom}

    class GreenfieldOstler:
        def __init__(self, _root):
            self.graph = Graph()

    monkeypatch.setattr(mod, "Ostler", GreenfieldOstler)
    monkeypatch.setattr(sys, "argv", ["detect-okf-docs.py", str(tmp_path)])

    with pytest.raises(SystemExit) as exc:
        mod.main(logging.getLogger("test"))

    assert exc.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["has_okf"] == "yes"
    assert out["features_root"] == str(custom)


def test_detect_okf_accepts_epics_only_bundle(tmp_path, monkeypatch, capsys):
    mod = _load("detect-okf-docs.py")
    (tmp_path / "docs/epics").mkdir(parents=True)

    class Graph:
        doc_roots = {"features": tmp_path / "docs/features"}

    class BundleOstler:
        def __init__(self, _root):
            self.graph = Graph()

    monkeypatch.setattr(mod, "Ostler", BundleOstler)
    monkeypatch.setattr(sys, "argv", ["detect-okf-docs.py", str(tmp_path)])

    with pytest.raises(SystemExit):
        mod.main(logging.getLogger("test"))

    out = json.loads(capsys.readouterr().out)
    assert out["has_okf"] == "yes"


def test_detect_okf_does_not_treat_generic_agents_config_as_opt_in(
    tmp_path, monkeypatch, capsys
):
    mod = _load("detect-okf-docs.py")
    (tmp_path / "agents.yml").write_text("workspace: {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["detect-okf-docs.py", str(tmp_path)])

    with pytest.raises(SystemExit):
        mod.main(logging.getLogger("test"))

    out = json.loads(capsys.readouterr().out)
    assert out["has_okf"] == "no"


def test_context_and_plan_validation_normalize_invalid(monkeypatch, capsys, qa_cli):
    ctx_mod = _load("validate-qa-okf-context.py")
    monkeypatch.setattr(
        qa_cli, "qa_context_validate",
        lambda spec_dir, **kwargs: (1, {"status": "invalid", "problems": ["bad context"]}, ""))
    ctx = _run_main(ctx_mod, ["validate-qa-okf-context.py", "/spec", "passed"], capsys)
    assert ctx["qa_context_result"]["status"] == "invalid"

    plan_mod = _load("validate-qa-plan.py")
    monkeypatch.setattr(
        qa_cli, "qa_validate",
        lambda plan, spec_dir, **kwargs: (1, {"status": "invalid"}, ""))
    plan = _run_main(plan_mod, ["validate-qa-plan.py", "/spec"], capsys)
    assert plan["qa_plan_validation"]["status"] == "invalid"


def test_context_validation_passes_only_when_all_green(monkeypatch, capsys, qa_cli):
    mod = _load("validate-qa-okf-context.py")
    monkeypatch.setattr(
        qa_cli, "qa_context_validate",
        lambda spec_dir, **kwargs: (0, {"status": "passed", "problems": []}, ""))
    out = _run_main(mod, ["validate-qa-okf-context.py", "/spec", "passed"], capsys)
    assert out["qa_context_result"]["status"] == "passed"


def test_audit_product_refutation_becomes_normal_qa_failure(capsys):
    mod = _load("mark-qa-audit-failed.py")

    out = _run_main(mod, ["mark-qa-audit-failed.py", "Observed persisted wrong value"], capsys)

    assert out == {
        "qa_result": {
            "status": "failed",
            "notes": "Observed persisted wrong value",
        }
    }


def test_assessment_product_diagnosis_becomes_normal_qa_failure(capsys):
    mod = _load("mark-qa-assessment-failed.py")

    out = _run_main(mod, ["mark-qa-assessment-failed.py", "Unexpected 500 observed"], capsys)

    assert out == {
        "qa_result": {
            "status": "failed",
            "notes": "Unexpected 500 observed",
        }
    }


def test_clear_qa_gate_state_removes_consumed_diagnostics(capsys):
    mod = _load("clear-qa-gate-state.py")

    out = _run_main(mod, ["clear-qa-gate-state.py"], capsys)

    assert out == {
        "qa_plan_validation": {"notes": ""},
        "qa_plan_review": {"notes": ""},
        "qa_assessment": {"notes": ""},
        "qa_audit": {"notes": ""},
        "qa_result": {"notes": ""},
    }
