"""Standalone tests for workhorse's layered workflow resolution.

A bare workflow NAME resolves across an ordered stack of library layers: the
configured overlay first, then the base library shipped as the `stablemate-library`
wheel. This is what lets `workhorse run coder` work from a bare pip install while
still letting a private overlay override a base workflow.

Run directly (no pytest required):
    uv run python tests/test_library_layers.py
"""

import importlib
import os
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
        make_workflow(base, "coder", "base-coder")
        with layers(overlay=None, base=base):
            path = main._resolve_workflow_path("coder")
        assert path == (base / "workflows" / "coder" / "workflow.yaml").resolve()
    print("ok: base-only resolves a bare name")


def test_overlay_shadows_base():
    with tempfile.TemporaryDirectory() as tmp:
        base, overlay = Path(tmp) / "base", Path(tmp) / "overlay"
        make_workflow(base, "coder", "base-coder")
        make_workflow(overlay, "coder", "overlay-coder")
        with layers(overlay=overlay, base=base):
            path = main._resolve_workflow_path("coder")
        assert path.read_text().strip() == "name: overlay-coder"
    print("ok: overlay shadows base")


def test_base_fills_gaps_under_an_overlay():
    """An overlay that does not define a workflow must still fall through to the base."""
    with tempfile.TemporaryDirectory() as tmp:
        base, overlay = Path(tmp) / "base", Path(tmp) / "overlay"
        make_workflow(base, "coder", "base-coder")
        make_workflow(overlay, "private", "overlay-private")
        with layers(overlay=overlay, base=base):
            path = main._resolve_workflow_path("coder")
        assert path.read_text().strip() == "name: base-coder"
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


@contextmanager
def wheel_installed_at(path: Path | None):
    """Pin the optional `from stablemate_library import base_dir` branch.

    With a path, the import resolves to a fake module whose ``base_dir()`` returns it;
    with None, the import raises ImportError — a None entry in ``sys.modules`` is how
    Python signals a failed import. This makes the wheel-present / wheel-absent cases
    deterministic regardless of what is actually installed in the test venv."""
    saved = sys.modules.get("stablemate_library")
    if path is None:
        sys.modules["stablemate_library"] = None  # type: ignore[assignment]
    else:
        module = types.ModuleType("stablemate_library")
        module.base_dir = lambda: path  # type: ignore[attr-defined]
        sys.modules["stablemate_library"] = module
    try:
        yield
    finally:
        if saved is None:
            sys.modules.pop("stablemate_library", None)
        else:
            sys.modules["stablemate_library"] = saved


@contextmanager
def config_values(values: dict[str, str]):
    """Back ``get_config_value`` with a dict and clear the base-dir env override."""
    original = main.get_config_value
    main.get_config_value = lambda key: values.get(key)
    os.environ.pop("STABLEMATE_BASE_DIR", None)
    try:
        yield
    finally:
        main.get_config_value = original
        os.environ.pop("STABLEMATE_BASE_DIR", None)


def _make_base(root: Path) -> Path:
    (root / "workflows").mkdir(parents=True)
    return root


def test_base_library_dir_resolution_order():
    """`$STABLEMATE_BASE_DIR` > config `base_dir` > wheel import > `stablemate_dir` checkout.

    This is the path that makes the base reachable from an isolated `pipx install
    workhorse-agent`, which cannot import a separately-installed wheel."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        env_base = _make_base(root / "env")
        cfg_base = _make_base(root / "cfg")
        wheel_base = _make_base(root / "wheel")
        checkout = root / "checkout"
        derived = checkout / "base-library" / "stablemate_library"
        (derived / "workflows").mkdir(parents=True)

        # 4. the checkout derivation is the lowest-precedence real source
        with config_values({"stablemate_dir": str(checkout)}), wheel_installed_at(None):
            assert main._base_library_dir() == derived.resolve()

        # 3. an importable wheel outranks the checkout
        with config_values({"stablemate_dir": str(checkout)}), wheel_installed_at(wheel_base):
            assert main._base_library_dir() == wheel_base

        # 2. a configured base_dir outranks the wheel
        with config_values({"base_dir": str(cfg_base)}), wheel_installed_at(wheel_base):
            assert main._base_library_dir() == cfg_base.resolve()

        # 1. the env var outranks everything
        with config_values({"base_dir": str(cfg_base)}), wheel_installed_at(wheel_base):
            os.environ["STABLEMATE_BASE_DIR"] = str(env_base)
            assert main._base_library_dir() == env_base.resolve()

        # an invalid override is skipped, not raised on — it falls through to the wheel
        with config_values({}), wheel_installed_at(wheel_base):
            os.environ["STABLEMATE_BASE_DIR"] = str(root / "does-not-exist")
            assert main._base_library_dir() == wheel_base

        # nothing configured and no wheel -> None (overlay-only, exactly as before)
        with config_values({}), wheel_installed_at(None):
            assert main._base_library_dir() is None
    print("ok: _base_library_dir resolution order (env > config > wheel > checkout)")


def _expect_exit(spec: str) -> int:
    try:
        main._resolve_workflow_path(spec)
    except SystemExit as exc:
        return exc.code
    raise AssertionError(f"expected SystemExit resolving {spec!r}")


def test_no_layers_at_all_exits():
    with layers(overlay=None, base=None):
        assert _expect_exit("coder") == 1
    print("ok: no layers at all exits non-zero")


def test_name_missing_from_every_layer_exits():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        make_workflow(base, "coder", "base-coder")
        with layers(overlay=None, base=base):
            assert _expect_exit("nope") == 1
    print("ok: a name no layer provides exits non-zero")


if __name__ == "__main__":
    test_base_only_resolves()
    test_overlay_shadows_base()
    test_base_fills_gaps_under_an_overlay()
    test_explicit_path_bypasses_layers()
    test_base_library_dir_resolution_order()
    test_no_layers_at_all_exits()
    test_name_missing_from_every_layer_exits()
    print("\nall library-layer tests passed")
