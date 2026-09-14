"""The book as a repair turn found it — the "before" a turn reads its own change against.

The drain commits only a completed book, so while a run heals, every repair it has landed
is uncommitted and `HEAD` is hours older than the tree. A turn that asks git what *it*
changed (`git diff`, `git show HEAD:<path>`) is shown every earlier repair of the run as
well, and a real turn took that for damage done by `ostler fmt` and copied `HEAD` back over
the file — erasing five repairs the run had already paid for. Nothing recorded the file as
the turn found it, so no instruction could name the right "before".

This node records it: a copy of the book taken immediately before the turn, replaced on the
next one. The repair prompts point the turn at it for "what did I change" and "undo my edit".
"""
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
