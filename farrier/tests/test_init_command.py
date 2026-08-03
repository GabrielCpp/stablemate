"""farrier init — the starter agents.yml, and the bare-invocation help it pairs with.

`init` is the only command that runs *before* a repo is configured, so it must work
with no library on the machine, and it must never quietly replace a config someone
already wrote.
"""

from pathlib import Path

import pytest
import yaml

from farrier.install import main


def run(argv: list[str]) -> int:
    return main(argv)


def test_init_writes_a_config_the_installer_can_read(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    config = yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))
    assert config["repo"]["name"] == "acme"
    assert config["agents"] == {"claude": True}
    # Present but empty: the selection is the one thing the operator has to fill in,
    # and an absent key would read as "farrier decides".
    assert config["packs"] == []


def test_init_needs_no_library_configured(tmp_path: Path, monkeypatch) -> None:
    """No layer resolution, no base-library fetch — just a file.

    A fresh machine has neither, and `farrier config set-library` is a step someone
    takes *after* they have a repo to point it at.
    """
    # A library path that isn't there; the suite's autouse fixtures already ensure
    # there is no base library to fall back on either.
    monkeypatch.setenv("FARRIER_LIBRARY_DIR", str(tmp_path / "does-not-exist"))
    repo = tmp_path / "globex"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0
    assert (repo / "agents.yml").is_file()


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


def test_init_quotes_a_directory_name_yaml_would_read_as_something_else(
    tmp_path: Path,
) -> None:
    """A repo called `no` is a string, not `False`.

    The name becomes the prefix on every installed skill, so a directory whose bare
    name YAML resolves to a bool or an int has to survive the round trip.
    """
    repo = tmp_path / "no"
    repo.mkdir()

    assert run(["init", "--repo", str(repo)]) == 0

    config = yaml.safe_load((repo / "agents.yml").read_text(encoding="utf-8"))
    assert config["repo"]["name"] == "no"


def test_bare_farrier_prints_help_rather_than_installing(capsys) -> None:
    """`farrier` with no arguments used to mean `farrier install --repo .`.

    Rendering every adapter file into whatever directory the shell happens to be in
    is not a default worth having; the verb listing is what a bare invocation is
    asking for. Reaching install would raise here — there is no agents.yml in cwd.
    """
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
        # No agents.yml: install fails, which is proof it was install that ran.
        run(["--repo", str(repo)])
