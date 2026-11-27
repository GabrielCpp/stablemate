"""The checks a loaded catalog's services must pass as a graph: every need exists, no needs form a cycle, and no service
is defined or published twice."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ostler.environments.spec import Catalog


def check_needs(catalog: Catalog) -> None:
    for service in catalog.services.values():
        for need in service.needs:
            if need not in catalog.services:
                catalog.errors.append(f"{service.ref} needs `{need}`, which no book defines")


def check_cycles(catalog: Catalog) -> None:
    state: dict[str, int] = {}

    def visit(ref: str, trail: list[str]) -> None:
        state[ref] = 1
        for need in catalog.services[ref].needs:
            if need not in catalog.services:
                continue
            if state.get(need) == 1:
                cycle = [*trail[trail.index(need):], need] if need in trail else [ref, need]
                catalog.errors.append(f"the needs form a cycle: {' -> '.join(cycle)}")
            elif need not in state:
                visit(need, [*trail, need])
        state[ref] = 2

    for ref in sorted(catalog.services):
        if ref not in state:
            visit(ref, [ref])


def check_shared(catalog: Catalog) -> None:
    by_define: dict[Path, str] = {}
    by_address: dict[str, str] = {}
    for ref, service in sorted(catalog.services.items()):
        other = by_define.setdefault(service.define.resolve(), ref)
        if other != ref:
            catalog.errors.append(
                f"{ref} and {other} are both defined by `{service.define.name}`: define it once "
                f"and name it in the other book's `needs:`")
        if service.address:
            owner = by_address.setdefault(service.address, ref)
            if owner != ref:
                catalog.errors.append(f"{ref} and {owner} both publish `{service.address}`")
