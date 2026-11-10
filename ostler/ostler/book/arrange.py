"""Something that happens to the service from outside its surface: mail lands,
a nightly job runs, a record is seeded. No caller takes it, so it carries no
caller. The surface performs it by its own means and the model reduces the
action it carries."""

from __future__ import annotations

from typing import Any, ClassVar, Generic, TypeVar

from ostler.book.domain import Action

F = TypeVar("F")


class Arrange(Generic[F]):
    """Subclass per outside event. The class body says what happens and the
    action it carries; an instance is one occurrence, aimed at the fixture it
    brings."""

    does: ClassVar[str] = ""
    carries: ClassVar[type[Action[Any, Any]] | None] = None
    by: None = None

    def __init__(self, of: F | None = None):
        self.of = of

    def input(self) -> F | None:
        return self.of

    @classmethod
    def describe(cls) -> str:
        accept = cls.carries.accept if cls.carries is not None else None
        takes = accept.__name__ if accept is not None else "nothing"
        return f"{cls.__name__:12} outside the surface takes {takes:8} {cls.does}".rstrip()

    def __str__(self) -> str:
        return type(self).__name__ + (f" {self.of}" if self.of is not None else "")
