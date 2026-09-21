"""farrier init — the starter agents.yml, and the bare-invocation help it pairs with."""

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
    assert config["agents"] == {"claude": True}
    assert config["packs"] == ["general", "stablemate"]


def test_init_needs_no_library_configured(tmp_path: Path, monkeypatch) -> None:
    """No layer resolution, no base-library fetch — just a file."""
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
    assert config["packs"] == ["general", "stablemate"]


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
