"""The book as a repair turn found it — the "before" a turn reads its own change against."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Baseline


@blueprint.node
def snapshot_book(logger: logging.Logger, features_root: str, dest: str) -> Baseline:
    """Replace `dest` with a copy of the book under `features_root`, as it stands now."""
    book, target = Path(features_root), Path(dest)
    if target.exists():
        shutil.rmtree(target)
    if book.is_dir():
        shutil.copytree(book, target)
    else:
        target.mkdir(parents=True)
    logger.info("turn baseline of %s at %s", book, target)
    return Baseline(path=str(target))


__all__ = ["snapshot_book"]
