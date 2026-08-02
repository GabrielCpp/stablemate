"""Generation-copy installs: the bind is copied, never imported.

The property under test is not "a copy happened" — it is that **a running process
never imports the directory the operator is editing**. That is what a plain
`uv tool install --editable /mnt/<pkg>-src` gets wrong: a save half-way through a
multi-file change lands directly in what a live process imports, and a wrong edit has
nothing to fall back to.

So the tests here are about the two guarantees that buys: a generation dir is written
once and never mutated, and a refresh that fails leaves the previous generation
installed rather than nothing.

`uv` is never spawned — `_run` is the module's single spawn point and therefore its
single seam.

    ./.venv/bin/python -m pytest tests/test_livesource.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import livesource


def _mount(tmp_path: Path, **files: str) -> Path:
    """A stand-in for the read-only host bind."""
    src = tmp_path / "mnt" / "pkg-src"
    src.mkdir(parents=True)
    for name, text in (files or {"pyproject.toml": "[project]\nname='pkg'\n"}).items():
        (src / name).write_text(text)
    return src


def _source(tmp_path: Path, mount: Path, **kw) -> livesource.LiveSource:
    return livesource.LiveSource(
        name="pkg", mount=mount, root=tmp_path / "live" / "pkg", **kw
    )


class _Uv:
    """A recording stand-in for the uv invocation, with a settable exit code."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str], bin_dir: Path) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        return subprocess.CompletedProcess(cmd, self.returncode, b"", b"")


# --------------------------------------------------------------------------- #
# Staging
# --------------------------------------------------------------------------- #


def test_a_generation_is_a_copy_of_the_bind_not_the_bind(tmp_path: Path):
    mount = _mount(tmp_path, **{"mod.py": "VERSION = 1\n"})
    gen = livesource.stage(_source(tmp_path, mount))

    assert gen is not None
    assert (gen / "mod.py").read_text() == "VERSION = 1\n"
    assert gen.resolve() != mount.resolve()


def test_an_edit_to_the_bind_does_not_reach_an_existing_generation(tmp_path: Path):
    """The whole point: what a running process imports is immune to the save the
    operator is making right now."""
    mount = _mount(tmp_path, **{"mod.py": "VERSION = 1\n"})
    gen = livesource.stage(_source(tmp_path, mount))
    assert gen is not None

    (mount / "mod.py").write_text("VERSION = 2  # half-typed\n")
    assert (gen / "mod.py").read_text() == "VERSION = 1\n"


def test_each_stage_is_a_new_directory_so_nothing_is_mutated_in_place(tmp_path: Path):
    mount = _mount(tmp_path)
    source = _source(tmp_path, mount)

    first = livesource.stage(source)
    second = livesource.stage(source)

    assert first is not None and second is not None
    assert first != second
    assert first.exists() and second.exists()
    # Chronological order is lexical order, which is what makes generations() a sort.
    assert [p.name for p in livesource.generations(source.root)] == ["0001", "0002"]


def test_no_mount_stages_nothing_and_is_not_an_error(tmp_path: Path):
    """A container launched without the bind simply has no live source."""
    source = _source(tmp_path, tmp_path / "absent")
    assert livesource.stage(source) is None
    assert livesource.refresh(source, tmp_path / "bin") is None


def test_the_expensive_and_useless_directories_are_not_copied(tmp_path: Path):
    """`.venv` and `node_modules` are rebuilt by the install; `.git` can dwarf the
    source; foreign bytecode is worse than useless."""
    mount = _mount(tmp_path)
    for junk in (".git", ".venv", "node_modules", "__pycache__"):
        (mount / junk).mkdir()
        (mount / junk / "big").write_text("x")

    gen = livesource.stage(_source(tmp_path, mount))
    assert gen is not None
    for junk in (".git", ".venv", "node_modules", "__pycache__"):
        assert not (gen / junk).exists(), junk


# --------------------------------------------------------------------------- #
# Installing
# --------------------------------------------------------------------------- #


def test_install_points_uv_at_the_copy_never_at_the_bind(tmp_path: Path, monkeypatch):
    mount = _mount(tmp_path)
    source = _source(tmp_path, mount)
    uv = _Uv()
    monkeypatch.setattr(livesource, "_run", uv)

    gen = livesource.refresh(source, tmp_path / "bin")

    assert gen is not None
    (cmd,) = uv.calls
    assert "--editable" in cmd
    assert cmd[cmd.index("--editable") + 1] == str(gen)
    assert str(mount) not in cmd


def test_extra_local_packages_are_installed_alongside(tmp_path: Path, monkeypatch):
    """A package that must build against THIS image's engine, not a released one."""
    engine = tmp_path / "app" / "workhorse"
    source = _source(tmp_path, _mount(tmp_path), with_editable=(engine,))
    uv = _Uv()
    monkeypatch.setattr(livesource, "_run", uv)

    livesource.refresh(source, tmp_path / "bin")

    (cmd,) = uv.calls
    assert cmd[cmd.index("--with-editable") + 1] == str(engine)


def test_a_failed_install_leaves_the_previous_generation_in_place(tmp_path: Path, monkeypatch):
    """A bad edit costs a restart, not the observer."""
    mount = _mount(tmp_path)
    source = _source(tmp_path, mount)
    uv = _Uv()
    monkeypatch.setattr(livesource, "_run", uv)

    good = livesource.refresh(source, tmp_path / "bin")
    assert good is not None

    uv.returncode = 1
    assert livesource.refresh(source, tmp_path / "bin") is None

    # The good generation survives — something is still running out of it — and the
    # failed copy is gone rather than left to make the next number skip.
    assert good.exists()
    assert [p.name for p in livesource.generations(source.root)] == [good.name]


def test_uv_missing_entirely_is_reported_not_raised(tmp_path: Path, monkeypatch):
    def boom(cmd, bin_dir):
        raise OSError("no uv")

    monkeypatch.setattr(livesource, "_run", boom)
    assert livesource.refresh(_source(tmp_path, _mount(tmp_path)), tmp_path / "bin") is None


# --------------------------------------------------------------------------- #
# Pruning
# --------------------------------------------------------------------------- #


def test_the_previous_generation_survives_a_refresh(tmp_path: Path, monkeypatch):
    """Deleting the directory a live process is importing from is exactly the
    failure this module exists to avoid, so the prune keeps more than one."""
    source = _source(tmp_path, _mount(tmp_path))
    monkeypatch.setattr(livesource, "_run", _Uv())

    installed: list[Path] = []
    for _ in range(4):
        generation = livesource.refresh(source, tmp_path / "bin")
        assert generation is not None
        installed.append(generation)

    surviving = [p.name for p in livesource.generations(source.root)]
    assert surviving == [installed[-2].name, installed[-1].name]
    assert len(surviving) == livesource.KEEP_GENERATIONS
