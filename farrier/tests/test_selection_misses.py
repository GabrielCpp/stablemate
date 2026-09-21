"""A selection entry that names nothing must fail loudly, not vanish."""

from pathlib import Path

import pytest

from farrier.install import main


def make_library(tmp_path: Path) -> Path:
    library = tmp_path / "agents"
    skills = library / "library" / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "real-skill.md").write_text(
        "---\nname: real-skill\ndescription: A real skill.\n---\n\nBody.\n", encoding="utf-8"
    )
    (library / "library" / "prompts" / "demo").mkdir(parents=True)
    (library / "library" / "prompts" / "demo" / "real-prompt.md").write_text(
        "---\nname: real-prompt\ndescription: A real prompt.\n---\n\nBody.\n", encoding="utf-8"
    )
    (library / "library" / "roots").mkdir(parents=True)
    (library / "library" / "roots" / "real-root.md").write_text("# Root\n", encoding="utf-8")
    (library / "packs").mkdir()
    (library / "scaffolds").mkdir()
    return library


def write_config(repo: Path, body: str) -> None:
    repo.mkdir(exist_ok=True)
    (repo / "agents.yml").write_text(body, encoding="utf-8")


def install(repo: Path, library: Path) -> int:
    return main(["install", "--repo", str(repo), "--library", str(library)])


BASE = """\
agents:
  claude: true
"""


def test_unknown_skill_fails_loudly(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/real-skill\n  - demo/typo-skill\n")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    message = str(excinfo.value)
    assert "unknown skill in agents.yml `skills:`" in message
    assert "demo/typo-skill" in message
    assert "did you mean: demo/real-skill?" in message
    assert "Available skills (1):" in message
    assert "Searched these library layers:" in message
    assert "farrier config set-library" in message


def test_unknown_prompt_fails_loudly(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/real-skill\nprompts:\n  - demo/nope\n")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    assert "prompts" in str(excinfo.value) and "nope" in str(excinfo.value)


def test_every_miss_is_reported_in_one_run(tmp_path: Path) -> None:
    """Collect before raising, so the operator fixes them all at once rather than rediscovering the next typo on each re-run."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(
        repo,
        BASE + "skills:\n  - demo/typo-one\n  - demo/typo-two\nprompts:\n  - demo/typo-three\n",
    )

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    message = str(excinfo.value)
    for name in ("typo-one", "typo-two", "typo-three"):
        assert name in message, f"{name} was not reported"


def test_glob_selecting_nothing_warns_but_proceeds(tmp_path: Path, capsys) -> None:
    """A glob is a filter, and a filter is allowed to match nothing."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/real-skill\n  - demo/nothing-*\n")

    assert install(repo, library) == 0
    out = capsys.readouterr().out
    assert "warning:" in out
    assert "glob 'demo/nothing-*' in agents.yml `skills:` selected nothing" in out


def test_valid_selection_still_installs(tmp_path: Path) -> None:
    """The guard must not reject a correct config — including one selecting by glob."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/*\nprompts:\n  - demo/real-prompt\n")

    assert install(repo, library) == 0
    assert (repo / ".claude" / "skills").is_dir()


def test_unknown_root_fails_loudly(tmp_path: Path) -> None:
    """Roots render only into the copilot adapter, so an unknown one used to be skipped in silence by the `if root_hit is not None` guard."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(
        repo,
        "agents:\n  copilot: true\n"
        "skills:\n  - demo/real-skill\nroots:\n  - ghost-root\n",
    )

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    assert "unknown root" in str(excinfo.value) and "ghost-root" in str(excinfo.value)


def test_unknown_root_fails_even_with_copilot_disabled(tmp_path: Path) -> None:
    """The declaration is wrong regardless of which assistants are enabled."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/real-skill\nroots:\n  - ghost-root\n")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    assert "ghost-root" in str(excinfo.value)


def test_known_root_still_renders(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(
        repo,
        "agents:\n  copilot: true\n"
        "skills:\n  - demo/real-skill\nroots:\n  - real-root\n",
    )

    assert install(repo, library) == 0
    assert (repo / ".github" / "copilot-instructions.md").is_file()



def test_unknown_pack_is_verbose(tmp_path: Path) -> None:
    library = make_library(tmp_path)
    (library / "packs" / "go.yml").write_text("skills:\n  - demo/real-skill\n", encoding="utf-8")
    repo = tmp_path / "repo"
    write_config(repo, BASE + "packs:\n  - og\n")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    message = str(excinfo.value)
    assert "unknown pack in agents.yml `packs:`" in message
    assert "did you mean: go?" in message
    assert "Available packs (1):" in message
    assert "includes:" in message


def test_empty_catalog_says_the_layer_is_missing_not_the_name(tmp_path: Path) -> None:
    """The failure mode this codebase actually hits: skills and packs live in a private overlay, so a *correct* name still resolves to nothing when no overlay is configured."""
    library = make_library(tmp_path)
    repo = tmp_path / "repo"
    write_config(repo, BASE + "skills:\n  - demo/real-skill\npacks:\n  - go\n")

    with pytest.raises(SystemExit) as excinfo:
        install(repo, library)

    message = str(excinfo.value)
    assert "No packs are available from the current library layers at all" in message
    assert "not configured" in message


def test_suggestions_catch_transpositions_difflib_misses(tmp_path: Path) -> None:
    """difflib's ratio is length-normalized, so a transposition in a short name scores far below any cutoff that is safe on long ones ('og' vs 'go' is 0.5)."""
    from farrier.selection_errors import suggestions

    assert suggestions("og", ["go", "flutter"]) == ["go"]
    assert suggestions("codre", ["coder", "author"])[0] == "coder"
    assert suggestions("Demo/Real_Skill", ["demo/real-skill"]) == ["demo/real-skill"]
    assert suggestions("something-entirely-else", ["go", "flutter"]) == []


def test_suggestions_drop_non_competitive_runners_up(tmp_path: Path) -> None:
    """A shared namespace prefix lifts every sibling over the similarity cutoff, so a plain top-N buries the one right answer under near-ties that are not close at all."""
    from farrier.selection_errors import suggestions

    catalog = [
        "stablemate/ostler",
        "stablemate/groom",
        "stablemate/agent-library",
        "stablemate/workhorse-coder-workflow",
    ]
    assert suggestions("stablemate/ostlr", catalog) == ["stablemate/ostler"]
