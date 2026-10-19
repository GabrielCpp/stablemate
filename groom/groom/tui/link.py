from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

Frame = dict[str, Any]


class LinkError(Exception):
    pass


class Link(Protocol):
    async def open(self) -> None: ...

    def frames(self) -> AsyncIterator[Frame]: ...

    async def send(self, command: Frame) -> bool: ...

    async def get(self, path: str) -> Frame: ...

    async def get_list(self, path: str) -> list[Frame]: ...

    async def post(self, path: str, body: Frame | None = None) -> Frame: ...

    async def delete(self, path: str) -> Frame: ...

    async def close(self) -> None: ...
