"""The complete read: every record the register holds."""
from __future__ import annotations

import logging

from ostler import Ostler, register
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.review_debt.nodes._blueprint import blueprint
from workhorse_workflows.review_debt.schemas import CompleteRead


def _three_records(*_args: object, **_kwargs: object) -> CompleteRead:
    """`read_register` under `--dry-run`: a register big enough to walk every state, down to a filed decision."""
    ids = ["dry-run-1", "dry-run-2", "dry-run-3"]
    return CompleteRead(ids=ids, listing=ids, shelf="dry-run")


@blueprint.node(stub=_three_records)
def read_register(logger: logging.Logger, repo_dir: str = "") -> CompleteRead:
    """Read every parseable record of every status in every repository, and name the files that did not parse."""
    okf = Ostler(find_docs_root(repo_dir))
    found = okf.records()
    for path in found.unreadable:
        logger.warning("record file unreadable, not reviewed: %s", path)
    return CompleteRead(
        ids=[r.id for r in found.records],
        listing=register.listing(found.records),
        shelf=str(okf.register_root()),
        unreadable=[str(p) for p in found.unreadable],
    )
