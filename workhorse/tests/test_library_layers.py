"""Standalone tests for workhorse's layered workflow resolution.

A bare workflow NAME resolves across an ordered stack of library layers: the
configured overlay first, then the base library shipped as the `stablemate-library`
wheel. This is what lets `workhorse run <name>` work from a bare pip install while
still letting a private overlay override a base workflow.

The fixture name is deliberately one no distribution ships (`acme-flow`): a packaged
entry point wins over every library layer, so naming the fixture after a real
workflow tests the entry-point branch instead of the layering this file is about.

Run directly (no pytest required):
    uv run python tests/test_library_layers.py
"""

import importlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

# `workhorse/__init__.py` re-exports the main() *function*, so `from workhorse import
# main` would bind the function, not the module. Import the module explicitly (the
# convention the other tests here follow).
main = importlib.import_module("workhorse.main")


@contextmanager
def layers(overlay: Path | None, base: Path | None):
    """Stub the two inputs to the search path: the configured overlay and the base."""
    original_config = main.get_config_value
    original_base = main._base_library_dir
    os.environ.pop("WORKHORSE_LIBRARY_DIR", None)
    main.get_config_value = lambda key: str(overlay) if key == "library_dir" else None
    main._base_library_dir = lambda: base
    try:
        yield
    finally:
        main.get_config_value = original_config
        main._base_library_dir = original_base


def make_workflow(root: Path, name: str, marker: str) -> None:
    directory = root / "workflows" / name
    directory.mkdir(parents=True)
    (directory / "workflow.yaml").write_text(f"name: {marker}\n", encoding="utf-8")


def test_base_only_resolves():
    """The zero-config case: `pip install stablemate-library` and run."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        make_workflow(base, "acme-flow", "base-acme-flow")
        with layers(overlay=None, base=base):
            path = main._resolve_workflow_path("acme-flow")
        assert path == (base / "workflows" / "acme-flow" / "workflow.yaml").resolve()
    print("ok: base-only resolves a bare name")


def test_overlay_shadows_base():
    with tempfile.TemporaryDirectory() as tmp:
        base, overlay = Path(tmp) / "base", Path(tmp) / "overlay"
        make_workflow(base, "acme-flow", "base-acme-flow")
        make_workflow(overlay, "acme-flow", "overlay-acme-flow")
        with layers(overlay=overlay, base=base):
            path = main._resolve_workflow_path("acme-flow")
        assert path.read_text().strip() == "name: overlay-acme-flow"
    print("ok: overlay shadows base")


def test_base_fills_gaps_under_an_overlay():
    """An overlay that does not define a workflow must still fall through to the base."""
    with tempfile.TemporaryDirectory() as tmp:
        base, overlay = Path(tmp) / "base", Path(tmp) / "overlay"
        make_workflow(base, "acme-flow", "base-acme-flow")
        make_workflow(overlay, "private", "overlay-private")
        with layers(overlay=overlay, base=base):
            path = main._resolve_workflow_path("acme-flow")
        assert path.read_text().strip() == "name: base-acme-flow"
    print("ok: base fills the gaps under an overlay")


def test_explicit_path_bypasses_layers():
    with tempfile.TemporaryDirectory() as tmp:
        explicit = Path(tmp) / "wf" / "workflow.yaml"
        explicit.parent.mkdir(parents=True)
        explicit.write_text("name: explicit\n", encoding="utf-8")
        with layers(overlay=None, base=None):
            path = main._resolve_workflow_path(str(explicit))
        assert path == explicit.resolve()
    print("ok: an explicit path bypasses the layers")


# Base-library resolution order moved to stablemate_core; its test lives in
# core/tests/test_discovery.py. What remains here is workhorse's own concern:
# how the overlay and base LAYERS stack for a bare workflow name.

def _expect_exit(spec: str) -> int:
    try:
        main._resolve_workflow_path(spec)
    except SystemExit as exc:
        return exc.code
    raise AssertionError(f"expected SystemExit resolving {spec!r}")


def test_no_layers_at_all_exits():
    with layers(overlay=None, base=None):
        assert _expect_exit("acme-flow") == 1
    print("ok: no layers at all exits non-zero")


def test_name_missing_from_every_layer_exits():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        make_workflow(base, "acme-flow", "base-acme-flow")
        with layers(overlay=None, base=base):
            assert _expect_exit("nope") == 1
    print("ok: a name no layer provides exits non-zero")


if __name__ == "__main__":
    test_base_only_resolves()
    test_overlay_shadows_base()
    test_base_fills_gaps_under_an_overlay()
    test_explicit_path_bypasses_layers()
    test_no_layers_at_all_exits()
    test_name_missing_from_every_layer_exits()
    print("\nall library-layer tests passed")
