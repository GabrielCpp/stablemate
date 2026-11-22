"""Boot the device and install the app each book's stack.yml names."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ostler._vendor.stablemate_core import books
from ostler.environments import spec as spec_mod
from ostler.qa import addresses
from ostler.qa import stack as stack_mod


class WorkingDirectoryError(ValueError):
    """A `working-directory:` names a workspace member this run does not have."""


def resolve_directory(root: Path, value: str, code: Path | None = None) -> Path:
    """Where a `working-directory:` value points: `repo://<member>/<path>` in that member's checkout, anything else under *root*."""
    if not value.startswith("repo://"):
        return (root / value).resolve()
    member, _slash, rest = value.removeprefix("repo://").partition("/")
    checkouts = books.book_checkouts(code or root)
    checkout = checkouts.get(member)
    if checkout is None:
        known = ", ".join(sorted(checkouts)) or "none"
        msg = (f"`working-directory: {value}` names workspace member {member!r}, "
               f"and this run's members are: {known}")
        raise WorkingDirectoryError(msg)
    return (checkout / (rest or ".")).resolve()


def bring_up_stacks(manifests: list[dict[str, Any]], *, repo_root: str,
                    logger: logging.Logger | None = None) -> list[dict[str, Any]]:
    """Bring every manifest up in document order, stopping at the first that fails."""
    log = logger or logging.getLogger(__name__)
    results: list[dict[str, Any]] = []
    for manifest in manifests:
        result = stack_mod.ensure_stack(
            manifest, repo_root=manifest.get("repo_root", repo_root), logger=log)
        results.append({**result, "manifest": manifest, "source": manifest.get("source", "")})
        if result.get("ready") != "yes":
            break
    return results


def bring_up_book_devices(root: Path, *, near: Path | None = None,
                          env: Mapping[str, str] | None = None, code: Path | None = None,
                          logger: logging.Logger | None = None) -> list[dict[str, Any]]:
    """Boot the device and install the app for each book whose `stack.yml` declares `device:` steps, read from the books alone."""
    manifests = _device_manifests(root, near, code)
    if not manifests:
        return []
    with addresses.leased(env or {}):
        return bring_up_stacks(manifests, repo_root=str(root), logger=logger)


def _device_manifests(root: Path, near: Path | None, code: Path | None = None) -> list[dict[str, Any]]:
    books = [book for book in spec_mod.load(root).books.values() if book.device]
    if near is not None:
        where = near if near.is_absolute() else root / near
        books = [book for book in books if where.resolve().is_relative_to(book.directory.resolve())] or books
    return [{"source": book.name, "app_cwd": str(root), "repo_root": str(root),
             "stack_file": str((book.ops_dir / spec_mod.STACK_FILE).relative_to(root)),
             "prepare": [_device_step(root, step, code) for step in book.device]} for book in books]


def _device_step(root: Path, step: dict[str, Any], code: Path | None = None) -> dict[str, Any]:
    command = {"run": step["run"],
               "working-directory": str(resolve_directory(root, step.get("working-directory", "."), code))}
    if step.get("name"):
        command["name"] = str(step["name"])
    if "timeout" in step:
        command["timeout"] = str(step["timeout"])
    return command
