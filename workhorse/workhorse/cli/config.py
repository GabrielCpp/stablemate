"""`workhorse config` — read and write the shared workhorse/farrier home config.

Mirrors farrier's interface so `agents.mk` and scripts can call either tool.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stablemate_core.config import (
    ConfigVersionError,
    config_path,
    get_config_value,
    load_config,
    write_config_key,
)
from stablemate_core.discovery import is_library_dir as _is_base_library_dir

NAME = "config"
HELP = "Manage the workhorse/farrier home config"


def add_arguments(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="config_command", required=True)
    # show [key] — print all keys as key=value lines, or a single bare value (farrier-compatible)
    show_p = sub.add_parser(
        "show", help="Print all config keys as key=value lines, or a single bare value"
    )
    show_p.add_argument(
        "key",
        nargs="?",
        default=None,
        help="If given, print only the value of this key",
    )
    # set-library / set-stablemate — write to the farrier config file (same file farrier reads)
    set_lib_p = sub.add_parser(
        "set-library", help="Record the prompt library directory in the home config"
    )
    set_lib_p.add_argument(
        "path", type=Path, help="Path to the library (the agents/ tree)"
    )
    set_sm_p = sub.add_parser(
        "set-stablemate", help="Record the stablemate checkout path in the home config"
    )
    set_sm_p.add_argument("path", type=Path, help="Path to the stablemate checkout")
    set_base_p = sub.add_parser(
        "set-base",
        help="Record the base library content path (for isolated/pipx installs where "
        "the stablemate-library wheel isn't importable)",
    )
    set_base_p.add_argument(
        "path", type=Path, help="Path to the base library content directory"
    )
    # list / get — workhorse-specific power/model config (workhorse's own config.toml)
    sub.add_parser("list", help="Print the loaded workhorse config (power mappings etc.)")
    get_p = sub.add_parser("get", help="Print one workhorse config value")
    get_p.add_argument("name", help="Config key, e.g. power or power.high.claude")


def run(args: argparse.Namespace) -> None:
    try:
        _dispatch(args)
    except ConfigVersionError as exc:
        # A config written by a newer stablemate-core. Actionable and deterministic, so
        # it exits cleanly like every other config error here rather than as a traceback.
        raise SystemExit(f"error: {exc}") from exc


def _dispatch(args: argparse.Namespace) -> None:
    if args.config_command == "set-library":
        path = Path(args.path).expanduser().resolve()
        write_config_key("library_dir", str(path))
        print(f"library_dir={path}")
        return

    if args.config_command == "set-stablemate":
        path = Path(args.path).expanduser().resolve()
        write_config_key("stablemate_dir", str(path))
        print(f"stablemate_dir={path}")
        return

    if args.config_command == "set-base":
        path = Path(args.path).expanduser().resolve()
        if not _is_base_library_dir(path):
            raise SystemExit(
                f"error: {path} is not a usable base library directory — it must contain library/."
            )
        write_config_key("base_dir", str(path))
        print(f"base_dir={path}")
        return

    cfg = load_config()

    if args.config_command == "show":
        if args.key:
            value = cfg.get(args.key)
            if value is None:
                print(
                    f"error: '{args.key}' is not set in {config_path()}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(value)
        else:
            for key, value in cfg.items():
                print(f"{key}={value}")
        return

    if args.config_command == "list":
        print(f"# {config_path()}")
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return

    if args.config_command == "get":
        value = get_config_value(args.name, cfg)
        if value is None:
            return
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2, sort_keys=True))
        else:
            print(value)
