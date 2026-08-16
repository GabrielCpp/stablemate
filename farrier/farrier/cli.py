"""Argument parsing and command dispatch — the ``farrier`` entry point.

Wires the config/layers/sources/renderer/outputs/scaffolds modules together behind
the subcommands (init, install, config, source, scaffold, version).
"""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import sys
from pathlib import Path
from typing import Any

from farrier import layers as _layers
from farrier import pipx
from farrier._vendor.stablemate_core.config import (
    CONFIG_PATH_ENV,
    ConfigVersionError,
    UnknownProfileError,
    config_path,
    read_config,
    select_profile,
    write_base_dir,
    write_library_dir,
    write_stablemate_dir,
)
from farrier.frontmatter import (
    LOCAL_INSTRUCTION_FILES,
    banner_sources,
    frontmatter_metadata,
    mapping_prompt_names,
    mapping_skill_names,
    read_yaml,
)
from farrier.init import default_config
from farrier.layers import (
    LAYERS,
    ensure_base_library_dir,
    find_in_layers,
    is_library_dir,
    resolve_library_dir,
    searched_layers,
    set_layers,
)
from farrier.library_check import check_library, format_findings
from farrier.naming import repo_prefix
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


def _run_init(args: argparse.Namespace) -> int:
    """`farrier init` — write the starter ``agents.yml`` every other command reads.

    Refusing to overwrite is the whole safety story here, and it is a hard error rather
    than the scaffold command's "exists (kept)": a scaffold seeds a tree where some
    files legitimately already exist, whereas someone running `init` in a configured
    repo has confused it with `install`, and telling them so beats printing a success
    line that did nothing. `--force` is the escape hatch, and it says what it costs.
    """
    repo = args.repo.resolve()
    if not repo.is_dir():
        raise SystemExit(f"error: {repo} is not a directory")
    target = repo / "agents.yml"
    if target.exists() and not args.force:
        raise SystemExit(
            f"error: {target} already exists — this repo is configured; "
            f"run `farrier install --repo {args.repo}` to render it, "
            f"or `farrier init --force` to replace the config with a fresh default"
        )
    write_text(target, default_config(repo))
    print(f"Wrote {target}")
    print("Next: list the packs you want under `packs:`, then `farrier install`.")
    return 0


def _run_install(args: argparse.Namespace) -> int:
    # Check out the base library, and update it, before anything looks for it. This is the
    # one command that does: install is an operator asking for a re-render at a moment
    # they chose, which is the same authority `rm -rf ~/.cache/stablemate` always carried.
    # It must come first because `resolve_library_dir` reads "no overlay and no base" as a
    # setup error, and the base is exactly what this call is here to produce.
    #
    # `--check` fetches but does not refresh. It writes nothing and runs in CI, where a
    # library that moved underneath the comparison would turn a drift report into a
    # coin-flip — the answer would depend on the hour the job ran rather than on the
    # commit it ran against.
    ensure_base_library_dir(refresh=not args.check)
    set_layers(resolve_library_dir(args.library))
    repo = args.repo.resolve()
    config_path = args.config.resolve() if args.config else repo / "agents.yml"
    if not args.config and not config_path.exists():
        raise SystemExit(
            f"Missing config: {config_path}\n"
            "Run `farrier init` to write a starter agents.yml, then list the "
            "packs to install under `packs:`."
        )
    config = read_yaml(config_path)
    outputs = render_expected(config, repo)
    if args.check:
        return check_outputs(repo, outputs)
    install_outputs(repo, outputs)
    print(f"Installed {len(outputs)} generated files into {repo}")
    return 0


def _run_config(args: argparse.Namespace) -> int:
    if getattr(args, "config_file", None):
        # Written into the environment rather than threaded through, because the reader
        # and the four writers below all resolve the path themselves — one assignment
        # here moves every one of them, and a parameter would have to be added to each.
        # It is also what a subprocess of this one would need to agree with.
        os.environ[CONFIG_PATH_ENV] = str(args.config_file.expanduser())
    try:
        return _dispatch_config(args)
    except ConfigVersionError as exc:
        # A config written by a newer stablemate-core. Actionable and deterministic, so
        # it exits cleanly like every other config error here rather than as a traceback.
        raise SystemExit(f"error: {exc}") from exc
    except UnknownProfileError as exc:
        # Same class of thing: the operator named something the file does not define, and
        # the message already lists what it does.
        raise SystemExit(f"error: {exc}") from exc


def _flatten(table: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """A nested config table as dotted `key=value` pairs, in file order.

    What an operator cannot do with `cat`: a profile is three tables deep
    (`power.high.claude.model`), so a TOML echo only reproduces the file they already
    have, while one line per leaf is greppable and diffable against another profile.
    """
    lines: list[tuple[str, Any]] = []
    for key, value in table.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            lines.extend(_flatten(value, f"{path}."))
        else:
            lines.append((path, value))
    return lines


def _dispatch_config(args: argparse.Namespace) -> int:
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
                f"error: {root} is not a usable base library directory — it must contain library/."
            )
        write_base_dir(root)
        print(f"base_dir={root}")
        return 0

    # show — with a key: print bare value; without: print all as key=value
    cfg = read_config()
    if args.profile:
        # Narrowed to the profile and flattened, because that is the shape of the answer:
        # a profile replaces the top-level tables rather than layering over them, so what
        # is printed here is the whole config a run on `--profile <name>` resolves from,
        # not a fragment to be read against the file around it.
        entries = dict(_flatten(select_profile(cfg, args.profile)))
    else:
        entries = dict(cfg)
    if args.key:
        value = entries.get(args.key)
        if value is None:
            where = f" profile '{args.profile}' of" if args.profile else ""
            raise SystemExit(f"error: '{args.key}' is not set in{where} {config_path()}")
        print(value)
    else:
        for key, value in entries.items():
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
    this file's directory, and turns its installed skill and prompt names into
    library source paths with the same selection/prefix machinery install uses.
    AGENTS.md and its CLAUDE.md pointer come from the same mapping, so both names
    resolve to the same sources; when two mappings claim a directory the last one
    wins, mirroring install.

    Returns library-relative source paths; None when the file is not a local
    instruction file or no agents.yml exists above it (caller may fall back to
    the banner); exits when agents.yml exists but no longer maps this file —
    the file is stale, and pointing at its old sources would invite edits that
    the next install silently discards.
    """
    if generated.name not in LOCAL_INSTRUCTION_FILES:
        return None
    config_path = find_agents_config(generated.parent)
    if config_path is None:
        return None
    repo = config_path.parent
    config = read_yaml(config_path)
    directory = generated.parent
    skill_names: list[str] = []
    prompt_names: list[str] = []
    for mapping in config.get("localInstructions", []) or []:
        for rel in mapping.get("paths", []) or []:
            if (repo / rel).resolve() == directory:
                skill_names = mapping_skill_names(mapping)
                prompt_names = mapping_prompt_names(mapping)
    if not skill_names and not prompt_names:
        raise SystemExit(
            f"error: {generated} is not mapped by {config_path} → "
            "localInstructions — the mapping was removed or moved, so this file "
            "is stale. Re-run `farrier --repo .` (or `make agent-install`) to "
            "regenerate or remove it."
        )
    repo_config = config.get("repo") or {}
    prefix = repo_prefix(repo)
    include_skills, include_prompts, _, _ = collect_selection(config)
    exclude = config.get("exclude") or {}
    skills = selected_sources(
        load_layered_sources("skill", "library", "skills"),
        include_skills,
        set(exclude.get("skills", []) or []),
    )
    prompts = selected_sources(
        load_layered_sources("prompt", "library", "prompts"),
        include_prompts,
        set(exclude.get("prompts", []) or []),
    )
    renderer = Renderer(repo, prefix, repo_config, {}, skills, prompts)
    return [
        library_source_path(renderer.skill_source(name)) for name in skill_names
    ] + [
        library_source_path(renderer.prompt_source(name)) for name in prompt_names
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
    # A bundled markdown reference has no front matter of its own and is not a local
    # instruction file either; its banner is its only provenance, and unlike a stale
    # localInstructions mapping there is nothing live it could disagree with.
    rel_source = frontmatter_metadata(text).get("source")
    if rel_source:
        rel_sources = [rel_source]
    else:
        rel_sources = mapped_instruction_sources(generated)
        if rel_sources is None:
            rel_sources = banner_sources(text)
            if rel_sources and generated.name in LOCAL_INSTRUCTION_FILES:
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

    # init
    init_p = sub.add_parser(
        "init",
        help="Write a starter agents.yml so this repository can be configured",
    )
    init_p.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root to write agents.yml into (default: cwd)",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing agents.yml instead of refusing",
    )

    # install (default)
    install_p = sub.add_parser(
        "install", help="Render/install the selected packs into a repository (default)"
    )
    _add_install_args(install_p)

    # config
    config_p = sub.add_parser("config", help="Manage the farrier home config")
    config_p.add_argument(
        "--config",
        dest="config_file",
        type=Path,
        metavar="PATH",
        help="Read and write this config file instead of the home one (also $"
        + CONFIG_PATH_ENV
        + "). Goes before the action: `farrier config --config ./c.toml show`",
    )
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
    show_p.add_argument(
        "--profile",
        default="",
        metavar="NAME",
        help="Show the named [profiles.NAME] table instead of the top level, flattened "
        "to dotted keys (power.high.claude.model=opus). A profile replaces the top "
        "level rather than layering over it, so this is the whole config a run on "
        "--profile NAME resolves from",
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

    # workflows
    workflows_p = sub.add_parser(
        "workflows",
        help="List the workflows installed on this machine (from pipx)",
    )
    workflows_p.add_argument(
        "--names",
        action="store_true",
        help="Print just the names, space-separated — the form the generated "
             "launcher reads at make time.",
    )

    # library
    library_p = sub.add_parser(
        "library",
        help="Validate the library's own sources (front matter, tags)",
    )
    library_p.add_argument(
        "--check",
        action="store_true",
        help="Report front-matter problems and exit non-zero on any error. "
             "Currently the only mode, and required so the verb reads the same as "
             "`agent-check` in a Makefile.",
    )
    library_p.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings (untagged skills, fragile unquoted values) as errors.",
    )
    library_p.add_argument(
        "--library",
        type=Path,
        help="Library directory (agents/ tree). Overrides $FARRIER_LIBRARY_DIR and the home config.",
    )

    # version
    sub.add_parser("version", help="Print the installed farrier version")

    return parser


def _run_library(args: argparse.Namespace) -> int:
    """`farrier library --check` — the gate on the library's own front matter.

    Checks every layer in the resolution stack, not just the overlay: a base-library
    skill with a broken fence fails in exactly the same silent way, and the operator
    running this cannot tell which layer a given skill came from without being told.
    """
    if not args.check:
        raise SystemExit("error: `farrier library` needs --check (the only mode today)")
    set_layers(resolve_library_dir(args.library))
    if not LAYERS:
        raise SystemExit(
            "error: no library layers to check — none configured, and no base library "
            "installed. Set one with `farrier config set-library <path>`."
        )
    # A stack that names the same directory twice is one library, not two — which is how
    # a repo pins this gate to its own library regardless of what the operator has
    # configured: point both the overlay and $STABLEMATE_BASE_DIR at it, and the two
    # entries collapse to a single pass over a single, machine-independent set of files.
    roots: list[Path] = []
    for layer in LAYERS:
        root = (layer.root / "library").resolve()
        if root in roots:
            continue
        roots.append(root)
        print(f"# layer: {layer.name}")
    findings, checked = check_library(roots)
    print(format_findings(findings, checked))
    levels = {"error"} if not args.strict else {"error", "warning"}
    return 1 if any(f.level in levels for f in findings) else 0


def _run_workflows(args: argparse.Namespace) -> int:
    """`farrier workflows` — what this machine can run, and where it came from.

    `--names` is the machine-readable form, and it is why this command exists: the
    generated launcher resolves its run targets by calling it at **make** time
    rather than having farrier bake the list into `.agents/agents.mk`. A baked list
    would be a tracked file whose content differs per developer — and, for a local
    install, one carrying somebody's home directory into the repo.
    """
    found = pipx.discover()

    if args.names:
        # Space-separated on one line: make's `$(shell …)` collapses newlines to
        # spaces anyway, and this keeps the empty case an empty line rather than a
        # stray one.
        print(" ".join(pipx.names(found)))
        return 0

    if not found:
        print(
            "No workflows installed. Install a workflow distribution "
            "(e.g. `pipx install workhorse-workflows`) and they appear here."
        )
        return 0

    for dist in found:
        origin = dist.origin or "?"
        if dist.local_path is not None:
            origin = f"{dist.local_path}{' (editable)' if dist.editable else ''}"
            if dist.missing:
                origin += "  ** source directory is gone **"
        print(f"{dist.distribution} {dist.version}  <- {origin}")
        for workflow in dist.workflows:
            print(f"    {workflow}")

    # A stale editable install is worth an exit code: it still *runs* here, so
    # nothing else will report it until a container tries to bind the path.
    return 1 if any(dist.missing for dist in found) else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = _build_parser()

    # Keep `farrier --repo .` working: if no recognised subcommand is given,
    # inject `install` so existing invocations are unchanged.
    # Exceptions: bare --help/-h shows the top-level subcommand listing, and so does
    # a bare `farrier`. Nothing else on this CLI mutates a repository without being
    # named, and "render every adapter file into whatever directory I happen to be
    # standing in" is the last default a bare invocation should have — the verbs are
    # what someone typing `farrier` alone is looking for.
    _SUBCOMMANDS = {
        "init",
        "install",
        "config",
        "version",
        "source",
        "scaffold",
        "workflows",
        "library",
    }
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0
    if argv[0] not in _SUBCOMMANDS:
        argv = ["install"] + argv

    args = parser.parse_args(argv)

    if args.command == "init":
        return _run_init(args)

    if args.command == "version":
        print(importlib.metadata.version("farrier"))
        return 0

    if args.command == "config":
        return _run_config(args)

    if args.command == "source":
        return _run_source(args)

    if args.command == "scaffold":
        return _run_scaffold(args)

    if args.command == "workflows":
        return _run_workflows(args)

    if args.command == "library":
        return _run_library(args)

    return _run_install(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
