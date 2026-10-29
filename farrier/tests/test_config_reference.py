"""`farrier config reference`: the shared config files' keys, printed from the schema."""

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


def _entries(text: str) -> set[str]:
    return {line[5:-1] for line in text.splitlines() if line.startswith("### `")}


def test_the_default_lists_every_key_of_both_files_on_one_line_each():
    """A key the index omits is a key no reader learns exists."""
    lines = _run().splitlines()

    for row in [*reference_rows(HomeConfig), *reference_rows(Manifest)]:
        assert any(line.startswith(f"- `{row.path}` (") for line in lines), row.path
    assert not any(line.startswith("### ") for line in lines)


def test_the_index_is_a_fraction_of_the_full_reference():
    """The index exists so an agent can scan every option without reading every entry."""
    assert len(_run()) < len(_run("--full")) * 0.6


def test_full_prints_every_entry_of_both_files():
    text = _run("--full")

    assert _entries(text) == {row.path for row in [*reference_rows(HomeConfig), *reference_rows(Manifest)]}


def test_a_key_prints_its_entry_and_the_keys_under_it_only():
    text = _run("workflow")

    assert _entries(text) == {row.path for row in reference_rows(Manifest) if row.path.split(".")[0] == "workflow"}
    assert "Machine config" not in text


def test_a_key_matches_a_name_the_user_picked_against_its_placeholder():
    """A reader types the profile name from their own file, not the placeholder the schema declares."""
    text = _run("profiles.claude.powers")

    assert "### `profiles.<name>.powers`" in text
    assert all(path.startswith("profiles.<name>.powers") for path in _entries(text))


def test_a_key_matches_whole_segments_only():
    """`workflow.githubToken` is a typo of a key, not a prefix of one."""
    err = io.StringIO()
    with redirect_stderr(err), pytest.raises(SystemExit) as exit_info:
        cli.main(["config", "reference", "workflow.githubToken"])

    assert "workflow.githubTokenEnv" in str(exit_info.value.code)


def test_file_home_prints_only_the_machine_config():
    """The --file seam must select the machine config, not drop it."""
    text = _run("--file", "home", "--full")

    assert "### `agents`" not in text
    assert "Machine config" in text


def test_file_manifest_prints_every_key_with_its_default_and_example():
    text = _run("--file", "manifest", "--full")

    assert _entries(text) == {row.path for row in reference_rows(Manifest)}
    assert "- legacy:" in text
    assert "- example:" in text
    assert "Machine config" not in text


def test_an_unknown_file_is_rejected():
    """A misspelt --file must fail loudly rather than print an empty reference."""
    with redirect_stderr(io.StringIO()), pytest.raises(SystemExit):
        cli.main(["config", "reference", "--file", "nope"])
