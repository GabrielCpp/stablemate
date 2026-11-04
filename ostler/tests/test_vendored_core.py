"""ostler carries `stablemate_core` the way workhorse and farrier already do."""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDOR_SCRIPT = REPO_ROOT / "scripts" / "vendor_core.py"
CORE = REPO_ROOT / "core" / "stablemate_core"
OSTLER_VENDOR = REPO_ROOT / "ostler" / "ostler" / "_vendor" / "stablemate_core"

VENDORING_TOOLS = ("farrier", "workhorse", "ostler", "paddock", "saddlebag")


def _vendor_script() -> ModuleType:
    """`scripts/vendor_core.py` as a module, so its destination list can be read."""
    assert VENDOR_SCRIPT.exists(), f"the vendor script is missing: {VENDOR_SCRIPT}"
    spec = importlib.util.spec_from_file_location("stablemate_vendor_core", VENDOR_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    destinations = [Path(d) for d in _vendor_script().DESTINATIONS]

    assert OSTLER_VENDOR in destinations, (
        "ostler's vendor destination is not listed in scripts/vendor_core.py, so "
        f"`make vendor` never writes it and `make check-vendor` never guards it: {destinations}"
    )
    for tool in VENDORING_TOOLS:
        assert any(tool in d.parts for d in destinations), f"no vendored copy for {tool}"


def test_the_committed_path_is_a_symlink_resolving_to_core():
    """A checkout holds a link to `core/stablemate_core`, not a second copy of it."""
    assert OSTLER_VENDOR.is_symlink(), (
        f"{OSTLER_VENDOR.relative_to(REPO_ROOT)} is not a symlink — run `make vendor`"
    )
    assert OSTLER_VENDOR.resolve() == CORE.resolve()


def test_check_vendor_passes_and_covers_every_copy():
    """`make check-vendor` is green over one copy per vendoring tool."""
    destinations = _vendor_script().DESTINATIONS
    assert len(destinations) == len(VENDORING_TOOLS), (
        f"expected one vendored copy per shipping tool {VENDORING_TOOLS}: {destinations}"
    )

    done = _run(sys.executable, str(VENDOR_SCRIPT), "--check")
    assert done.returncode == 0, done.stderr or done.stdout


def _fake_repo(root: Path) -> Path:
    core = root / "core" / "stablemate_core"
    core.mkdir(parents=True)
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "config.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def test_vendoring_a_repo_links_every_tool_and_passes_check(tmp_path):
    """Default mode builds the links and digests that `--check` then accepts."""
    repo = _fake_repo(tmp_path)

    wrote = _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo))
    assert wrote.returncode == 0, wrote.stderr or wrote.stdout
    for tool in VENDORING_TOOLS:
        link = repo / tool / tool / "_vendor" / "stablemate_core"
        assert link.is_symlink() and link.resolve() == (repo / "core" / "stablemate_core").resolve()

    checked = _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo), "--check")
    assert checked.returncode == 0, checked.stderr or checked.stdout


def test_a_stale_digest_fails_check_naming_the_tool(tmp_path):
    """A core change without `make vendor` is the change that ships to nobody."""
    repo = _fake_repo(tmp_path)
    assert _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo)).returncode == 0

    (repo / "core" / "stablemate_core" / "config.py").write_text("VALUE = 2\n", encoding="utf-8")

    done = _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo), "--check")
    assert done.returncode != 0
    for tool in VENDORING_TOOLS:
        assert f"{tool}: " in done.stderr and "stale" in done.stderr
    assert "make vendor" in done.stderr


def test_a_missing_or_misdirected_link_fails_check(tmp_path):
    """A real directory or a link elsewhere is not the shared package."""
    repo = _fake_repo(tmp_path)
    assert _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo)).returncode == 0

    farrier = repo / "farrier" / "farrier" / "_vendor" / "stablemate_core"
    farrier.unlink()
    elsewhere = repo / "elsewhere"
    elsewhere.mkdir()
    saddlebag = repo / "saddlebag" / "saddlebag" / "_vendor" / "stablemate_core"
    saddlebag.unlink()
    saddlebag.symlink_to(elsewhere, target_is_directory=True)

    done = _run(sys.executable, str(VENDOR_SCRIPT), "--root", str(repo), "--check")
    assert done.returncode != 0
    assert "farrier: " in done.stderr and "not a symlink" in done.stderr
    assert "saddlebag: " in done.stderr and "does not resolve" in done.stderr


def test_the_built_wheel_ships_real_core_files(tmp_path):
    """A build that stops following the link would ship ostler without core."""
    done = _run("uv", "build", "--package", "ostler", "--wheel", "--out-dir", str(tmp_path))
    assert done.returncode == 0, done.stderr or done.stdout

    (wheel,) = tmp_path.glob("ostler-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    assert "ostler/_vendor/stablemate_core/config.py" in names, names


def test_the_vendored_package_is_importable_under_ostler():
    """`ostler._vendor.stablemate_core` resolves, and resolves *inside* the ostler package."""
    ostler = importlib.import_module("ostler")
    vendored = importlib.import_module("ostler._vendor.stablemate_core")

    assert vendored.__file__ is not None
    inside = [Path(root) for root in ostler.__path__]
    assert any(Path(vendored.__file__).is_relative_to(root) for root in inside), (
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


@pytest.mark.parametrize("requirement", ["platformdirs", "tomlkit"])
def test_pyproject_declares_the_vendored_packages_requirements(requirement: str):
    """`platformdirs>=4` and `tomlkit>=0.13`, floors included."""
    floors = {"platformdirs": 4, "tomlkit": 0}
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
        "the platformdirs/tomlkit floors must be annotated as the vendored package's "
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
