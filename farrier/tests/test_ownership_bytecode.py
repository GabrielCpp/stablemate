"""Interpreter caches inside an owned script directory are build exhaust, not drift."""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_install import configured

from farrier import cli
from farrier.ownership import owned_files


@pytest.fixture
def repo(monkeypatch, tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skill = library / "library" / "skills" / "demo" / "scripted" / "SKILL.md"
    (skill.parent / "scripts").mkdir(parents=True)
    (skill.parent / "scripts" / "helper.py").write_text("print('ok')\n", encoding="utf-8")
    skill.write_text("---\nname: scripted\ndescription: a skill with a script\n---\n\n# Scripted\n", encoding="utf-8")
    (library / "packs").mkdir()
    root = configured(monkeypatch, library, tmp_path, "demo/scripted")
    assert cli.main(["install", "--repo", str(root)]) == 0
    return root


def test_a_bytecode_cache_in_an_owned_script_directory_is_not_owned_and_does_not_drift(repo: Path):
    scripts = next(repo.glob(".*/skills/*/scripts"))
    cache = scripts / "__pycache__"
    cache.mkdir()
    pyc = cache / "helper.cpython-312.pyc"
    pyc.write_bytes(b"\x00")
    stray = scripts / "helper.pyo"
    stray.write_bytes(b"\x00")

    owned = owned_files(scripts.parents[2])

    assert scripts / "helper.py" in owned
    assert pyc not in owned
    assert stray not in owned
    assert cli.main(["install", "--repo", str(repo), "--check"]) == 0
