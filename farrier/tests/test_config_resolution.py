"""Standalone tests for farrier's library-layer resolution and config CLI.

Run directly (no pytest required):
    uv run python tests/test_config_resolution.py
"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from farrier import install, layers
from stablemate_core import config


def make_library(root: Path) -> Path:
    """Create a minimal but valid library directory (library/ + packs/)."""
    (root / "library").mkdir(parents=True)
    (root / "packs").mkdir()
    return root


def with_temp_config(fn):
    """Run fn against a throwaway config file, isolated from this machine's real one.

    Redirecting $STABLEMATE_CONFIG alone is not enough: when that file is absent,
    read_config() falls back to the legacy per-tool paths (~/.config/workhorse,
    ~/.config/farrier), so a test would read the developer's actual library_dir.
    Neutralize that route too.
    """
    original_env = os.environ.get(config.CONFIG_PATH_ENV)
    original_legacy = config.legacy_config_paths
    with tempfile.TemporaryDirectory() as tmp:
        os.environ[config.CONFIG_PATH_ENV] = str(Path(tmp) / "config.toml")
        config.legacy_config_paths = list
        try:
            fn(Path(tmp))
        finally:
            config.legacy_config_paths = original_legacy
            if original_env is None:
                os.environ.pop(config.CONFIG_PATH_ENV, None)
            else:
                os.environ[config.CONFIG_PATH_ENV] = original_env


@contextmanager
def base_library(path: Path | None):
    """Pretend a base library is present at ``path`` (or absent).

    Stubs the whole lookup: how a base is FOUND is stablemate_core's business and is
    tested in core/tests/test_discovery.py. What matters here is only how farrier stacks
    the result against an overlay.
    """
    original = layers.base_library_dir
    layers.base_library_dir = lambda: path
    try:
        yield
    finally:
        layers.base_library_dir = original


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
        assert config.config_path().exists()
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


# Base-library resolution order moved to stablemate_core; its test lives in
# core/tests/test_discovery.py.

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
    test_overlay_shadows_base()
    test_unknown_pack_names_the_layers()
    print("\nall config-resolution tests passed")
