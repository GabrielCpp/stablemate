"""Standalone tests for farrier's library-directory resolution and config CLI.

Run directly (no pytest required):
    uv run python tests/test_config_resolution.py
"""

import os
import tempfile
from pathlib import Path

from farrier import install


def make_library(root: Path) -> Path:
    """Create a minimal but valid library directory (library/ + packs/)."""
    (root / "library").mkdir(parents=True)
    (root / "packs").mkdir()
    return root


def with_temp_config(fn):
    """Run fn with install.CONFIG_PATH pointed at a throwaway file."""
    original = install.CONFIG_PATH
    with tempfile.TemporaryDirectory() as tmp:
        install.CONFIG_PATH = Path(tmp) / "config.toml"
        try:
            fn(Path(tmp))
        finally:
            install.CONFIG_PATH = original


def clear_env():
    os.environ.pop("FARRIER_LIBRARY_DIR", None)


def test_is_library_dir():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_library(Path(tmp) / "agents")
        assert install.is_library_dir(root)
        assert not install.is_library_dir(Path(tmp))
    print("ok: is_library_dir")


def test_write_then_read_config():
    def body(tmp: Path):
        lib = make_library(tmp / "agents")
        install.write_library_dir(lib)
        assert install.CONFIG_PATH.exists()
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


def test_unresolved_errors_with_hint():
    def body(tmp: Path):
        clear_env()
        try:
            install.resolve_library_dir(None)
        except SystemExit as exc:
            assert "config set-library" in str(exc)
            return
        raise AssertionError("expected SystemExit when nothing is configured")
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
            assert "library/ and packs/" in str(exc)
            return
        raise AssertionError("expected SystemExit for a non-library path")
    with_temp_config(body)
    print("ok: bad library path errors")


def test_set_library_globals():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_library(Path(tmp) / "agents")
        install.set_library_globals(root)
        assert install.LIBRARY == root / "library"
        assert install.PACKS == root / "packs"
        assert install.SKILLS == root / "library" / "skills"
        assert install.WORKFLOWS == root / "workflows"
    print("ok: set_library_globals")


if __name__ == "__main__":
    test_is_library_dir()
    test_write_then_read_config()
    test_precedence_flag_over_env_over_config()
    test_unresolved_errors_with_hint()
    test_bad_library_path_errors()
    test_set_library_globals()
    print("\nall config-resolution tests passed")
