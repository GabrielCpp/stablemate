"""Unified QA tool registry: which external commands a repo has opted into, and what they resolve to on this machine."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ostler._vendor.stablemate_core.config import config_path, load_home_config
from ostler._vendor.stablemate_core.schema import HomeConfig, QaTool
from ostler.manifest import MANIFEST_FILENAMES, read_manifest
from ostler.provenance import effective_checkouts
from ostler.qa.outcome import QaOutcome

BUILTIN_TOOLS: dict[str, str] = {
    "tesseract": "tesseract",
    "convert": "convert",
    "grpcurl": "grpcurl",
}

def config_files(root: Path) -> tuple[Path, ...]:
    """Every file whose contents decide which QA tools a run on *root* can invoke, present or not."""
    return (*(root / name for name in MANIFEST_FILENAMES), config_path())


def opted_in_tools(root: Path) -> set[str]:
    """The tool names *root*'s `qa:` block lists under `tools:`, plus each active workspace member's."""
    names: set[str] = set()
    for repo in (root, *effective_checkouts(None).values()):
        manifest = read_manifest(repo)
        if manifest is not None:
            names.update(manifest.qa.tools)
    return names


@dataclass(frozen=True)
class ToolSpec:
    name: str
    command: str
    description: str
    builtin: bool

    @property
    def available(self) -> bool:
        return shutil.which(self.command) is not None


def _configured_tools(home: HomeConfig | None) -> dict[str, QaTool]:
    return dict((home if home is not None else load_home_config()).qa_tools)


def catalog(root: Path, *, home: HomeConfig | None = None) -> tuple[dict[str, ToolSpec], list[str]]:
    """Every opted-in tool, resolved to a `ToolSpec`, plus errors for names that resolve to nothing."""
    configured = _configured_tools(home)
    specs: dict[str, ToolSpec] = {}
    errors: list[str] = []
    for name in sorted(opted_in_tools(root)):
        entry = configured.get(name)
        if entry is not None:
            command = entry.command
            if not command:
                errors.append(
                    f"qa tool {name!r} is opted into via agents.yml but its "
                    f"[qa_tools.{name}] table in {config_path()} has no `command`"
                )
                continue
            specs[name] = ToolSpec(
                name=name,
                command=command,
                description=entry.description,
                builtin=name in BUILTIN_TOOLS,
            )
        elif name in BUILTIN_TOOLS:
            specs[name] = ToolSpec(
                name=name, command=BUILTIN_TOOLS[name], description=f"built-in {name} tool", builtin=True
            )
        else:
            errors.append(
                f"qa tool {name!r} is opted into via agents.yml's `qa: {{tools: [...]}}` "
                f"but is not a built-in and has no [qa_tools.{name}] table in {config_path()}"
            )
    return specs, errors


def cmd_catalog(root: Path, *, home: HomeConfig | None = None) -> QaOutcome:
    """The catalog as the rows the CLI prints and the coder workflow reads."""
    try:
        specs, errors = catalog(root, home=home)
    except (OSError, ValueError) as exc:
        specs, errors = {}, [str(exc)]
    rows = [
        {
            "name": spec.name,
            "command": spec.command,
            "description": spec.description,
            "builtin": spec.builtin,
            "available": spec.available,
        }
        for spec in specs.values()
    ]
    missing = [str(row["name"]) for row in rows if not row["available"]]
    ok = not errors and not missing
    message = "\n".join(
        [*errors, *(f"qa tool {name!r} is not on PATH" for name in missing)]
    ) or f"{len(rows)} qa tool(s) available"
    return QaOutcome(ok=ok, message=message, data={"tools": rows, "errors": errors})


def preflight_errors(root: Path, *, home: HomeConfig | None = None) -> list[str]:
    """Every reason this repo's opted-in QA tools cannot run right now."""
    specs, errors = catalog(root, home=home)
    missing = [
        f"qa tool {spec.name!r} names command {spec.command!r}, which is not on PATH"
        for spec in specs.values()
        if not spec.available
    ]
    return [*errors, *missing]


def resolved_commands(root: Path, *, home: HomeConfig | None = None) -> dict[str, str]:
    """`{name: command}` for every opted-in tool that resolved to a definition."""
    specs, _errors = catalog(root, home=home)
    return {spec.name: spec.command for spec in specs.values()}
