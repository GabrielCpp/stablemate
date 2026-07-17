"""Argument parsing and command dispatch — the ``farrier`` entry point.

Wires the config/layers/sources/renderer/outputs/scaffolds modules together behind
the subcommands (install, config, source, scaffold, version).
"""
from __future__ import annotations

import argparse
import importlib.metadata
import sys
from pathlib import Path
from typing import Any

from farrier import layers as _layers
from stablemate_core.config import (
    config_path,
    read_config,
    write_base_dir,
    write_library_dir,
    write_stablemate_dir,
)
from farrier.frontmatter import (
    banner_sources,
    frontmatter_metadata,
    mapping_skill_names,
    read_yaml,
)
from farrier.layers import (
    find_in_layers,
    is_library_dir,
    resolve_library_dir,
    searched_layers,
    set_layers,
)
from farrier.naming import kebab
from farrier.outputs import (
    check_outputs,
    install_outputs,
    render_expected,
    write_text,
)
from farrier.renderer import Renderer
from farrier.scaffolds import (
    available_scaffold_ids,
    fetch_scaffold_url,
    flatten_scaffold_tree,
    load_scaffold_defs,
    parse_param_overrides,
    resolve_scaffold_params,
    substitute_scaffold_path,
)
from farrier.sources import (
    collect_selection,
    library_source_path,
    load_layered_sources,
    selected_sources,
)


def _add_install_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to install into (default: cwd)",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to agents.yml (default: <repo>/agents.yml)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated files are current without writing",
    )
    parser.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )


def _run_install(args: argparse.Namespace) -> int:
    set_layers(resolve_library_dir(args.library))
    repo = args.repo.resolve()
    config_path = args.config.resolve() if args.config else repo / "agents.yml"
    config = read_yaml(config_path)
    outputs = render_expected(config, repo)
    if args.check:
        return check_outputs(repo, outputs)
    install_outputs(repo, outputs)
    print(f"Installed {len(outputs)} generated files into {repo}")
    return 0


def _run_config(args: argparse.Namespace) -> int:
    if args.config_action == "set-library":
        root = args.path.expanduser().resolve()
        if not is_library_dir(root):
            raise SystemExit(
                f"error: {root} is not a usable library directory — it must contain library/ and packs/."
            )
        write_library_dir(root)
        print(f"library_dir={root}")
        return 0

    if args.config_action == "set-stablemate":
        root = args.path.expanduser().resolve()
        write_stablemate_dir(root)
        print(f"stablemate_dir={root}")
        return 0

    if args.config_action == "set-base":
        root = args.path.expanduser().resolve()
        if not is_library_dir(root):
            raise SystemExit(
                f"error: {root} is not a usable base library directory — it must contain "
                "library/ or workflows/."
            )
        write_base_dir(root)
        print(f"base_dir={root}")
        return 0

    # show — with a key: print bare value; without: print all as key=value
    cfg = read_config()
    if args.key:
        value = cfg.get(args.key)
        if value is None:
            raise SystemExit(f"error: '{args.key}' is not set in {config_path()}")
        print(value)
    else:
        for key, value in cfg.items():
            print(f"{key}={value}")
    return 0


def find_agents_config(start: Path) -> Path | None:
    """The nearest agents.yml at or above *start* (the repo config), or None."""
    for directory in [start, *start.parents]:
        candidate = directory / "agents.yml"
        if candidate.is_file():
            return candidate
    return None


def mapped_instruction_sources(generated: Path) -> list[str] | None:
    """Resolve a generated local-instruction file via its repo's agents.yml.

    The file's HTML banner is a generation-time snapshot; `agents.yml →
    localInstructions` is the live mapping and may have been edited since. So
    resolution walks up to the repo's agents.yml, finds the mapping targeting
    this file's directory, and turns its installed skill names into library
    source paths with the same selection/prefix machinery install uses. When
    several mappings target the directory the last one wins, mirroring install.

    Returns library-relative source paths; None when the file is not a local
    instruction file or no agents.yml exists above it (caller may fall back to
    the banner); exits when agents.yml exists but no longer maps this file —
    the file is stale, and pointing at its old sources would invite edits that
    the next install silently discards.
    """
    if generated.name not in ("CLAUDE.md", "AGENTS.md", "CODEX.md"):
        return None
    config_path = find_agents_config(generated.parent)
    if config_path is None:
        return None
    repo = config_path.parent
    config = read_yaml(config_path)
    directory = generated.parent
    skill_names: list[str] = []
    for mapping in config.get("localInstructions", []) or []:
        for rel in mapping.get("paths", []) or []:
            if (repo / rel).resolve() == directory:
                skill_names = mapping_skill_names(mapping)
    if not skill_names:
        raise SystemExit(
            f"error: {generated} is not mapped by {config_path} → "
            "localInstructions — the mapping was removed or moved, so this file "
            "is stale. Re-run `farrier --repo .` (or `make agent-install`) to "
            "regenerate or remove it."
        )
    repo_config = config.get("repo") or {}
    prefix = kebab(
        str(repo_config.get("prefix") or repo_config.get("name") or repo.name)
    )
    include_skills, _, _, _, _ = collect_selection(config)
    exclude = config.get("exclude") or {}
    skills = selected_sources(
        load_layered_sources("skill", "library", "skills"),
        include_skills,
        set(exclude.get("skills", []) or []),
    )
    renderer = Renderer(repo, prefix, repo_config, {}, skills, [])
    return [
        library_source_path(renderer.skill_source(name)) for name in skill_names
    ]


def _run_source(args: argparse.Namespace) -> int:
    """Resolve a generated file back to its editable library source path(s).

    Skills/commands carry a machine-independent, `library/`-anchored
    `metadata.source` in front matter; local instruction files resolve through
    their repo's agents.yml (see mapped_instruction_sources). Either way the
    relative path is joined under the library root resolved exactly as
    ``install`` does (`--library` > `$FARRIER_LIBRARY_DIR` > home config), so
    the printed path is the real editable source on *this* machine.
    """
    generated = args.file.resolve()
    if not generated.is_file():
        raise SystemExit(f"error: {args.file} is not a file")
    set_layers(resolve_library_dir(args.library))
    text = generated.read_text(encoding="utf-8")
    # Skills/commands stamp one source in front matter. Local instruction files
    # resolve through the repo's agents.yml — the live mapping — and only fall
    # back to their generation-time HTML banner when no agents.yml is found.
    rel_source = frontmatter_metadata(text).get("source")
    if rel_source:
        rel_sources = [rel_source]
    else:
        rel_sources = mapped_instruction_sources(generated)
        if rel_sources is None:
            rel_sources = banner_sources(text)
            if rel_sources:
                print(
                    f"note: no agents.yml found above {args.file}; resolving from "
                    "the file's banner, which may be stale.",
                    file=sys.stderr,
                )
    if not rel_sources:
        raise SystemExit(
            f"error: {args.file} has no `metadata.source` front matter and no "
            "farrier banner — it is not a farrier-generated file."
        )
    for rel in rel_sources:
        hit = find_in_layers(rel)
        if hit is None or not hit[1].is_file():
            raise SystemExit(
                f"error: source '{rel}' does not exist in any library layer.\n"
                f"Searched:\n{searched_layers()}\n"
                "The generated file may predate a library move/rename — check "
                "`farrier config show library_dir`."
            )
        layer, abs_source = hit
        # With more than one layer, *which* copy you are about to edit is the whole
        # question — an overlay shadowing the base means the base copy is inert.
        # stdout stays the bare path so callers can `$(farrier source ...)` it.
        if len(_layers.LAYERS) > 1:
            print(f"note: resolved from layer {layer.name}", file=sys.stderr)
        print(abs_source)
    return 0


def _list_scaffolds(
    defs: dict[str, dict[str, Any]], available: set[str], repo: Path
) -> int:
    ids = sorted(set(defs) & available)
    if not ids:
        print(
            "No scaffolds available. Library defines: "
            + (", ".join(sorted(defs)) or "(none)")
            + f". Add ids to the `scaffolds:` list in {repo / 'agents.yml'}."
        )
        return 0
    for sid in ids:
        definition = defs[sid]
        description = str(definition.get("description") or "").strip()
        print(f"{sid}" + (f" — {description}" if description else ""))
        for name, default in (definition.get("params") or {}).items():
            suffix = "(required)" if default is None else f"(default: {default})"
            print(f"    --param {name}=...  {suffix}")
    return 0


def _run_scaffold(args: argparse.Namespace) -> int:
    set_layers(resolve_library_dir(args.library))
    repo = args.repo.resolve()
    defs = load_scaffold_defs()
    available = available_scaffold_ids(repo, defs)

    if args.list or not args.id:
        return _list_scaffolds(defs, available, repo)

    scaffold_id = args.id
    if scaffold_id not in defs:
        raise SystemExit(
            f"Unknown scaffold: {scaffold_id!r}. Library defines: "
            + (", ".join(sorted(defs)) or "(none)")
        )
    if scaffold_id not in available:
        raise SystemExit(
            f"Scaffold {scaffold_id!r} is not enabled for this repo — add it to "
            f"the `scaffolds:` list in {repo / 'agents.yml'} (or select a pack "
            "that provides it)."
        )

    definition = defs[scaffold_id]
    params = resolve_scaffold_params(
        scaffold_id, definition, parse_param_overrides(args.param), repo
    )
    files, dirs = flatten_scaffold_tree(scaffold_id, definition["tree"])

    from string import Template

    created = 0
    for rel in sorted(dirs):
        resolved = substitute_scaffold_path(scaffold_id, rel, params)
        target = repo / resolved
        if target.is_dir():
            print(f"exists (kept): {resolved}/")
            continue
        target.mkdir(parents=True, exist_ok=True)
        print(f"created: {resolved}/")
    for rel, spec in sorted(files.items()):
        resolved = substitute_scaffold_path(scaffold_id, rel, params)
        target = repo / resolved
        # Seed semantics: never clobber a file the repo already owns.
        if target.exists():
            print(f"exists (kept): {resolved}")
            continue
        if isinstance(spec, dict):
            content = fetch_scaffold_url(scaffold_id, resolved, str(spec["url"]))
        else:
            content = Template(spec).safe_substitute(params)
        write_text(target, content)
        print(f"created: {resolved}")
        created += 1
    print(f"Scaffolded {scaffold_id!r}: {created} file(s) created in {repo}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="farrier",
        description="Render an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters.",
    )
    sub = parser.add_subparsers(dest="command")

    # install (default)
    install_p = sub.add_parser(
        "install", help="Render/install the selected packs into a repository (default)"
    )
    _add_install_args(install_p)

    # config
    config_p = sub.add_parser("config", help="Manage the farrier home config")
    config_sub = config_p.add_subparsers(dest="config_action", required=True)
    set_lib = config_sub.add_parser(
        "set-library", help="Record the library directory in the home config"
    )
    set_lib.add_argument(
        "path", type=Path, help="Path to the library (the agents/ tree)"
    )
    set_sm = config_sub.add_parser(
        "set-stablemate", help="Record the stablemate checkout path in the home config"
    )
    set_sm.add_argument("path", type=Path, help="Path to the stablemate checkout")
    set_base = config_sub.add_parser(
        "set-base",
        help="Record the base library content path (for isolated/pipx installs where "
        "the stablemate-library wheel isn't importable)",
    )
    set_base.add_argument(
        "path", type=Path, help="Path to the base library content directory"
    )
    show_p = config_sub.add_parser(
        "show", help="Print all config keys as key=value lines, or a single bare value"
    )
    show_p.add_argument(
        "key",
        nargs="?",
        default=None,
        help="If given, print only the value of this key",
    )

    # source
    source_p = sub.add_parser(
        "source",
        help="Print the editable library source path of a generated skill/command",
    )
    source_p.add_argument(
        "file", type=Path, help="Path to a generated SKILL.md / command .md"
    )
    source_p.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )

    # scaffold
    scaffold_p = sub.add_parser(
        "scaffold",
        help="Seed repository files from a library scaffold definition",
    )
    scaffold_p.add_argument(
        "id",
        nargs="?",
        default=None,
        help="Scaffold id (omit to list the available scaffolds)",
    )
    scaffold_p.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override a scaffold parameter (repeatable)",
    )
    scaffold_p.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scaffold into (default: cwd)",
    )
    scaffold_p.add_argument(
        "--list",
        action="store_true",
        help="List the scaffolds available to this repo and their params",
    )
    scaffold_p.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )

    # version
    sub.add_parser("version", help="Print the installed farrier version")

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = _build_parser()

    # Keep `farrier --repo .` working: if no recognised subcommand is given,
    # inject `install` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    _SUBCOMMANDS = {"install", "config", "version", "source", "scaffold"}
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["install"] + argv

    args = parser.parse_args(argv)

    if args.command == "version":
        print(importlib.metadata.version("farrier"))
        return 0

    if args.command == "config":
        return _run_config(args)

    if args.command == "source":
        return _run_source(args)

    if args.command == "scaffold":
        return _run_scaffold(args)

    return _run_install(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
