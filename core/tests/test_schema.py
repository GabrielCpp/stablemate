"""The machine config's schema: every key declared and documented, the reference generated from it, a load that validates."""

from __future__ import annotations

import logging
import types
from typing import Any, Union, get_args, get_origin

import pytest
from pydantic import BaseModel

from stablemate_core import config as cfgmod
from stablemate_core import profiles
from stablemate_core.schema import (
    HomeConfig,
    reference_rows,
    render_reference,
    stray_keys,
)

_FULL = """\
config_version = 2
default_cli = "opencode"
library_dir = "/lib"
base_dir = "/base"
stablemate_dir = "/checkout"
worktree_dir = "/worktrees"
artifacts_dir = "/artifacts"
paddock_dir = "/bench"
ostler_index_dir = "/index"

[workspaces]
acme = ["/code/api-service", { path = "/code/web-app", name = "web", url = "https://example.com/web.git", branch = "dev" }]

[profiles.opencode]
cli = "opencode"
[profiles.opencode.powers.high]
model = "m"
effort = "high"
timeout_scale = 2.5
[profiles.opencode.default]
model = "d"
[profiles.opencode.delegates.lookup]
model = "h"

[cli.opencode]
env = { FLAG = "1" }

[groom.attend]
mode = "session"
last_mode = "headless"
cli = "claude"
deny = ["merge"]

[groom.dispatch.runner]
command = "workhorse-loop-runner"
concurrency = 2
[[groom.dispatch.runner.params]]
name = "story"
label = "Story"
type = "select"
required = true
default = "a"
options = ["a", "b"]
template = "--story {value}"

[user_library.claude]
packs = ["general"]
skills = ["x"]
prompts = ["p"]
exclude = { skills = ["y"], prompts = ["q"] }
[user_library.template]
anything = "goes"

[qa_tools.tesseract]
command = "tesseract"
description = "OCR"

[saddlebag]
backend = "keyring"
"""


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setenv(cfgmod.CONFIG_PATH_ENV, str(path))
    monkeypatch.delenv(cfgmod.LEGACY_CONFIG_PATH_ENV, raising=False)
    cfgmod._warned_strays.clear()
    return path


def _models(annotation: Any) -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    if get_origin(annotation) in (Union, types.UnionType, list, dict):
        for arg in get_args(annotation):
            found.extend(_models(arg))
    return found


def _expand(annotation: Any, path: str) -> set[str]:
    paths: set[str] = set()
    origin = get_origin(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _paths(annotation, f"{path}.")
    if origin is dict:
        return _expand(get_args(annotation)[1], f"{path}.<name>")
    if origin is list:
        return _expand(get_args(annotation)[0], f"{path}[]")
    if origin in (Union, types.UnionType):
        for arg in get_args(annotation):
            paths |= _expand(arg, path)
    return paths


def _paths(model: type[BaseModel], prefix: str = "") -> set[str]:
    paths: set[str] = set()
    for name, info in model.model_fields.items():
        path = f"{prefix}{name}"
        paths.add(path)
        paths |= _expand(info.annotation, path)
    return paths


def _fields(model: type[BaseModel], prefix: str = ""):
    for name, info in model.model_fields.items():
        yield f"{prefix}{name}", info
        for child in _models(info.annotation):
            yield from _fields(child, f"{prefix}{name}.")


def test_every_setting_has_a_meaning_and_an_example():
    """A setting declared without its documentation would print as a blank entry in the reference."""
    missing = [
        path
        for path, info in _fields(HomeConfig)
        if not (info.description or "").strip() or not info.examples
    ]

    assert missing == []


def test_an_env_var_is_never_documented_without_its_precedence():
    """A reader told only that a variable stands in for a key cannot tell which one wins."""
    bare = [
        path
        for path, info in _fields(HomeConfig)
        if isinstance(info.json_schema_extra, dict)
        and info.json_schema_extra.get("env")
        and not info.json_schema_extra.get("precedence")
    ]

    assert bare == []


def test_the_reference_lists_exactly_the_declared_settings():
    """A setting added to the model but missing from the output, or an entry no field backs, breaks the one-source promise."""
    text = render_reference(HomeConfig, title="Home")
    listed = {line[5:-1] for line in text.splitlines() if line.startswith("### `")}

    assert listed == _paths(HomeConfig)
    assert listed == {row.path for row in reference_rows(HomeConfig)}


def test_the_reference_names_every_env_var_and_legacy_alias():
    """The reference is the only place a reader learns an environment variable stands in for a key."""
    text = render_reference(HomeConfig, title="Home")

    for var in ("STABLEMATE_ARTIFACTS_DIR", "STABLEMATE_BASE_DIR", "FARRIER_LIBRARY_DIR", "OSTLER_INDEX_DIR", "AGENT_CLI", "GROOM_ATTEND", "SADDLEBAG_BACKEND"):
        assert f"`${var}`" in text
    assert "- legacy:" in text
    assert "harness" in text


def test_a_full_file_loads_into_typed_attributes(cfg_file):
    """Every key group must validate against its declaration, or a valid client file would fail to load."""
    cfg_file.write_text(_FULL)

    home = cfgmod.load_home_config()

    assert home.groom and home.groom.attend and home.groom.attend.mode == "session"
    assert home.groom.dispatch["runner"].params[0].options == ["a", "b"]
    assert home.user_library and home.user_library.claude and home.user_library.claude.exclude
    assert home.user_library.template == {"anything": "goes"}
    assert home.qa_tools["tesseract"].command == "tesseract"
    assert home.saddlebag and home.saddlebag.backend == "keyring"
    assert home.workspaces["acme"][1].name == "web"
    assert home.cli["opencode"].env == {"FLAG": "1"}
    assert stray_keys(home) == []


def test_an_unknown_key_loads_and_warns_with_the_closest_declared_key(cfg_file, caplog):
    """A file written by a newer release must load; a typo must be pointed at the key it meant."""
    cfg_file.write_text('config_version = 2\ndefualt_cli = "claude"\n[profiles.p]\ncli = "claude"\n[profiles.p.powrs.high]\nmodel = "x"\n')

    with caplog.at_level(logging.WARNING):
        home = cfgmod.load_home_config()

    assert home.default_cli == "claude"
    assert "defualt_cli" in caplog.text and "'default_cli'" in caplog.text
    assert "profiles.p.powrs" in caplog.text and "'profiles.p.powers'" in caplog.text


def test_a_stray_key_is_warned_once_per_process(cfg_file, caplog):
    """A run re-reads the config on every node; repeating the warning would bury the log."""
    cfg_file.write_text('config_version = 2\nmystery = 1\n')

    with caplog.at_level(logging.WARNING):
        cfgmod.load_home_config()
        cfgmod.load_home_config()

    assert caplog.text.count("mystery") == 1


def test_a_newer_schema_with_unknown_keys_still_loads(cfg_file, caplog):
    """A newer release's file must never stop an older tool from reading."""
    cfg_file.write_text('config_version = 9\nfuture_key = { a = 1 }\ndefault_cli = "codex"\n')

    with caplog.at_level(logging.WARNING):
        home = cfgmod.load_home_config()

    assert home.config_version == 9
    assert home.default_cli == "codex"


def test_a_bad_type_raises_naming_the_key_path(cfg_file):
    """A fresh load that accepts a wrong shape would let the mistake surface as a misbehaving run."""
    cfg_file.write_text('config_version = 2\n[groom.dispatch.runner]\ncommand = "x"\nconcurrency = "many"\n')

    with pytest.raises(cfgmod.ConfigError, match=r"groom\.dispatch\.runner\.concurrency"):
        cfgmod.load_home_config()


def test_a_workspace_entry_without_a_path_names_its_key_path(cfg_file):
    cfg_file.write_text('[workspaces]\nacme = ["/a", { name = "x" }]\n')

    with pytest.raises(cfgmod.ConfigError, match=r"workspaces\.acme\.1\.path"):
        cfgmod.load_home_config()


def test_a_failed_in_memory_lift_raises_instead_of_returning_the_raw_shape(cfg_file):
    """The raw v1 shape fails validation in confusing ways; the migration's own message says what to fix."""
    cfg_file.write_text('[profiles.broken]\n[profiles.broken.powers.high]\nmodel = "x"\n')

    with pytest.raises(cfgmod.ConfigVersionError, match="cli field"):
        cfgmod.load_home_config()


def test_a_version_one_file_loads_through_the_migration(cfg_file):
    """A client with an old file must see the same profiles the v2 shape gives."""
    cfg_file.write_text(
        '[power.high.claude]\nmodel = "opus"\n[default.claude]\nmodel = "sonnet"\n[harness.claude]\nenv = { A = "1" }\n'
    )

    home = cfgmod.load_home_config()

    assert home.profiles["claude"].powers["high"].model == "opus"
    assert home.profiles["claude"].default and home.profiles["claude"].default.model == "sonnet"
    assert profiles.resolve_harness_env("claude") == {"A": "1"}


def test_resolvers_read_the_same_values_through_the_document(cfg_file, monkeypatch):
    """Moving the readers onto the Document must not move a single resolved value."""
    monkeypatch.delenv(cfgmod.ARTIFACTS_DIR_ENV, raising=False)
    cfg_file.write_text(_FULL)

    assert str(cfgmod.resolve_stablemate_dir()) == "/checkout"
    assert str(cfgmod.resolve_worktree_dir()) == "/worktrees"
    assert str(cfgmod.resolve_artifacts_dir()) == "/artifacts"
    assert str(cfgmod.resolve_paddock_dir()) == "/bench"
    assert profiles.resolve_default_cli() == "opencode"
    assert profiles.profile_names() == ["opencode"]
    profile = profiles.select_profile(None, "opencode")
    assert profiles.resolve_power("high", "opencode", profile) == profiles.PowerMapping("m", "high", 2.5)
    assert profiles.resolve_backend_default("opencode", profile).model == "d"
    assert set(profiles.resolve_delegates("opencode", profile)) == {"lookup"}
    members = cfgmod.resolve_workspace("acme")
    assert [(m.name, m.url, m.branch) for m in members] == [
        ("api-service", "", ""),
        ("web", "https://example.com/web.git", "dev"),
    ]
