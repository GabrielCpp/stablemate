"""What a screen is in and how it moves: the page sizes it plays at, the states a component shows, and the phases and
transitions a screen declares."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from ostler.book.errors import BookError

if TYPE_CHECKING:
    from ostler.book.screen import Component


@dataclass(frozen=True)
class Viewport:
    """A page size a step plays at, such as a phone's. The app lays its pages out for it, and a phase may hold only there."""

    name: str
    width: int
    height: int


@dataclass(frozen=True)
class Aspect:
    """A state of a component the book names and the run reads: open or closed, valid or not, which choice is picked.
    `attribute` is the attribute it reads, such as `aria-expanded`. `checked` and `picked` need none: the run reads
    whether a check is ticked, and which choice a select or a set of radios shows picked."""

    name: str
    attribute: str = ""

    def __post_init__(self) -> None:
        if not self.attribute and self.name not in ("checked", "picked"):
            raise BookError(f"the aspect {self.name!r} names the attribute it reads, such as attribute='aria-pressed'")


EXPANDED = Aspect("expanded", "aria-expanded")
INVALID = Aspect("invalid", "aria-invalid")
CHECKED = Aspect("checked")
PICKED = Aspect("picked")


@dataclass(frozen=True)
class Is:
    """A claim that a component is in a state, as `Is(menu, EXPANDED, "false")`. `value` is the text the run reads, or a
    function of the model and the person looking that returns it, with a docstring that says what it reads."""

    component: Component
    aspect: Aspect
    value: str | Callable[[Any, Any], str]

    def __post_init__(self) -> None:
        if callable(self.value) and not (self.value.__doc__ or "").strip():
            raise BookError(f"the value of {self.aspect.name} on {self.component.label or self.component.id} has no docstring: "
                            "its first line says what the state reads")

    def wanted(self, model: Any, by: Any) -> str:
        return self.value if isinstance(self.value, str) else self.value(model, by)

    def text(self, lang: str) -> str:
        said = (getattr(self.value, "__doc__", "") or "").strip().splitlines()[0] if callable(self.value) else repr(self.value)
        return f"{self.component.found_by(lang)} {self.aspect.name} {said}"


@dataclass(frozen=True)
class Condition:
    """When a phase holds, in the product's words. `holds` reads the model and the person looking; `viewport` holds only
    when the step played at that size. Each one given must hold."""

    says: str
    holds: Callable[[Any, Any], bool] | None = None
    viewport: Viewport | None = None

    def met(self, model: Any, by: Any, at: Viewport | None) -> bool:
        if self.viewport is not None and self.viewport != at:
            return False
        return self.holds is None or bool(self.holds(model, by))


@dataclass(frozen=True)
class Stored:
    """One value the screen keeps in memory (a useState, a field of a State
    object) with the type of value acceptable there."""

    name: str
    accepts: str
    initial: str


@dataclass(frozen=True)
class Phase:
    """A state of the screen: what is shown, what is disabled, the states its components are in, and why. A phase with
    `when` is a claim: each time a step lands on the screen and the condition holds, the run checks every part of it."""

    name: str
    shows: tuple[Component, ...] = ()
    hides: tuple[Component, ...] = ()
    disabled: tuple[Component, ...] = ()
    because: str = ""
    when: Condition | None = None
    states: tuple[Is, ...] = ()

    def __post_init__(self) -> None:
        if self.states and self.when is None:
            raise BookError(f"the phase {self.name!r} claims states and says not when it holds: give it when=Condition(...)")


@dataclass(frozen=True)
class When:
    """The trigger of a transition: a component acted on, or an answer arriving."""

    what: str
    on: Component | None = None

    def text(self, lang: str) -> str:
        return f"{self.what} {self.on.found_by(lang)}" if self.on else self.what


@dataclass(frozen=True)
class Transition:
    start: Phase
    when: When
    end: Phase
    only_if: str = ""
    then: str = ""

    def text(self, lang: str) -> str:
        guard = f" only if {self.only_if}" if self.only_if else ""
        effect = f"; {self.then}" if self.then else ""
        return f"{self.start.name} --[{self.when.text(lang)}{guard}]--> {self.end.name}{effect}"
