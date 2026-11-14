"""A named happening one service puts out and another hears: its name, the source it comes from
and the shape of what it carries. The emitter's book declares it once; an action says `emits`,
and an outside event says `heard`."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ostler.book.errors import BookError

if TYPE_CHECKING:
    from ostler.book.http import Object


def bare(path: str) -> str:
    return path.replace("[]", "").replace("{}", "")


class Event:
    """Subclass per event. `name` is what travels, `detail` the object it carries. An event whose emitter
    has no book under the root is declared by its listener, with `owner` saying who emits it."""

    name: ClassVar[str] = ""
    source: ClassVar[str] = ""
    detail: ClassVar[Object | None] = None
    owner: ClassVar[str] = ""

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        from ostler.book.http import Object

        if not cls.name:
            raise BookError(f"{cls.__name__} has no name: set name = '<what the bus carries>', for example name = 'ticket.changed'")
        if not isinstance(cls.detail, Object):
            raise BookError(f"{cls.__name__} has no detail: set detail = Object(<field>=Field(<shape>), ...) for what the event carries")
        if not (cls.__dict__.get("__doc__") or "").strip():
            raise BookError(f"{cls.__name__} has no docstring: say in one line what happened")

    @classmethod
    def paths(cls) -> set[str]:
        from ostler.book.http import declared_paths

        return {bare(p) for p in declared_paths(cls.detail)}
