"""`farrier config get KEY` and `farrier config set KEY=VALUE`: one machine-config key, checked against the schema."""

import io
import tomllib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from farrier import cli


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.toml"
    path.write_text('# kept\nconfig_version = 2\ndefault_cli = "claude"\n\n[profiles.claude]\ncli = "claude"\n')
    monkeypatch.delenv("STABLEMATE_CONFIG", raising=False)
    return path


def _run(config: Path, *argv: str) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["config", "--config", str(config), *argv])
    return out.getvalue()


def _fails(config: Path, *argv: str) -> str:
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as exit_info:
        cli.main(["config", "--config", str(config), *argv])
    return str(exit_info.value.code)


def test_set_writes_a_nested_key_and_keeps_the_comments(config: Path):
    _run(config, "set", "profiles.claude.powers.high.model=opus")
    _run(config, "set", "profiles.claude.powers.high.timeout_scale=1.5")

    text = config.read_text()
    assert "# kept" in text
    assert tomllib.loads(text)["profiles"]["claude"]["powers"]["high"] == {"model": "opus", "timeout_scale": 1.5}


def test_get_reads_back_what_set_wrote(config: Path):
    _run(config, "set", "default_cli=codex")

    assert _run(config, "get", "default_cli") == "codex\n"


def test_get_prints_a_table_under_its_full_path(config: Path):
    """A header without its path would not paste back into the file."""
    _run(config, "set", "profiles.claude.powers.high.model=opus")

    assert "[profiles.claude.powers.high]\nmodel = \"opus\"" in _run(config, "get", "profiles.claude.powers")


def test_set_accepts_a_whole_table_under_a_name_the_user_picks(config: Path):
    _run(config, "set", 'profiles.codex={ cli = "codex" }')

    assert _run(config, "get", "profiles.codex.cli") == "codex\n"


def test_set_accepts_a_free_key_of_a_string_table(config: Path):
    _run(config, "set", "cli.claude.env.EXAMPLE_FLAG=1")

    assert tomllib.loads(config.read_text())["cli"]["claude"]["env"] == {"EXAMPLE_FLAG": "1"}


def test_an_undeclared_key_is_refused_with_the_closest_keys(config: Path):
    """Every tool would ignore a misspelt key, so writing one would look like it worked."""
    before = config.read_text()

    assert "`default_cli`" in _fails(config, "set", "default_clii=codex")
    assert config.read_text() == before


def test_a_value_the_schema_rejects_leaves_the_file_unchanged(config: Path):
    before = config.read_text()

    assert "saddlebag.backend" in _fails(config, "set", "saddlebag.backend=nope")
    assert config.read_text() == before


def test_a_value_the_schema_would_read_as_unset_is_refused(config: Path):
    """timeout_scale drops a string on load; the setter must not report a write no tool will see."""
    before = config.read_text()

    assert "would read it as None" in _fails(config, "set", 'profiles.claude.powers.high.timeout_scale="fast"')
    assert config.read_text() == before


def test_a_non_string_key_needs_a_toml_value(config: Path):
    assert "not a TOML value" in _fails(config, "set", "profiles.claude.powers.high.timeout_scale=fast")


def test_set_without_an_equals_sign_is_refused(config: Path):
    assert "KEY=VALUE" in _fails(config, "set", "default_cli")


def test_get_of_a_declared_key_with_no_value_says_so(config: Path):
    assert "not set" in _fails(config, "get", "worktree_dir")


def test_bare_config_prints_every_action(config: Path):
    """A bare group command used to end in an argparse error that named no action."""
    text = _run(config)

    for action in ("get", "set", "show", "reference"):
        assert f"    {action} " in text
