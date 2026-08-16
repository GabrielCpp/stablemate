"""Standalone tests for `farrier config --config` and `config show --profile`.

Reading a profile is what the operator does *before* launching a run on it — "what
does `cheap` actually map high to" — and a `cat` of the TOML answers that only if they
can hold three levels of table in their head. So `show --profile` narrows the config
the same way a run does and flattens the result to one dotted line per leaf.

`--config` is the other half: it names the file, so the same question can be asked of
a config that is not this machine's home one.

Run directly (no pytest required):
    uv run python tests/test_config_profiles_cli.py
"""

import io
import os
import tempfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from farrier import cli
from farrier._vendor.stablemate_core import config

CONFIG = """\
default_cli = "claude"

[power.high.claude]
model = "opus"

[profiles.cheap]
default_cli = "opencode"

[profiles.cheap.power.high.claude]
model = "haiku"
effort = "low"

[profiles.cheap.default.opencode]
model = "qwen"
"""


@contextmanager
def written(text: str = CONFIG):
    """A config file on disk, with this process's own $STABLEMATE_CONFIG restored after.

    `_run_config` writes the resolved path into the environment — that is the mechanism
    under test — so a test that did not put the old value back would hand every later
    test in the same process this temporary file.
    """
    before = os.environ.get(config.CONFIG_PATH_ENV)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.toml"
        path.write_text(text)
        try:
            yield path
        finally:
            if before is None:
                os.environ.pop(config.CONFIG_PATH_ENV, None)
            else:
                os.environ[config.CONFIG_PATH_ENV] = before


def _show(*argv: str) -> list[str]:
    out = io.StringIO()
    with redirect_stdout(out):
        assert cli.main(["config", *argv]) == 0
    return out.getvalue().splitlines()


def test_the_config_flag_reads_the_file_it_names():
    """Not the home config, and without the caller having to export anything: the
    operator comparing two config files is the case this exists for."""
    with written() as path:
        lines = _show("--config", str(path), "show")

    assert "default_cli=claude" in lines


def test_a_profile_is_shown_flattened_to_dotted_keys():
    """One line per leaf, which is what makes two profiles diffable against each other.
    A TOML echo would only reproduce the file the operator already has."""
    with written() as path:
        lines = _show("--config", str(path), "show", "--profile", "cheap")

    assert lines == [
        "default_cli=opencode",
        "power.high.claude.model=haiku",
        "power.high.claude.effort=low",
        "default.opencode.model=qwen",
    ]


def test_the_profile_replaces_the_top_level_rather_than_layering_over_it():
    """The property the whole feature rests on, asserted where an operator can see it:
    `[power.high.claude] model = "opus"` is above the profile in the same file, and the
    profile's own entry is the *whole* answer rather than an override on top of it."""
    with written() as path:
        lines = _show("--config", str(path), "show", "--profile", "cheap")

    assert not any(line.endswith("=opus") for line in lines), lines


def test_a_key_is_looked_up_by_its_dotted_path_within_the_profile():
    """`show <key>` already means "print one bare value"; inside a profile the keys are
    the dotted ones, so this is the same verb rather than a second spelling."""
    with written() as path:
        lines = _show("--config", str(path), "show", "power.high.claude.model",
                      "--profile", "cheap")

    assert lines == ["haiku"]


def test_an_unknown_profile_exits_cleanly_and_lists_the_ones_there_are():
    """A misspelling is the common case, and a traceback would neither name the file
    nor say what it could have meant."""
    with written() as path:
        try:
            _show("--config", str(path), "show", "--profile", "chaep")
        except SystemExit as exc:
            assert "chaep" in str(exc) and "cheap" in str(exc), exc
            return
    raise AssertionError("expected SystemExit for a profile the config does not define")


def test_a_key_the_profile_does_not_set_says_which_profile_it_looked_in():
    """The top-level config may well have it, so "not set" alone reads as a bug in the
    tool rather than as a gap in the profile."""
    with written() as path:
        try:
            _show("--config", str(path), "show", "power.high.codex.model",
                  "--profile", "cheap")
        except SystemExit as exc:
            assert "profile 'cheap'" in str(exc), exc
            return
    raise AssertionError("expected SystemExit for a key the profile does not set")


def test_a_config_with_no_profiles_at_all_still_shows_the_top_level():
    with written('default_cli = "codex"\n') as path:
        assert _show("--config", str(path), "show") == ["default_cli=codex"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
