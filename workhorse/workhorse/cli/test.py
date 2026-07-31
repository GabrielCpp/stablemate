"""`workhorse test` — run a workflow's own pytest suite."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

NAME = "test"
HELP = "Run pytest tests from a workflow's tests/ directory"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "workflow_dir",
        help="Directory containing the workflow package and a tests/ subdirectory",
    )
    parser.add_argument(
        "--filter",
        "-k",
        default=None,
        metavar="PATTERN",
        help="Only run tests matching this pytest -k expression",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Pass -v to pytest for verbose output",
    )


def run(args: argparse.Namespace) -> None:
    workflow_dir = Path(args.workflow_dir).resolve()
    tests_dir = workflow_dir / "tests"
    if not tests_dir.is_dir():
        print(f"error: no tests/ directory found in {workflow_dir}", file=sys.stderr)
        sys.exit(1)
    try:
        # Genuinely absent in a normal install — workhorse runs workflows without it,
        # and only this command needs it. The handler is what makes the deferral honest.
        import pytest as _pytest  # noqa: PLC0415
    except ImportError:
        print(
            "error: pytest is required to run workflow tests.\n"
            "Install it with: pip install 'workhorse-agent[test]'",
            file=sys.stderr,
        )
        sys.exit(1)
    pytest_args = [str(tests_dir)]
    if args.filter:
        pytest_args += ["-k", args.filter]
    if args.verbose:
        pytest_args += ["-v"]
    sys.exit(_pytest.main(pytest_args))
