"""farrier init — the starter agents.yml, and the bare-invocation help it pairs with."""

import io
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from farrier.init import USER_LIBRARY_PROPOSAL
from farrier.install import main
from farrier.layers import BASE_DIR_ENV

BASE_LIBRARY = Path(__file__).resolve().parents[2] / "base-library"


def run(argv: list[str]) -> int:
    return main(argv)


def test_init_writes_a_config_the_installer_can_read(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    config = yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))
    assert config["agents"] == {"claude": True}
    assert config["packs"] == []


def test_init_needs_no_library_configured(tmp_path: Path, monkeypatch) -> None:
    """No layer resolution, no base-library fetch — just a file."""
    monkeypatch.setenv("FARRIER_LIBRARY_DIR", str(tmp_path / "does-not-exist"))
    repo = tmp_path / "globex"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0
    assert (repo / "agents.yml").is_file()


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def answer(monkeypatch, reply: str) -> None:
    monkeypatch.setattr(sys, "stdin", _Terminal())
    monkeypatch.setattr("builtins.input", lambda _question: reply)


def test_a_yes_writes_the_user_library_and_installs_it(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.toml"
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    monkeypatch.setenv(BASE_DIR_ENV, str(BASE_LIBRARY))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    answer(monkeypatch, "y")
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    written = tomllib.loads(config.read_text(encoding="utf-8"))
    assert written["user_library"]["claude"] == {"packs": ["general", "stablemate"]}
    assert any((tmp_path / "home" / ".claude" / "skills").iterdir())


def test_a_no_leaves_the_home_alone_and_prints_the_proposal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config.toml"
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    answer(monkeypatch, "")
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    assert not config.exists()
    assert USER_LIBRARY_PROPOSAL in capsys.readouterr().out


def test_init_never_asks_without_a_terminal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO())

    def refuse(_question: str) -> str:
        raise AssertionError("init asked a question with no terminal attached")

    monkeypatch.setattr("builtins.input", refuse)
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0


def test_init_proposes_a_user_library_when_none_is_configured(
    tmp_path: Path, capsys
) -> None:
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    assert USER_LIBRARY_PROPOSAL in capsys.readouterr().out


def test_init_proposes_nothing_once_a_user_library_exists(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'config_version = 1\n\n[user_library.claude]\npacks = ["general"]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    assert "user_library" not in capsys.readouterr().out


def test_the_proposed_user_library_installs_from_the_base_library(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        f"config_version = 1\n\n{USER_LIBRARY_PROPOSAL}", encoding="utf-8"
    )
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))
    monkeypatch.setenv(BASE_DIR_ENV, str(BASE_LIBRARY))
    home = tmp_path / "home"

    assert run(["install", "--user", "--home", str(home)]) == 0

    assert any((home / ".claude" / "skills").iterdir())


def test_install_after_init_succeeds_and_says_nothing_about_skills(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv(BASE_DIR_ENV, str(BASE_LIBRARY))
    repo = tmp_path / "acme"
    repo.mkdir()
    assert run(["init", "--repo", str(repo)]) == 0
    capsys.readouterr()

    assert run(["install", "--repo", str(repo)]) == 0

    out = capsys.readouterr().out
    assert "skill" not in out
    assert not (repo / ".claude" / "skills").exists()


def test_init_refuses_to_overwrite_an_existing_config(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    repo.mkdir()
    (repo / "agents.yml").write_text("packs: [go]\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        run(["init", "--repo", str(repo)])

    assert "already exists" in str(excinfo.value)
    assert (repo / "agents.yml").read_text(encoding="utf-8") == "packs: [go]\n"


def test_init_force_replaces_an_existing_config(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    repo.mkdir()
    (repo / "agents.yml").write_text("packs: [go]\n", encoding="utf-8")

    assert run(["init", "--repo", str(repo), "--force"]) == 0

    config = yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))
    assert config["packs"] == []


def test_init_rejects_a_repo_path_that_is_not_a_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"

    with pytest.raises(SystemExit) as excinfo:
        run(["init", "--repo", str(missing)])

    assert "not a directory" in str(excinfo.value)


def test_init_sets_no_repo_name(tmp_path: Path) -> None:
    """The name is the directory's, so the starter config does not restate it."""
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    text = (repo / "agents.yml").read_text(encoding="utf-8")
    assert yaml.safe_load(text).get("repo") is None
    assert "acme-db" in text


def test_bare_farrier_prints_help_rather_than_installing(capsys) -> None:
    """`farrier` with no arguments used to mean `farrier install --repo .`."""
    assert run([]) == 0

    out = capsys.readouterr().out
    assert "usage: farrier" in out
    assert "init" in out
    assert "scaffold" in out


def test_naming_a_flag_first_still_means_install(tmp_path: Path) -> None:
    """`farrier --repo .` keeps working — the implicit `install` is unchanged."""
    repo = tmp_path / "acme"
    repo.mkdir()

    with pytest.raises(SystemExit):
        run(["--repo", str(repo)])
