"""The label a screen names a thing by: one text per language the app speaks, or one text for every language."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book.errors import BookError


@dataclass(frozen=True, init=False)
class T:
    """A label: one text per language the app speaks, or one text that reads the same in each."""

    same: str | None
    texts: tuple[tuple[str, str], ...]

    def __init__(self, *same: str, **texts: str) -> None:
        if len(same) > 1:
            raise BookError(f"a label names each language, as in T(<language>={same[0]!r}, ...); it got {len(same)} bare texts")
        if bool(same) == bool(texts):
            raise BookError("a label is one bare text, or one text per language by name")
        object.__setattr__(self, "same", same[0] if same else None)
        object.__setattr__(self, "texts", tuple(sorted(texts.items())))

    def __getitem__(self, lang: str) -> str:
        if self.same is not None:
            return self.same
        for name, text in self.texts:
            if name == lang:
                return text
        raise BookError(f"the label {self.texts[0][1]!r} has no text in {lang!r}")

    def languages(self) -> frozenset[str] | None:
        """The languages it names, or None when it reads the same in each."""
        return None if self.same is not None else frozenset(name for name, _ in self.texts)


def as_label(text: T | str | None) -> T | None:
    return T(text) if isinstance(text, str) else text
