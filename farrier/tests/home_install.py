"""Setup shared by the tests that run `farrier install --user` against a temporary home."""

from pathlib import Path

import pytest

from farrier.install import main


def configure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    config = tmp_path / "stablemate.toml"
    config.write_text(f"config_version = 1\n\n{body}", encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def run(home: Path, library: Path, *extra: str) -> int:
    return main(["install", "--user", "--home", str(home), "--library", str(library), *extra])


def agent_library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    agents = root / "library" / "agents"
    agents.mkdir(parents=True)
    (root / "packs").mkdir()
    (agents / "lookup.md").write_text(
        '---\ndescription: "Read-only lookup."\nread_only: true\n---\n\nYou answer one question.\n',
        encoding="utf-8",
    )
    (agents / "worker.md").write_text(
        "---\ndescription: Carries out a plan.\n---\n\nYou carry out a plan.\n", encoding="utf-8"
    )
    return root


def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    return path


def install(home: Path, library: Path, config: str, *flags: str) -> int:
    (home.parent / "config.toml").write_text(config, encoding="utf-8")
    return main(["--user", "--home", str(home), "--library", str(library), *flags])


def add_search_server(library: Path) -> None:
    servers = library / "library" / "mcp"
    servers.mkdir()
    (servers / "search.yml").write_text("command: ostler\nargs: [mcp]\n", encoding="utf-8")


def add_skill_pair(library: Path) -> None:
    skills = library / "library" / "skills" / "general"
    skills.mkdir(parents=True)
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: Review.\n---\n\nReview.\n", encoding="utf-8"
    )
    (skills / "ship.md").write_text(
        "---\nname: ship\ndescription: Ship.\n---\n\nThen {{ skill_command('review') }}.\n",
        encoding="utf-8",
    )


def add_settings(library: Path, body: str) -> None:
    settings = library / "library" / "settings"
    settings.mkdir(parents=True)
    (settings / "prefs.json").write_text(body, encoding="utf-8")


def seed(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path
