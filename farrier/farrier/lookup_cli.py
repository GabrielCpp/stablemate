"""`farrier state-dir` and `farrier policies path`: the lookups a script or a hook asks farrier for."""

from __future__ import annotations

import argparse
from pathlib import Path

from farrier._vendor.stablemate_core.schema import Manifest
from farrier import layers
from farrier.layers import resolve_library_dir, set_layers
from farrier.manifest import locate_manifest, read_manifest
from farrier.sources import build_policy_lookup, load_layered_sources
from farrier.state import repo_state_dir

LOOKUP_COMMANDS = ("state-dir", "policies")


def add_lookup_parsers(sub) -> None:
    state_p = sub.add_parser(
        "state-dir",
        help="Print the per-user folder farrier keeps this repository's context manifests in",
    )
    state_p.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd)",
    )

    policies_p = sub.add_parser("policies", help="Look up a library policy")
    policies_sub = policies_p.add_subparsers(dest="policies_action", required=True)
    path_p = policies_sub.add_parser(
        "path",
        help="Print the library folder holding a policy, or nothing when no layer has it",
    )
    path_p.add_argument("name", help="The policy's library name")


def run_lookup(args: argparse.Namespace) -> int:
    if args.command == "state-dir":
        return _run_state_dir(args)
    return _run_policies_path(args)


def _run_policies_path(args: argparse.Namespace) -> int:
    """`farrier policies path <name>` — where the layer stack keeps one policy, for a hook to run its script from."""
    try:
        set_layers(resolve_library_dir(None))
    except SystemExit:
        return 0
    if not layers.LAYERS:
        return 0
    lookup = build_policy_lookup(load_layered_sources("policy", "library", "policies"))
    source = lookup.get(args.name.replace(".", "-"))
    if source is not None:
        print(source.path.parent)
    return 0


def _run_state_dir(args: argparse.Namespace) -> int:
    """`farrier state-dir` — where this repository's generated machine state lives."""
    repo = args.repo.resolve()
    config_file = locate_manifest(repo)
    config = read_manifest(config_file) if config_file else Manifest()
    print(repo_state_dir(repo, config.repo.mapping()))
    return 0
