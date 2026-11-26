"""The named lock a task holds for its whole round."""

from __future__ import annotations

import fcntl
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from paddock import paths

LOCK_FILE_ENV = "PADDOCK_LOCK_FILE"


@contextmanager
def hold_lock(name: str | None) -> Iterator[Path | None]:
    """Hold an exclusive flock on the named lock file, waiting while another process has it."""
    if name is None:
        yield None
        return
    path = paths.lock_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"paddock: round is waiting for {name}", file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        saved = os.environ.get(LOCK_FILE_ENV)
        os.environ[LOCK_FILE_ENV] = str(path)
        try:
            yield path
        finally:
            if saved is None:
                os.environ.pop(LOCK_FILE_ENV, None)
            else:
                os.environ[LOCK_FILE_ENV] = saved
            fcntl.flock(handle, fcntl.LOCK_UN)
