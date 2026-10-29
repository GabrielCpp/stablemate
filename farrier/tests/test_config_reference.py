"""`farrier config reference`: the machine config's keys, printed from the schema."""

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from farrier import cli
from farrier._vendor.stablemate_core.schema import HomeConfig, Manifest, reference_rows


def _run(*argv: str) -> str:
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["config", "reference", *argv])
    return out.getvalue()


def test_the_default_prints_every_declared_key():
    """A key the command omits is a key no reader learns exists."""
    text = _run()

    for row in reference_rows(HomeConfig):
        assert f"### `{row.path}`" in text


def test_the_default_prints_every_manifest_key_too():
    text = _run()

    for row in reference_rows(Manifest):
        assert f"### `{row.path}`" in text


def test_file_home_prints_only_the_machine_config():
    """The --file seam must select the machine config, not drop it."""
    text = _run("--file", "home")

    assert "### `agents`" not in text
    assert text in _run()


def test_file_manifest_prints_every_key_with_its_default_and_example():
    text = _run("--file", "manifest")

    for row in reference_rows(Manifest):
        assert f"### `{row.path}`" in text
    assert "### `workflow.githubTokenEnv`" in text
    assert "- legacy:" in text
    assert "- example:" in text
    assert "[home]" not in text
    assert "Machine config" not in text


def test_an_unknown_file_is_rejected():
    """A misspelt --file must fail loudly rather than print an empty reference."""
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        cli.main(["config", "reference", "--file", "nope"])
