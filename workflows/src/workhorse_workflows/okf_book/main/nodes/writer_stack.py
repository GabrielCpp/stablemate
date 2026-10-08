"""The stack the writer's checks share in one turn: the first check brings it up, the next ones adopt it, and the turn's end releases it."""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.book_run import StackReadiness, book_runbooks, bring_up, release, stack_pages

KEPT_NAME = "writer-stack.json"


class _Kept(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runbooks: str
    owned: tuple[str, ...]
    app_logs: tuple[str, ...] = ()


def runbooks_digest(root: Path, service: str) -> str:
    """What changes whenever a runbook page the service's stack starts from is written."""
    digest = hashlib.sha256()
    for page in stack_pages(root, service):
        path = root / page
        digest.update(f"{page}\0".encode())
        digest.update(path.read_bytes() if path.is_file() else b"")
    return digest.hexdigest()


def _group_alive(pgid: str) -> bool:
    try:
        os.killpg(int(pgid), 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True, slots=True)
class KeptStack:
    """The stack kept up in `folder` across a turn's checks, which `logger` reports bringing up and releasing."""

    folder: Path
    logger: logging.Logger

    @property
    def path(self) -> Path:
        return self.folder / KEPT_NAME

    def _read(self) -> _Kept | None:
        return _Kept.model_validate_json(self.path.read_text(encoding="utf-8")) if self.path.is_file() else None

    def up(self, root: Path, service: str) -> StackReadiness:
        """The stack a check runs on: the one an earlier check of the turn left up, while it lives and its runbooks are unchanged, or else one brought up now."""
        runbooks = runbooks_digest(root, service)
        kept = self._read()
        if kept is not None and kept.runbooks == runbooks and all(_group_alive(pgid) for pgid in kept.owned):
            return StackReadiness(up=True, serving=True, notes="", app_logs=kept.app_logs, runbooks=book_runbooks(root, service))
        self.release()
        stack = bring_up(self.logger, root, service)
        if stack.serving and stack.owned:
            _ = self.path.write_text(_Kept(runbooks=runbooks, owned=stack.owned, app_logs=stack.app_logs).model_dump_json(), encoding="utf-8")
            return StackReadiness(up=True, serving=True, notes=stack.notes, app_logs=stack.app_logs, runbooks=stack.runbooks)
        return stack

    def release(self) -> None:
        """Stop the stack the turn's checks kept up, so the next bring-up finds the app's ports free."""
        kept = self._read()
        if kept is None:
            return
        release(self.logger, StackReadiness(up=True, serving=True, notes="", owned=kept.owned))
        self.path.unlink(missing_ok=True)
