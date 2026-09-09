"""`farrier hooks list` — the per-stage catalogue of declared hooks.

The verb's question is preventive: an operator wants to know what will run at the
next commit, *before* committing. The answer comes from the selection — not from
disk — so the tests below stub a minimal library and exercise the round trip from
`agents.yml` to the printed catalogue. Drift is `install --check`'s job; surfacing
it here would duplicate a gate.

    ./.venv/bin/python -m pytest tests/test_hooks_list.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier import cli
from farrier.install import set_layers


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A minimal library with one skill that declares a pre-commit hook."""
    root = tmp_path / "agents"
    skill = root / "library" / "skills" / "demo" / "gated" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    scripts = skill.parent / "scripts"
    scripts.mkdir()
    (scripts / "check.py").write_text("print('gate')\n", encoding="utf-8")
    skill.write_text(
        "---\n"
        "name: gated\n"
        "description: a skill that declares a hook\n"
        "hooks:\n"
        "  - stage: pre-commit\n"
        "    run: scripts/check.py\n"
        "---\n\n"
        "# Gated\n\nBody.\n",
        encoding="utf-8",
    )
    (root / "packs").mkdir()
    return root


@pytest.fixture(autouse=True)
def _wire_library(monkeypatch, library: Path):
    """The list verb resolves its library through `cli.resolve_library_dir`,
    which reads the home config rather than the test fixture. Pin the
    resolution to the fixture path so each test sees the library it set up."""
    monkeypatch.setattr(cli, "resolve_library_dir", lambda _cli: library)


def _seed_repo(repo: Path, *, manager: str = "githooks") -> None:
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\n"
        "skills:\n  - demo/gated\n"
        f"hooks:\n  manager: {manager}\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# the catalogue itself
# ---------------------------------------------------------------------------


def test_list_groups_declared_hooks_by_stage(library: Path, tmp_path: Path, capsys):
    """One block per stage, one line per hook, in selection order."""
    set_layers(library)
    repo = tmp_path / "demo"
    repo.mkdir()
    _seed_repo(repo)

    assert cli.main(["hooks", "list", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "pre-commit:" in out
    assert "  demo-gated  scripts/check.py" in out


def test_list_with_no_declared_hooks_prints_none_per_stage(
    library: Path, tmp_path: Path, capsys
):
    """A skill with no `hooks:` block still gets one block per stage, with
    `(none)` under every one — the verb's contract is "every stage", not
    "stages with hooks"."""
    skill = library / "library" / "skills" / "demo" / "ungated" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: ungated\ndescription: no hook here\n---\n\n# Ungated\n",
        encoding="utf-8",
    )
    set_layers(library)
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\n"
        "skills:\n  - demo/ungated\n"
        "hooks:\n  manager: githooks\n",
        encoding="utf-8",
    )

    assert cli.main(["hooks", "list", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "pre-commit:" in out
    assert "  (none)" in out


def test_list_with_manager_none_prints_header_note(
    library: Path, tmp_path: Path, capsys
):
    """`manager: none` is a runtime fact about wiring, not a fact about
    selection: the hooks are still listed, prefixed by the header that names
    the cause so an operator turning the manager back on tomorrow knows what
    will start running."""
    set_layers(library)
    repo = tmp_path / "demo"
    repo.mkdir()
    _seed_repo(repo, manager="none")

    assert cli.main(["hooks", "list", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "manager: none — these hooks are not wired" in out
    assert "  demo-gated  scripts/check.py" in out


# ---------------------------------------------------------------------------
# error and absence paths
# ---------------------------------------------------------------------------


def test_list_with_no_agents_yml_exits_nonzero(tmp_path: Path, capsys):
    """Doctor's precedent: a missing `agents.yml` is a non-zero exit so a
    script that gates on the verb's exit sees the same signal it would see
    from `farrier doctor`."""
    repo = tmp_path / "demo"
    repo.mkdir()

    assert cli.main(["hooks", "list", "--repo", str(repo)]) == 1

    err = capsys.readouterr().err
    assert "no agents.yml" in err


def test_list_with_no_library_prints_hint_and_exits_zero(
    tmp_path: Path, capsys, monkeypatch
):
    """No library is a setup choice, not a failure of this repo: print the
    cause-named hint and exit 0 so the verb stays read-only in the case
    where the operator has not yet configured one."""
    set_layers(None)
    monkeypatch.setattr(cli, "resolve_library_dir", lambda _cli: None)
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\nhooks:\n  manager: githooks\n", encoding="utf-8"
    )

    assert cli.main(["hooks", "list", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "no library available" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))