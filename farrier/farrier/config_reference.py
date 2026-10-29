"""The reference `farrier config reference` prints: every key of the shared config files, rendered from their schema."""
from __future__ import annotations

import difflib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from farrier._vendor.stablemate_core.config import (
    CONFIG_PATH_ENV,
    LEGACY_CONFIG_PATH_ENV,
    config_path,
)
from farrier._vendor.stablemate_core.manifest import LEGACY_MANIFEST_NAMES, MANIFEST_NAME
from farrier._vendor.stablemate_core.schema import (
    HomeConfig,
    Manifest,
    ReferenceRow,
    Section,
    reference_rows,
    render_entries,
    render_index,
    select_rows,
    toml_value,
    yaml_value,
)


@dataclass(frozen=True)
class Reference:
    """One shared config file as the reference describes it."""

    title: str
    intro: Callable[[], str]
    model: type[Section]
    render: Callable[[Any], str]

    def rows(self) -> list[ReferenceRow]:
        return reference_rows(self.model, render=self.render)


def _home_intro() -> str:
    return (
        "The machine config is one TOML file per user, read by every stablemate tool. "
        f"On this machine it is `{config_path()}`; `${CONFIG_PATH_ENV}` (or the older "
        f"`${LEGACY_CONFIG_PATH_ENV}`) points the tools at another file. A key that is "
        "not set takes its default. A key not listed here is kept and reported as a "
        "stray key when the file loads. In a path, `<name>` stands for a name the user "
        "picks and `[]` for one entry of a list."
    )


def _manifest_intro() -> str:
    return (
        f"The repository manifest is one YAML file, `{MANIFEST_NAME}`, at the repository root. "
        f"Farrier reads it to decide what to render. The installed workflows and ostler read "
        f"their own keys from it. The older names {', '.join(f'`{n}`' for n in LEGACY_MANIFEST_NAMES)} "
        f"are still found, with a warning. The file has no version. A key not listed here is "
        "kept and reported as a stray key when the file loads. In a path, `<name>` stands for a "
        "name the user picks and `[]` for one entry of a list."
    )


REFERENCES: dict[str, Reference] = {
    "home": Reference("Machine config (config.toml)", _home_intro, HomeConfig, toml_value),
    "manifest": Reference(f"Repository manifest ({MANIFEST_NAME})", _manifest_intro, Manifest, yaml_value),
}

INDEX_FOOTER = (
    "Run `farrier config reference <key>` for the full entry of a key and the keys under it: "
    "its meaning, environment variable, precedence and example. A name you picked matches its "
    "`<name>` placeholder, so `profiles.claude` works. `--full` prints every full entry."
)


class UnknownKeyError(LookupError):
    """A key path that matches no setting of the selected files."""


def _closest(query: str, references: list[Reference]) -> list[str]:
    paths = [row.path for reference in references for row in reference.rows()]
    return difflib.get_close_matches(query, paths, n=3, cutoff=0.5)


def reference_text(file: str = "all", key: str = "", *, full: bool = False) -> str:
    """The index of the selected files, or full entries for ``key`` and the keys under it, or every full entry."""
    references = list(REFERENCES.values()) if file == "all" else [REFERENCES[file]]
    if not key:
        render = render_entries if full else render_index
        parts = [render(reference.rows(), title=reference.title, intro=reference.intro()) for reference in references]
        return "\n".join(parts) + ("" if full else f"\n{INDEX_FOOTER}\n")
    parts = []
    for reference in references:
        rows = select_rows(reference.rows(), key)
        if rows:
            parts.append(render_entries(rows, title=reference.title))
    if not parts:
        near = _closest(key, references)
        hint = f" Closest: {', '.join(f'`{path}`' for path in near)}." if near else ""
        raise UnknownKeyError(f"no config key matches `{key}`.{hint} `farrier config reference` lists every key.")
    return "\n".join(parts)
