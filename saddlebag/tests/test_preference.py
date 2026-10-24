"""The standing preference: environment first, then the shared config file."""

from __future__ import annotations

from pathlib import Path

import platformdirs
import pytest

from saddlebag import preference
from saddlebag.preference import Preference
from saddlebag.route import RouteError


def write(path: Path, text: str) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return {"STABLEMATE_CONFIG": str(path)}


def test_the_environment_wins_over_the_file(isolated_config: Path) -> None:
    environ = write(isolated_config, '[saddlebag]\nbackend = "daemon"\n')
    environ["SADDLEBAG_BACKEND"] = "keyring"
    assert preference.read(environ) == Preference("keyring", "SADDLEBAG_BACKEND")


def test_the_file_alone_gives_its_path_as_the_source(isolated_config: Path) -> None:
    environ = write(isolated_config, '[saddlebag]\nbackend = "daemon"\n')
    assert preference.read(environ) == Preference("daemon", str(isolated_config))


def test_no_environment_and_no_file_gives_none(isolated_config: Path) -> None:
    assert preference.read({"STABLEMATE_CONFIG": str(isolated_config)}) is None


@pytest.mark.parametrize("base", ["/Users/x/Library/Application Support/stablemate", "/home/x/.config/stablemate"])
def test_the_default_path_lives_in_the_platform_config_dir(base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platformdirs, "user_config_dir", lambda appname: base)
    assert preference.config_path({}) == Path(base) / "config.toml"


def test_a_bad_value_in_the_file_is_refused(isolated_config: Path) -> None:
    environ = write(isolated_config, '[saddlebag]\nbackend = "bogus"\n')
    with pytest.raises(RouteError, match=r"unknown backend 'bogus' in \[saddlebag\] of .*: expected keyring or daemon"):
        preference.read(environ)


def test_a_bad_value_in_the_environment_keeps_the_existing_message() -> None:
    with pytest.raises(RouteError, match="unknown SADDLEBAG_BACKEND 'bogus': expected keyring or daemon"):
        preference.read({"SADDLEBAG_BACKEND": "bogus"})


def test_unparsable_toml_is_refused(isolated_config: Path) -> None:
    environ = write(isolated_config, "[saddlebag\n")
    with pytest.raises(RouteError, match="cannot read "):
        preference.read(environ)


def test_a_file_without_the_table_gives_none(isolated_config: Path) -> None:
    environ = write(isolated_config, '[other]\nbackend = "daemon"\n')
    assert preference.read(environ) is None
