"""`workhorse-new`: write a standalone workflow distribution that loops an agent until a check passes."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template"

NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")


def package_name(name: str) -> str:
    """The import name of the package a workflow called `name` lives in."""
    return name.replace("-", "_")


def _destination(relative: Path, package: str) -> Path:
    parts = list(relative.parts)
    if parts[0] == "package":
        parts = ["src", package, *parts[1:]]
    if parts[-1].endswith(".tmpl"):
        parts[-1] = parts[-1].removesuffix(".tmpl")
    return Path(*parts)


def _render(text: str, *, name: str, package: str, check: str, python: bool) -> str:
    if python:
        text = text.replace('"__CHECK__"', json.dumps(check, ensure_ascii=False))
    return (
        text.replace("__CHECK__", check)
        .replace("__WORKFLOW_NAME__", name)
        .replace("__PACKAGE__", package)
    )


def _template_files() -> list[Path]:
    return sorted(
        path
        for path in TEMPLATE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def scaffold(name: str, check: str, parent: Path) -> Path:
    """Write the `name` distribution into `parent / name`, and refuse if that path exists."""
    if not NAME.fullmatch(name):
        raise ValueError(
            f"{name!r} is not a workflow name: use lowercase letters, digits and single dashes, "
            f"starting with a letter"
        )
    if not check.strip():
        raise ValueError("--check is empty: give the shell command that decides when the work is done")
    target = parent / name
    if target.exists():
        raise FileExistsError(f"{target} already exists; pick another name or remove it")
    package = package_name(name)
    for source in _template_files():
        relative = source.relative_to(TEMPLATE)
        path = target / _destination(relative, package)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        path.write_text(
            _render(text, name=name, package=package, check=check, python=source.suffix == ".py"),
            encoding="utf-8",
        )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="workhorse-new",
        description="Write a workflow that runs an agent turn, then CHECK, and loops until CHECK exits 0.",
    )
    parser.add_argument("name", help="the workflow name, e.g. fix-tests; the command becomes workhorse-NAME")
    parser.add_argument("--check", required=True, help="the shell command that decides when the work is done")
    parser.add_argument(
        "--into",
        default=".",
        metavar="DIR",
        help="the directory to create NAME in (default: the current directory)",
    )
    args = parser.parse_args(argv)
    try:
        target = scaffold(args.name, args.check, Path(args.into))
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {target}")
    print("next:")
    print(f"  uv tool install {target}")
    print(f"  workhorse-{args.name} run --dry-run")
    return 0
