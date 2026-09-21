"""ostler carries `stablemate_core` the way workhorse and farrier already do."""

from __future__ import annotations

import filecmp
import importlib
import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_SCRIPT = REPO_ROOT / "scripts" / "vendor_core.py"
CORE = REPO_ROOT / "core" / "stablemate_core"
OSTLER_VENDOR = REPO_ROOT / "ostler" / "ostler" / "_vendor" / "stablemate_core"

VENDORING_TOOLS = ("farrier", "workhorse", "ostler")


def _vendor_script() -> ModuleType:
    """`scripts/vendor_core.py` as a module, so its destination list can be read."""
    assert VENDOR_SCRIPT.exists(), f"the vendor script is missing: {VENDOR_SCRIPT}"
    spec = importlib.util.spec_from_file_location("stablemate_vendor_core", VENDOR_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(root: Path) -> list[Path]:
    """Every file making up a package, relative to its own root, `__pycache__` aside."""
    return sorted(
        p.relative_to(root)
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )


def _run(
    *argv: str, timeout: int = 900, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        list(argv),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        env=env,
    )


def test_the_vendor_script_lists_ostlers_destination():
    """ostler joins workhorse and farrier in `DESTINATIONS` — one copy per shipping tool."""
    destinations = [Path(d).resolve() for d in _vendor_script().DESTINATIONS]

    assert OSTLER_VENDOR.resolve() in destinations, (
        "ostler's vendor destination is not listed in scripts/vendor_core.py, so "
        f"`make vendor` never writes it and `make check-vendor` never guards it: {destinations}"
    )
    for tool in VENDORING_TOOLS:
        assert any(tool in d.parts for d in destinations), f"no vendored copy for {tool}"


def test_the_committed_copy_is_byte_identical_to_core():
    """The copy is in the tree, complete, and the same bytes as `core/stablemate_core`."""
    assert OSTLER_VENDOR.is_dir(), (
        f"no committed copy at {OSTLER_VENDOR.relative_to(REPO_ROOT)} — run `make vendor`"
    )

    want, have = _files(CORE), _files(OSTLER_VENDOR)
    assert have == want, "the vendored copy is missing or has extra files"

    differing = [
        str(p) for p in want if not filecmp.cmp(CORE / p, OSTLER_VENDOR / p, shallow=False)
    ]
    assert not differing, f"vendored copy has drifted from core/stablemate_core: {differing}"


def test_check_vendor_passes_and_covers_all_three_copies():
    """`make check-vendor` is green over three copies."""
    destinations = _vendor_script().DESTINATIONS
    assert len(destinations) == len(VENDORING_TOOLS), (
        f"expected one vendored copy per shipping tool {VENDORING_TOOLS}: {destinations}"
    )

    done = _run(sys.executable, str(VENDOR_SCRIPT), "--check")
    assert done.returncode == 0, done.stderr or done.stdout


def test_the_vendored_package_is_importable_under_ostler():
    """`ostler._vendor.stablemate_core` resolves, and resolves *inside* the ostler package."""
    ostler = importlib.import_module("ostler")
    vendored = importlib.import_module("ostler._vendor.stablemate_core")

    assert vendored.__file__ is not None
    inside = [Path(root).resolve() for root in ostler.__path__]
    assert any(Path(vendored.__file__).resolve().is_relative_to(root) for root in inside), (
        "the vendored package must live under the ostler package, or the wheel ships without it"
    )


def test_the_cache_directory_resolver_is_reachable_from_ostler_code(monkeypatch, tmp_path):
    """The shared cache directory can be named from ostler — the whole point of the copy."""
    base_cache = importlib.import_module("ostler._vendor.stablemate_core.base_cache")

    monkeypatch.setenv(base_cache.CACHE_DIR_ENV, str(tmp_path / "elsewhere"))
    assert base_cache.cache_root() == tmp_path / "elsewhere"

    monkeypatch.delenv(base_cache.CACHE_DIR_ENV, raising=False)
    default = base_cache.cache_root()
    assert isinstance(default, Path)
    assert default.name == "stablemate", f"not the shared stablemate cache: {default}"


@pytest.mark.parametrize("requirement", ["platformdirs", "tomli-w"])
def test_pyproject_declares_the_vendored_packages_requirements(requirement: str):
    """`platformdirs>=4` and `tomli-w>=1.0`, floors included."""
    floors = {"platformdirs": 4, "tomli-w": 1}
    pyproject = tomllib.loads((REPO_ROOT / "ostler" / "pyproject.toml").read_text("utf-8"))
    declared = {
        d.split(">=")[0].strip(): d for d in pyproject["project"]["dependencies"]
    }

    assert requirement in declared, (
        f"{requirement} is the vendored package's requirement and must be declared: "
        f"{sorted(declared)}"
    )
    spec = declared[requirement]
    assert ">=" in spec, f"{spec} pins no floor, so an install can resolve a version core predates"
    assert int(spec.split(">=")[1].strip().split(".")[0]) >= floors[requirement], spec


def test_the_requirements_are_annotated_as_the_vendored_packages_own():
    """The same comment farrier and workhorse carry, for the same reason."""
    text = (REPO_ROOT / "ostler" / "pyproject.toml").read_text(encoding="utf-8")
    block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    comments = " ".join(line.strip() for line in block.splitlines() if line.strip().startswith("#"))

    assert "ostler._vendor.stablemate_core" in comments, (
        "the platformdirs/tomli-w floors must be annotated as the vendored package's "
        f"requirements, not ostler's own: {comments!r}"
    )


def test_vendoring_changes_no_ostler_behaviour(tmp_path):
    """A reachable cache directory is not a used one — this commit only makes it nameable."""
    package = REPO_ROOT / "ostler" / "ostler"
    assert OSTLER_VENDOR.is_dir(), f"nothing vendored yet at {OSTLER_VENDOR.relative_to(REPO_ROOT)}"

    fetchers = ("ensure_cached_base", "refresh_cached_base", "remote_commit")
    callers = [
        f"{path.relative_to(package)}: {name}"
        for path in package.rglob("*.py")
        if "_vendor" not in path.relative_to(package).parts
        for name in fetchers
        if name in path.read_text(encoding="utf-8")
    ]
    assert not callers, f"ostler must not fetch the base library: {callers}"

    base_cache = importlib.import_module("ostler._vendor.stablemate_core.base_cache")
    cache_dir = tmp_path / "stablemate-cache"
    done = _run(
        sys.executable,
        "-m",
        "ostler.cli",
        "--help",
        timeout=300,
        env={**os.environ, base_cache.CACHE_DIR_ENV: str(cache_dir)},
    )
    assert done.returncode == 0, done.stderr or done.stdout
    assert not cache_dir.exists(), "running the CLI must not touch the shared cache yet"
