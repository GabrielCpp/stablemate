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
