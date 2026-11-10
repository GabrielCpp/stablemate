"""Screens as a reader and a driver both see them: components with their
accessibility id and labels, what the screen stores, the phases it moves
through and the transitions between them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Generic, TypeVar, cast

from ostler.book.cast import KEEP, SOLE, Actor
from ostler.book.domain import Action
from ostler.book.errors import BookError


@dataclass(frozen=True)
class T:
    """A label in every language the app speaks."""

    en: str
    fr: str

    def __getitem__(self, lang: str) -> str:
        return getattr(self, lang)


ROLES = {
    "field": "textbox",
    "textarea": "textbox",
    "date": "textbox",
    "button": "button",
    "select": "combobox",
    "check": "checkbox",
    "heading": "heading",
    "menuitem": "menuitem",
    "link": "link",
    "option": "option",
    "banner": "alert",
    "spinner": "progressbar",
}


@dataclass(frozen=True)
class Component:
    """One thing on a screen. `id` is the accessibility handle a driver finds it
    by (data-testid on the web, a semantics identifier in Flutter). Without an
    id the driver finds it by role and label, as a user would."""

    id: str | None
    kind: str
    label: T | None = None
    does: str = ""
    options: tuple[T, ...] = ()
    per_row: bool = False

    def __post_init__(self) -> None:
        if self.id is None and self.label is None:
            raise BookError(f"a {self.kind} component has neither an id nor a label")

    def found_by(self, lang: str = "en") -> str:
        """How a driver finds this component: its id, or its role and name."""
        if self.id is not None:
            return self.id
        assert self.label is not None
        role = ROLES.get(self.kind)
        name = self.label[lang]
        return f"text {name!r}" if role is None else f"{role} {name!r}"


def Field(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "field", label, does)


def TextArea(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "textarea", label, does)


def DateField(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "date", label, does)


def Select(id: str | None, label: T, options: tuple[T, ...], does: str = "") -> Component:
    return Component(id, "select", label, does, options)


def Button(id: str | None, label: T | None = None, does: str = "", per_row: bool = False) -> Component:
    return Component(id, "button", label, does, per_row=per_row)


def Text(id: str | None, label: T | None = None, does: str = "", per_row: bool = False) -> Component:
    return Component(id, "text", label, does, per_row=per_row)


def Spinner(id: str | None, does: str = "", label: T | None = None) -> Component:
    return Component(id, "spinner", label, does)


def Banner(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "banner", label, does)


def Check(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "check", label, does)


def Heading(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "heading", label, does)


def MenuItem(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "menuitem", label, does)


def Link(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "link", label, does)


def Option(id: str | None, label: T, does: str = "") -> Component:
    return Component(id, "option", label, does)


@dataclass(frozen=True)
class Stored:
    """One value the screen keeps in memory (a useState, a field of a State
    object) with the type of value acceptable there."""

    name: str
    accepts: str
    initial: str


@dataclass(frozen=True)
class Phase:
    """A state of the screen: what is shown, what is disabled, and why."""

    name: str
    shows: tuple[Component, ...] = ()
    hides: tuple[Component, ...] = ()
    disabled: tuple[Component, ...] = ()
    because: str = ""


@dataclass(frozen=True)
class When:
    """The trigger of a transition: a component acted on, or an answer arriving."""

    what: str
    on: Component | None = None

    def __str__(self) -> str:
        return f"{self.what} {self.on.found_by()}" if self.on else self.what


@dataclass(frozen=True)
class Transition:
    start: Phase
    when: When
    end: Phase
    only_if: str = ""
    then: str = ""

    def __str__(self) -> str:
        guard = f" only if {self.only_if}" if self.only_if else ""
        effect = f"; {self.then}" if self.then else ""
        return f"{self.start.name} --[{self.when}{guard}]--> {self.end.name}{effect}"


class Screen:
    """Subclass per screen. Components, stored values, phases and transitions are
    class attributes so a reader and `describe()` see one declaration."""

    route: str = ""
    name: T = T("", "")
    root: Component | None = None
    first: bool = False
    reached_from: str = ""
    stored: tuple[Stored, ...] = ()
    phases: tuple[Phase, ...] = ()
    transitions: tuple[Transition, ...] = ()
    sends: tuple[Callable[[Any], bool], ...] = ()
    api: str = ""

    @classmethod
    def components(cls) -> list[Component]:
        return [v for v in vars(cls).values() if isinstance(v, Component) and v is not cls.root]

    @classmethod
    def describe(cls, lang: str = "en") -> str:
        lines = [f"# {cls.name[lang] or cls.__name__}" + (f"  ({cls.route})" if cls.route else "")]
        if cls.root is not None:
            lines.append(f"inside: {cls.root.found_by(lang)}")
        if cls.first:
            lines.append("first screen")
        if cls.reached_from:
            lines.append(f"reached from: {cls.reached_from}")
        lines.append("")
        lines.append("components:")
        for c in cls.components():
            label = f" {c.label[lang]!r}" if c.label else ""
            opts = "  options: " + ", ".join(o[lang] for o in c.options) if c.options else ""
            row = " (per row)" if c.per_row else ""
            lines.append(f"  {c.found_by(lang):18} {c.kind:9}{label}{row}  {c.does}{opts}".rstrip())
        if cls.sends:
            lines.append("")
            lines.append(f"sends (to {cls.api or 'the product API'}):")
            for sent in cls.sends:
                lines.append(f"  {getattr(sent, 'text', 'a request')}")
        if cls.stored:
            lines.append("")
            lines.append("stored:")
            for s in cls.stored:
                lines.append(f"  {s.name:12} {s.accepts}  (starts {s.initial})")
        if cls.phases:
            lines.append("")
            lines.append("phases:")
            for p in cls.phases:
                bits = []
                if p.shows:
                    bits.append("shows " + ", ".join(c.found_by(lang) for c in p.shows))
                if p.hides:
                    bits.append("hides " + ", ".join(c.found_by(lang) for c in p.hides))
                if p.disabled:
                    bits.append("disabled " + ", ".join(c.found_by(lang) for c in p.disabled))
                if p.because:
                    bits.append(f"because {p.because}")
                lines.append(f"  {p.name:10} " + "; ".join(bits))
            lines.append("")
            lines.append("transitions:")
            for t in cls.transitions:
                lines.append(f"  {t}")
        return "\n".join(lines)


F = TypeVar("F")


class Interaction(Generic[F]):
    """Subclass per thing a user does on a screen, or per change that reaches the
    app from outside its screens: the clock, the network, the store. The class
    body declares the screen, what the act does and the action it carries on the
    model; an instance is one act, aimed at the fixture the user fills in."""

    screen: ClassVar[type[Screen] | None] = None
    does: ClassVar[str] = ""
    carries: ClassVar[type[Action[Any, Any]] | None] = None

    def __init_subclass__(cls) -> None:
        if cls.carries is None and cls.screen is None:
            raise BookError(f"{cls.__name__}: carries no action")

    def __init__(self, of: object = None, *, by: Actor | None | object = KEEP):
        cls = type(self)
        self.by: Actor | None = SOLE if by is KEEP else cast("Actor | None", by)
        takes = cls.carries.accept if cls.carries is not None else None
        if takes is None and of is not None:
            raise BookError(f"{cls.__name__} takes nothing")
        if takes is not None and of is None:
            try:
                of = takes()
            except TypeError:
                raise BookError(f"{cls.__name__} needs a {takes.__name__}") from None
        if takes is not None and not isinstance(of, takes):
            raise BookError(f"{cls.__name__} takes a {takes.__name__}, not {type(of).__name__}")
        self.of: F = cast(F, of)

    def input(self) -> F:
        return self.of

    @classmethod
    def describe(cls) -> str:
        where = cls.screen.__name__ if cls.screen is not None else "outside the screens"
        accept = cls.carries.accept if cls.carries is not None else None
        takes = accept.__name__ if accept is not None else "nothing"
        return f"{cls.__name__:12} on {where:20} takes {takes:8} {cls.does}".rstrip()

    def __str__(self) -> str:
        text = type(self).__name__ + (f" {self.of}" if self.of is not None else "")
        if self.by is None:
            return text + " (by nobody)"
        return text if self.by is SOLE else f"{text} (by {self.by})"
