"""`farrier policies path`: the lookup a script or a hook asks farrier for."""

from __future__ import annotations

import argparse

from farrier import layers
from farrier.layers import resolve_library_dir, set_layers
from farrier.sources import build_policy_lookup, load_layered_sources

LOOKUP_COMMANDS = ("policies",)


def add_lookup_parsers(sub) -> None:
    policies_p = sub.add_parser("policies", help="Look up a library policy")
    policies_sub = policies_p.add_subparsers(dest="policies_action", required=True)
    path_p = policies_sub.add_parser(
        "path",
        help="Print the library folder holding a policy, or nothing when no layer has it",
    )
    path_p.add_argument("name", help="The policy's library name")


def run_lookup(args: argparse.Namespace) -> int:
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

