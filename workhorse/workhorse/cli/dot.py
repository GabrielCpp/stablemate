"""`workhorse dot` — render a workflow's state machine as Graphviz DOT."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workhorse.cli.resolve import packaged_registry
from workhorse.pyflow.dot import to_dot
from workhorse.pyflow.graph import registry_graphs

NAME = "dot"
HELP = "Render a workflow graph to Graphviz DOT"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow",
        default=None,
        help="The workflow NAME, resolved the same way `run` resolves one. Rendered "
        "from its states, one cluster per flow.",
    )
    parser.add_argument(
        "positional",
        nargs="*",
        help="Positional form of --workflow: `workhorse dot <name>`.",
    )
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="Override the digraph identifier (default: sanitized workflow name).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Write the DOT output to this file (default: stdout).",
    )


def run(args: argparse.Namespace) -> None:
    """Render a workflow's state machine as DOT, one cluster per flow."""
    spec = _spec(args)
    registry = getattr(args, "registry", None) or packaged_registry(spec)
    dot = to_dot(registry_graphs(registry), name=args.name or registry.name)

    if args.output:
        Path(args.output).write_text(dot)
        print(f"[workhorse] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(dot)


def _spec(args: argparse.Namespace) -> str:
    """The workflow `dot` was asked for, from --workflow or the positional form."""
    positional = list(getattr(args, "positional", None) or [])
    spec = args.workflow or (positional.pop(0) if positional else None)
    if positional:
        print(f"error: unexpected argument '{positional[0]}'", file=sys.stderr)
        sys.exit(1)
    if not spec:
        print("error: dot needs a workflow name", file=sys.stderr)
        sys.exit(1)
    return spec
