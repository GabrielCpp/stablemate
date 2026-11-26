from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from farrier._vendor.stablemate_core.config import load_home_config
from farrier._vendor.stablemate_core.schema.home import HomeConfig, UserLibraryTable
from farrier.antigravity_bridge import ANTIGRAVITY_BRIDGE, ANTIGRAVITY_GUARDS
from farrier.home_entries import user_entries
from farrier.home_guards import (
    GUARD_HOME,
    Guard,
    antigravity_hooks,
    installed_command,
    selected_guards,
)
from farrier.home_mcp import MCP_DIALECTS
from farrier.layers import resolve_library_dir, set_layers
from farrier.outputs import render_user_expected, write_text
from farrier.renderer import Rendered
from farrier.user_library import user_library_tables

HARNESS = "antigravity"
NAME = "stablemate"
DESCRIPTION = (
    "The stablemate agent toolchain: workhorse workflows, farrier, groom, ostler and "
    "saddlebag, with the library's skills, agents and guards."
)
SKILL_LIMIT = 24 * 1024
TOOLS = (
    "farrier",
    "groom",
    "groom-sidecar",
    "ostler",
    "saddlebag",
    "workhorse-loop-runner",
    "workhorse-research",
    "workhorse-author",
    "workhorse-coder",
    "workhorse-okf-book",
    "workhorse-review-debt",
    "workhorse-new",
)
PLACES = (
    (".gemini/config/AGENTS.md", "rules/AGENTS.md"),
    (".gemini/config/", ""),
    (f"{GUARD_HOME}/", "hooks/"),
)
BRIDGE = "hooks/farrier-guards.py"
LAUNCHER = '#!/bin/sh\n{drive}exec uvx --from "stablemate=={version}" {tool} "$@"\n'
DRIVE_AGY = 'export AGENT_CLI="${{AGENT_CLI:-{harness}}}"\n'


def launcher(tool: str, version: str) -> Rendered:
    drive = DRIVE_AGY.format(harness=HARNESS) if tool.startswith("workhorse-") else ""
    return Rendered(
        LAUNCHER.format(drive=drive, version=version, tool=tool), verbatim=True, executable=True
    )


def tool_reference(command: str) -> str:
    head, _, rest = command.partition(" ")
    if head not in TOOLS:
        return command
    return f"bin/{head}" + (f" {rest}" if rest else "")


def plugin_rel(rel: str) -> str:
    for home_rel, placed in PLACES:
        if not home_rel.endswith("/") and rel == home_rel:
            return placed
        if home_rel.endswith("/") and rel.startswith(home_rel):
            return placed + rel[len(home_rel) :]
    raise SystemExit(
        f"error: the {HARNESS} home render wrote {rel}, which has no place in a plugin."
    )


def scoped(config: HomeConfig) -> HomeConfig:
    table = user_library_tables(config).get(HARNESS)
    if table is None:
        raise SystemExit(
            f"error: the config names no [user_library.{HARNESS}] table, so the plugin "
            "would carry nothing. Add one naming its packs, guards, agents and MCP servers."
        )
    if table.settings:
        raise SystemExit(
            f"error: [user_library.{HARNESS}] names settings, and an Antigravity plugin "
            "cannot carry settings. Remove `settings` from the table."
        )
    return config.model_copy(
        update={"user_library": UserLibraryTable.model_validate({HARNESS: table})}
    )


def guard_hooks(guards: list[Guard]) -> str:
    def command(guard: Guard) -> str:
        folder = f"hooks/{guard.name}"
        return tool_reference(installed_command(guard, Path(), HARNESS, folder))

    served = [guard for guard in guards if HARNESS not in guard.not_on]
    return antigravity_hooks(served, HARNESS, BRIDGE, command)


def mcp_config(config: HomeConfig) -> str | None:
    rel = MCP_DIALECTS[HARNESS].rel
    servers = {}
    for entry in user_entries(config):
        if entry.rel != rel:
            continue
        server = dict(entry.value)
        command = str(server["command"])
        if command in TOOLS:
            server["command"] = "sh"
            server["args"] = ["${PLUGIN_ROOT}/bin/" + command, *server.get("args", [])]
        servers[entry.name] = server
    if not servers:
        return None
    return json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n"


def oversized_skills(files: dict[str, str]) -> list[str]:
    return [
        f"{rel} ({len(text.encode('utf-8')) / 1024:.1f} KB)"
        for rel, text in sorted(files.items())
        if rel.startswith("skills/")
        and rel.endswith("/SKILL.md")
        and len(text.encode("utf-8")) > SKILL_LIMIT
    ]


def plugin_files(config: HomeConfig, version: str) -> dict[str, str]:
    config = scoped(config)
    with tempfile.TemporaryDirectory() as scratch:
        home = Path(scratch)
        rendered = render_user_expected(config, home)
        own = {home / ANTIGRAVITY_GUARDS, home / ANTIGRAVITY_BRIDGE}
        files = {
            plugin_rel(path.relative_to(home).as_posix()): text
            for path, text in rendered.items()
            if path not in own
        }
        absolute = sorted(rel for rel, text in files.items() if scratch in text)
        bridge = rendered.get(home / ANTIGRAVITY_BRIDGE)
    if absolute:
        raise SystemExit(
            "error: these plugin files name the render folder, and a plugin carries no "
            f"absolute path: {', '.join(absolute)}"
        )
    guards = selected_guards(config).get(HARNESS, [])
    if bridge is not None:
        files[BRIDGE] = bridge
        files["hooks.json"] = Rendered(guard_hooks(guards), verbatim=True)
    servers = mcp_config(config)
    if servers is not None:
        files["mcp_config.json"] = Rendered(servers, verbatim=True)
    for tool in TOOLS:
        files[f"bin/{tool}"] = launcher(tool, version)
    manifest = {"name": NAME, "version": version, "description": DESCRIPTION}
    files["plugin.json"] = Rendered(json.dumps(manifest, indent=2) + "\n", verbatim=True)
    over = oversized_skills(files)
    if over:
        raise SystemExit(
            f"error: Antigravity loads only the first {SKILL_LIMIT // 1024} KB of a skill, "
            f"and these are longer: {', '.join(over)}. Split each into an entry skill and "
            "reference files."
        )
    return files


def build(config: HomeConfig, version: str, out: Path) -> int:
    files = plugin_files(config, version)
    if out.exists() and any(out.iterdir()):
        if not (out / "plugin.json").is_file():
            raise SystemExit(
                f"error: {out} holds files and no plugin.json. Name an empty folder or a "
                "plugin built before."
            )
        shutil.rmtree(out)
    for rel, text in files.items():
        write_text(out / rel, text)
    print(f"Built the {NAME} {HARNESS} plugin {version}: {len(files)} files in {out}")
    return 0


def add_plugin_parser(sub: argparse._SubParsersAction) -> None:
    plugin = sub.add_parser("plugin", help="Build an agent-CLI plugin from the library")
    actions = plugin.add_subparsers(dest="plugin_action", required=True)
    build_p = actions.add_parser(
        "build",
        help="Render the library and a launcher for every stablemate tool into a plugin folder",
    )
    build_p.add_argument("--harness", required=True, choices=[HARNESS])
    build_p.add_argument("--out", required=True, type=Path, help="The plugin folder to write")
    build_p.add_argument(
        "--version",
        required=True,
        help="The stablemate version the plugin carries and its launchers run",
    )
    build_p.add_argument(
        "--config",
        type=Path,
        help=f"A stablemate config whose [user_library.{HARNESS}] table selects the content "
        "(default: the home config)",
    )


def run_plugin(args: argparse.Namespace) -> int:
    set_layers(resolve_library_dir(None))
    config = load_home_config(args.config.resolve() if args.config else None)
    return build(config, args.version, args.out.resolve())
