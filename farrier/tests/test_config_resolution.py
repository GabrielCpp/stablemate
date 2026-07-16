"""Standalone tests for farrier's library-layer resolution and config CLI.

Run directly (no pytest required):
    uv run python tests/test_config_resolution.py
"""

import os
import sys
import tempfile
import types
from contextlib import contextmanager
from pathlib import Path

from farrier import config, install, layers


def make_library(root: Path) -> Path:
    """Create a minimal but valid library directory (library/ + packs/)."""
    (root / "library").mkdir(parents=True)
    (root / "packs").mkdir()
    return root


def with_temp_config(fn):
    """Run fn with config.CONFIG_PATH pointed at a throwaway file."""
    original = config.CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        config.CONFIG_PATH = Path(tmp) / "config.toml"
        try:
            fn(Path(tmp))
        finally:
            config.CONFIG_PATH = original


@contextmanager
def base_library(path: Path | None):
    """Pretend the `stablemate-library` wheel is installed at `path` (or absent).

    The tools discover the base with an optional import, so the two cases that matter
    — wheel present, wheel absent — are both reachable only by stubbing the lookup.
    """
    original = layers.base_library_dir
    layers.base_library_dir = lambda: path
    try:
        yield
    finally:
        layers.base_library_dir = original


@contextmanager
def wheel_installed_at(path: Path | None):
    """Pin the optional `from stablemate_library import base_dir` branch of the real
    ``base_library_dir()`` (the other tests stub the whole function; this one exercises
    its internals). A path makes the import resolve to a fake module returning it; None
    makes it raise ImportError (a None entry in ``sys.modules`` signals a failed import)."""
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


def clear_env():
    os.environ.pop("FARRIER_LIBRARY_DIR", None)
    os.environ.pop("STABLEMATE_BASE_DIR", None)


def test_is_library_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_library(Path(tmp) / "agents")
        assert install.is_library_dir(root)
        assert not install.is_library_dir(Path(tmp))

        # packs/ is NOT required: the base library ships workflows and skills with
        # no packs at all, and a repo selects from it directly in agents.yml.
        workflows_only = Path(tmp) / "base"
        (workflows_only / "workflows").mkdir(parents=True)
        assert install.is_library_dir(workflows_only)
    print("ok: is_library_dir")


def test_write_then_read_config():
    def body(tmp: Path):
        lib = make_library(tmp / "agents")
        install.write_library_dir(lib)
        assert config.CONFIG_PATH.exists()
        assert install.read_config()["library_dir"] == str(lib)

    with_temp_config(body)
    print("ok: write_then_read_config")


def test_precedence_flag_over_env_over_config():
    def body(tmp: Path):
        clear_env()
        cfg_lib = make_library(tmp / "cfg")
        env_lib = make_library(tmp / "env")
        flag_lib = make_library(tmp / "flag")
        install.write_library_dir(cfg_lib)

        # config only
        assert install.resolve_library_dir(None) == cfg_lib.resolve()
        # env overrides config
        os.environ["FARRIER_LIBRARY_DIR"] = str(env_lib)
        assert install.resolve_library_dir(None) == env_lib.resolve()
        # flag overrides env + config
        assert install.resolve_library_dir(flag_lib) == flag_lib.resolve()
        clear_env()

    with_temp_config(body)
    print("ok: precedence flag > env > config")


def test_no_overlay_is_fine_when_base_is_installed():
    """The base alone is a usable library — that is the public, zero-config setup."""

    def body(tmp: Path):
        clear_env()
        base = make_library(tmp / "base")
        with base_library(base):
            assert install.resolve_library_dir(None) is None
            install.set_layers(None)
            assert [layer.name for layer in install.LAYERS] == [
                install.BASE_LAYER_NAME
            ]

    with_temp_config(body)
    print("ok: no overlay resolves to the base alone")


def test_unresolved_errors_with_hint():
    """No overlay AND no base is the only genuinely unusable case."""

    def body(tmp: Path):
        clear_env()
        with base_library(None):
            try:
                install.resolve_library_dir(None)
            except SystemExit as exc:
                assert "pip install stablemate-library" in str(exc)
                assert "config set-library" in str(exc)
                return
        raise AssertionError("expected SystemExit with no overlay and no base")

    with_temp_config(body)
    print("ok: unresolved errors with setup hint")


def test_bad_library_path_errors():
    def body(tmp: Path):
        clear_env()
        not_a_lib = tmp / "empty"
        not_a_lib.mkdir()
        try:
            install.resolve_library_dir(not_a_lib)
        except SystemExit as exc:
            assert "library/ or workflows/" in str(exc)
            return
        raise AssertionError("expected SystemExit for a non-library path")

    with_temp_config(body)
    print("ok: bad library path errors")


def test_base_library_dir_resolution_order():
    """`$STABLEMATE_BASE_DIR` > config `base_dir` > wheel import > `stablemate_dir` checkout.

    This is the discovery path that makes the base reachable from an isolated
    ``pipx install farrier``, which cannot import a separately-installed wheel."""

    def body(tmp: Path):
        clear_env()
        env_base = make_library(tmp / "env")
        cfg_base = make_library(tmp / "cfg")
        wheel_base = make_library(tmp / "wheel")
        checkout = tmp / "checkout"
        derived = checkout / "base-library" / "stablemate_library"
        (derived / "workflows").mkdir(parents=True)

        # 4. the checkout derivation is the lowest-precedence real source
        install.write_stablemate_dir(checkout)
        with wheel_installed_at(None):
            assert layers.base_library_dir() == derived.resolve()

        # 3. an importable wheel outranks the checkout
        with wheel_installed_at(wheel_base):
            assert layers.base_library_dir() == wheel_base

        # 2. a configured base_dir outranks the wheel
        install.write_base_dir(cfg_base)
        with wheel_installed_at(wheel_base):
            assert layers.base_library_dir() == cfg_base.resolve()

        # 1. the env var outranks everything
        os.environ["STABLEMATE_BASE_DIR"] = str(env_base)
        with wheel_installed_at(wheel_base):
            assert layers.base_library_dir() == env_base.resolve()
        clear_env()

        # an invalid override is skipped, not raised on — it falls through to the next
        # source. With the config cleared, that next source is the wheel.
        config.CONFIG_PATH.unlink(missing_ok=True)
        os.environ["STABLEMATE_BASE_DIR"] = str(tmp / "does-not-exist")
        with wheel_installed_at(wheel_base):
            assert layers.base_library_dir() == wheel_base
        clear_env()

        # nothing configured and no wheel -> None (overlay-only, exactly as before)
        with wheel_installed_at(None):
            assert layers.base_library_dir() is None

    with_temp_config(body)
    print("ok: base_library_dir resolution order (env > config > wheel > checkout)")


def test_overlay_shadows_base():
    """A higher layer wins name-for-name — the whole point of layering."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        base = make_library(root / "base")
        overlay = make_library(root / "overlay")

        for lib, body in ((base, "# from base"), (overlay, "# from overlay")):
            skill = lib / "library" / "skills" / "demo" / "shared"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(body, encoding="utf-8")
        # A skill only the base defines still resolves through the overlay.
        only_base = base / "library" / "skills" / "demo" / "base-only"
        only_base.mkdir(parents=True)
        (only_base / "SKILL.md").write_text("# base only", encoding="utf-8")

        with base_library(base):
            install.set_layers(overlay)
            sources = {
                source.id: source
                for source in install.load_layered_sources("skill", "library", "skills")
            }

        assert set(sources) == {"demo/shared", "demo/base-only"}
        assert sources["demo/shared"].path.read_text() == "# from overlay"
        assert sources["demo/shared"].layer.root == overlay
        assert sources["demo/base-only"].layer.name == install.BASE_LAYER_NAME
    print("ok: overlay shadows base, base fills the gaps")


def test_unknown_pack_names_the_layers():
    """The error a public clone hits must explain the overlay, not just say 'unknown'."""
    with tempfile.TemporaryDirectory() as tmp:
        base = make_library(Path(tmp) / "base")
        with base_library(base):
            install.set_layers(None)
            try:
                install.load_pack("python-workflow")
            except SystemExit as exc:
                message = str(exc)
                assert "python-workflow" in message
                assert install.BASE_LAYER_NAME in message
                assert "config set-library" in message
                print("ok: unknown pack names the searched layers")
                return
        raise AssertionError("expected SystemExit for a pack no layer provides")


if __name__ == "__main__":
    test_is_library_dir()
    test_write_then_read_config()
    test_precedence_flag_over_env_over_config()
    test_no_overlay_is_fine_when_base_is_installed()
    test_unresolved_errors_with_hint()
    test_bad_library_path_errors()
    test_base_library_dir_resolution_order()
    test_overlay_shadows_base()
    test_unknown_pack_names_the_layers()
    print("\nall config-resolution tests passed")
