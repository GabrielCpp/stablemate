"""`dot` — render the workflow's state machine as Graphviz DOT."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workhorse.pyflow.dot import to_dot
from workhorse.pyflow.graph import registry_graphs

NAME = "dot"
HELP = "Render this workflow's graph to Graphviz DOT"


def add_arguments(parser: argparse.ArgumentParser) -> None:
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
    """Render the workflow's state machine as DOT, one cluster per flow.

    *Which* workflow is not a question this command asks: it is whichever one's console
    script started the process, and its registry arrives on the namespace."""
    registry = args.registry
    dot = to_dot(registry_graphs(registry), name=args.name or registry.name)

    if args.output:
        Path(args.output).write_text(dot)
        print(f"[workhorse] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(dot)
