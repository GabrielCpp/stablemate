"""The reference `farrier config reference` prints: every key of the shared config files, rendered from their schema."""
from __future__ import annotations

from collections.abc import Callable

from farrier._vendor.stablemate_core.config import (
    CONFIG_PATH_ENV,
    LEGACY_CONFIG_PATH_ENV,
    config_path,
)
from farrier._vendor.stablemate_core.manifest import LEGACY_MANIFEST_NAMES, MANIFEST_NAME
from farrier._vendor.stablemate_core.schema import HomeConfig, Manifest, render_reference, yaml_value


def home_reference() -> str:
    intro = (
        "The machine config is one TOML file per user, read by every stablemate tool. "
        f"On this machine it is `{config_path()}`; `${CONFIG_PATH_ENV}` (or the older "
        f"`${LEGACY_CONFIG_PATH_ENV}`) points the tools at another file. A key that is "
        "not set takes its default. A key not listed here is kept and reported as a "
        "stray key when the file loads. In a path, `<name>` stands for a name the user "
        "picks and `[]` for one entry of a list."
    )
    return render_reference(HomeConfig, title="Machine config (config.toml)", intro=intro)


def manifest_reference() -> str:
    intro = (
        f"The repository manifest is one YAML file, `{MANIFEST_NAME}`, at the repository root. "
        f"Farrier reads it to decide what to render. The installed workflows and ostler read "
        f"their own keys from it. The older names {', '.join(f'`{n}`' for n in LEGACY_MANIFEST_NAMES)} "
        f"are still found, with a warning. The file has no version. A key not listed here is "
        "kept and reported as a stray key when the file loads. In a path, `<name>` stands for a "
        "name the user picks and `[]` for one entry of a list."
    )
    return render_reference(
        Manifest, title=f"Repository manifest ({MANIFEST_NAME})", intro=intro, render=yaml_value
    )


REFERENCES: dict[str, Callable[[], str]] = {
    "home": home_reference,
    "manifest": manifest_reference,
}


def reference_text(file: str = "all") -> str:
    """The reference of one file, or of every file when ``file`` is ``all``."""
    names = list(REFERENCES) if file == "all" else [file]
    return "\n".join(REFERENCES[name]() for name in names)
