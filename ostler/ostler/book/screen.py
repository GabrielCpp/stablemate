"""Screens as a reader and a driver both see them: components with their
accessibility id and labels, what the screen stores, the phases it moves
through and the transitions between them."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, ClassVar, Generic, Sequence, TypeVar, cast

from ostler.book.asked import Asked
from ostler.book.cast import KEEP, SOLE, Actor
from ostler.book.domain import Action, Fixture
from ostler.book.errors import BookError
from ostler.book.http import Field as Wire
from ostler.book.pagedata import Handed


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


ROLES = {
    "field": "textbox",
    "textarea": "textbox",
    "date": "textbox",
    "button": "button",
    "select": "combobox",
    "form": "form",
    "check": "checkbox",
    "heading": "heading",
    "menuitem": "menuitem",
    "link": "link",
    "option": "option",
    "banner": "alert",
    "spinner": "progressbar",
    "tab": "tab",
    "image": "img",
    "group": "group",
    "radios": "radiogroup",
}


@dataclass(frozen=True)
class Lists:
    """What a list filled from data holds: `given` matches the request whose answer fills it, or names the page whose
    data the app's server hands it with `handed(route)`, or names a backend's call, asked as the person looking, with
    `asked(Endpoint)`, `derived` turns the decoded body of that answer, or that data,
    into the texts the list shows, in order, and `head` are the labels shown before them.
    `derived` may take the URL of the request that was answered as a second argument, which is '' for a list
    given by `asked`.
    `always` and `never` read the model, for the person looking, and return the texts the list must show and the
    texts it must not; entries neither names are ignored.
    `entries` are rules every entry shown must hold, such as `in_order()`, and `picked` is the label the list has
    selected before a person picks, or a function of the model and the person looking that returns it.
    The entries of a generated form are its fields, each a pair of the field's accessible name and its ARIA role:
    `derived` returns those pairs, and the rules judge the names."""

    head: tuple[T | str, ...] = ()
    given: Callable[[Any], bool] | Handed | Asked | None = None
    derived: Callable[..., list[Any]] | None = None
    always: Callable[[Any, Any], list[str]] | None = None
    never: Callable[[Any, Any], list[str]] | None = None
    entries: tuple[Callable[[list[Any]], list[str]], ...] = ()
    picked: T | str | Callable[[Any, Any], str] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.head, (str, T)):
            raise BookError("head takes a tuple of labels, not one label")
        if callable(self.entries):
            raise BookError("entries takes a tuple of rules, not one rule: write entries=(in_order(),)")
        object.__setattr__(self, "head", tuple(T(h) if isinstance(h, str) else h for h in self.head))
        if (self.given is None) != (self.derived is None):
            missing, present = ("derived", "given") if self.derived is None else ("given", "derived")
            raise BookError(f"a list states what it holds with both given and derived; it has {present} and no {missing}")
        if self.derived is None and self.always is None and self.never is None and not self.entries and self.picked is None:
            raise BookError("a list states nothing: give it given and derived, always, never, entries or picked")
        for rule in self.entries:
            if not (rule.__doc__ or "").strip():
                raise BookError(f"the entries rule {getattr(rule, '__name__', 'rule')} has no docstring: "
                                "its first line says what the entries hold, and search and explain show it")
        if self.derived is not None and not 1 <= self.arity() <= 2:
            raise BookError(f"the derived function {getattr(self.derived, '__name__', 'derived')} takes the body of the answer "
                            "and, if it wants it, the URL of the request: one or two arguments")
        picked = self.picked if callable(self.picked) else None
        for claim, function in (("derived", self.derived), ("always", self.always), ("never", self.never), ("picked", picked)):
            if function is not None and not (function.__doc__ or "").strip():
                raise BookError(f"the {claim} function {getattr(function, '__name__', claim)} has no docstring: "
                                "its first line says what the list holds, and search and explain show it")

    def arity(self) -> int:
        assert self.derived is not None
        taken = inspect.signature(self.derived).parameters.values()
        if any(p.kind is p.VAR_POSITIONAL for p in taken):
            return 2
        return sum(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in taken)

    def derive(self, body: Any, url: str) -> list[Any]:
        assert self.derived is not None
        return self.derived(body, url) if self.arity() == 2 else self.derived(body)

    def labels(self, lang: str) -> list[str]:
        return [(T(h) if isinstance(h, str) else h)[lang] for h in self.head]

    def label_picked(self, lang: str) -> str | None:
        """The label the list has selected first when the book states it fixed, else None."""
        if self.picked is None or callable(self.picked):
            return None
        return self.picked[lang] if isinstance(self.picked, T) else self.picked

    def says(self, lang: str) -> str:
        said = (self.derived.__doc__ or "").strip().splitlines()[0] if self.derived is not None else ""
        if said and isinstance(self.given, Handed):
            said = f"{said}, from the {self.given.text}"
        if said and isinstance(self.given, Asked):
            said = f"{said}, asked of {self.given.text}"
        shown = ", ".join([repr(label) for label in self.labels(lang)] + ([said] if said else []))
        claims = [f"{claim} {function.__doc__.strip().splitlines()[0]}"
                  for claim, function in (("always", self.always), ("never", self.never)) if function is not None and function.__doc__]
        if self.entries:
            claims.append("entries " + ", ".join(rule.__doc__.strip().splitlines()[0] for rule in self.entries if rule.__doc__))
        if self.picked is not None:
            fixed = self.label_picked(lang)
            said_picked = (getattr(self.picked, "__doc__", "") or "").strip().splitlines()[0] if fixed is None else repr(fixed)
            claims.append(f"picked {said_picked}")
        return "; ".join(([shown] if shown else []) + claims)


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
    takes: str = ""
    holds: Wire | None = None
    lists: Lists | None = None
    unlisted: str = ""

    def __post_init__(self) -> None:
        if self.id is None and self.label is None:
            raise BookError(f"a {self.kind} component has neither an id nor a label")
        if (self.holds is None) != (not self.takes):
            raise BookError(f"a {self.kind} component holds a shape only with the fixture field it takes, and the reverse")

    def describe(self, lang: str) -> str:
        """The component as a line of its screen's description: how it is found, its kind, its label and what it does."""
        label = f" {self.label[lang]!r}" if self.label else ""
        opts = "  options: " + ", ".join(o[lang] for o in self.options) if self.options else ""
        opts = f"  lists: {self.lists.says(lang)}" if self.lists is not None else opts
        opts = f"  choices unlisted: {self.unlisted}" if self.unlisted else opts
        row = " (per row)" if self.per_row else ""
        holds = f"  holds {self.holds.describe()} as {self.takes}" if self.holds is not None else ""
        return f"{self.found_by(lang):18} {self.kind:9}{label}{row}  {self.does}{opts}{holds}".rstrip()

    def found_by(self, lang: str) -> str:
        """How a driver finds this component: its id, or its role and name."""
        if self.id is not None:
            return self.id
        assert self.label is not None
        role = ROLES.get(self.kind)
        name = self.label[lang]
        return f"text {name!r}" if role is None else f"{role} {name!r}"


def Field(id: str | None, label: T | str, does: str = "", takes: str = "", holds: Wire | None = None) -> Component:
    return Component(id, "field", as_label(label), does, takes=takes, holds=holds)


def TextArea(id: str | None, label: T | str, does: str = "", takes: str = "", holds: Wire | None = None) -> Component:
    return Component(id, "textarea", as_label(label), does, takes=takes, holds=holds)


def DateField(id: str | None, label: T | str, does: str = "", takes: str = "", holds: Wire | None = None) -> Component:
    return Component(id, "date", as_label(label), does, takes=takes, holds=holds)


def Select(id: str | None, label: T | str, does: str = "", takes: str = "", holds: Wire | None = None, *,
           options: tuple[T | str, ...] = (), lists: Lists | None = None, unlisted: str = "") -> Component:
    """A picker. `options` are its fixed choices, `lists` says what data fills it, and `unlisted="<why>"` says why
    the book states neither, such as choices that come from records of the signed-in account."""
    if not isinstance(does, str):
        raise TypeError("options are given by name: Select(id, label, does, options=(...))")
    if isinstance(options, (str, T)):
        raise TypeError("options takes a list of texts, not one text")
    if options and lists is not None:
        raise BookError(f"a select with fixed options cannot also derive its list: write options=(...) for a fixed list "
                        f"or lists=Lists(...) for one filled from data, not both ({id or label})")
    if unlisted and (options or lists is not None or holds is not None):
        raise BookError(f"a select whose choices are unlisted states no options, list or shape ({id or label})")
    return Component(id, "select", as_label(label), does, tuple(T(o) if isinstance(o, str) else o for o in options),
                     takes=takes, holds=holds, lists=lists, unlisted=unlisted)


def Form(id: str | None, label: T | str, does: str = "", *, lists: Lists | None = None) -> Component:
    return Component(id, "form", as_label(label), does, lists=lists)


def Button(id: str | None, label: T | str | None = None, does: str = "", per_row: bool = False) -> Component:
    return Component(id, "button", as_label(label), does, per_row=per_row)


def Text(id: str | None, label: T | str | None = None, does: str = "", per_row: bool = False) -> Component:
    return Component(id, "text", as_label(label), does, per_row=per_row)


def Spinner(id: str | None, does: str = "", label: T | str | None = None) -> Component:
    return Component(id, "spinner", as_label(label), does)


def Banner(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "banner", as_label(label), does)


def Check(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "check", as_label(label), does)


def Heading(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "heading", as_label(label), does)


def MenuItem(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "menuitem", as_label(label), does)


def Link(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "link", as_label(label), does)


def Option(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "option", as_label(label), does)


def Tab(id: str | None, label: T | str, does: str = "") -> Component:
    return Component(id, "tab", as_label(label), does)


def Image(id: str | None, label: T | str, does: str = "") -> Component:
    """An image found by its alternative text."""
    return Component(id, "image", as_label(label), does)


def Group(id: str | None, label: T | str, does: str = "") -> Component:
    """A region that gathers related content under one name, such as a tile or a card."""
    return Component(id, "group", as_label(label), does)


def Radios(id: str | None, label: T | str, does: str = "", *, options: tuple[T | str, ...] = ()) -> Component:
    """A set of radio buttons under one name; `options` are the names of its radios."""
    if isinstance(options, (str, T)):
        raise TypeError("options takes a list of texts, not one text")
    return Component(id, "radios", as_label(label), does, tuple(T(o) if isinstance(o, str) else o for o in options))


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


class Screen:
    """Subclass per screen. Components, stored values, phases and transitions are
    class attributes so a reader and `describe()` see one declaration."""

    route: str = ""
    name: T | str = ""
    root: Component | None = None
    first: bool = False
    inside: ClassVar[type[Screen] | None] = None
    shown_in: ClassVar[Phase | None] = None
    stored: tuple[Stored, ...] = ()
    phases: tuple[Phase, ...] = ()
    transitions: tuple[Transition, ...] = ()
    sends: tuple[Callable[[Any], bool], ...] = ()
    api: str = ""
    source: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def components(cls) -> list[Component]:
        return [v for v in vars(cls).values() if isinstance(v, Component) and v is not cls.root]

    @classmethod
    def attributes(cls) -> list[tuple[str, Component]]:
        """Each component with the attribute it sits on."""
        return [(name, v) for name, v in vars(cls).items() if isinstance(v, Component) and v is not cls.root]

    @classmethod
    def describe(cls, lang: str, arrived: Sequence[type[Interaction[Any]]] = ()) -> str:
        title = as_label(cls.name)
        lines = [f"# {(title[lang] if title else '') or cls.__name__}" + (f"  ({cls.route})" if cls.route else "")]
        if cls.root is not None:
            lines.append(f"inside: {cls.root.found_by(lang)}")
        if cls.first:
            lines.append("first screen")
        for interaction in arrived:
            on = f" on {interaction.screen.__name__}" if interaction.screen is not None else ""
            lines.append(f"reached by: {interaction.__name__}{on}")
        if cls.inside is not None:
            lines.append(f"hosted by: {cls.inside.__name__}")
        if cls.shown_in is not None:
            lines.append(f"shown in: {cls.shown_in.name}")
        lines.append("")
        lines.append("components:")
        for c in cls.components():
            lines.append("  " + c.describe(lang))
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
                if p.states:
                    bits.append("; ".join(s.text(lang) for s in p.states))
                if p.when is not None:
                    bits.append(f"when {p.when.says}" + (f" at {p.when.viewport.name}" if p.when.viewport else ""))
                if p.because:
                    bits.append(f"because {p.because}")
                lines.append(f"  {p.name:10} " + "; ".join(bits))
            lines.append("")
            lines.append("transitions:")
            for t in cls.transitions:
                lines.append(f"  {t.text(lang)}")
        return "\n".join(lines)


F = TypeVar("F")


class Interaction(Generic[F]):
    """Subclass per thing a user does on a screen, or per change that reaches the
    app from outside its screens: the clock, the network, the store. The class
    body declares the screen, what the act does and the action it carries on the
    model; an instance is one act, aimed at the fixture the user fills in."""

    screen: ClassVar[type[Screen] | None] = None
    leads_to: ClassVar[type[Screen] | None] = None
    does: ClassVar[str] = ""
    carries: ClassVar[type[Action[Any, Any]] | None] = None
    source: ClassVar[tuple[str, ...]] = ()
    viewport: ClassVar[Viewport | None] = None

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
    def typed(cls) -> list[Component]:
        """The components of its screen that declare the shape of a field of the fixture this interaction takes."""
        accept = cls.carries.accept if cls.carries is not None else None
        if cls.screen is None or not (isinstance(accept, type) and issubclass(accept, Fixture)):
            return []
        held = accept.field_names()
        return [c for c in cls.screen.components() if c.holds is not None and c.takes in held]

    @classmethod
    def describe(cls) -> str:
        where = cls.screen.__name__ if cls.screen is not None else "outside the screens"
        accept = cls.carries.accept if cls.carries is not None else None
        takes = accept.__name__ if accept is not None else "nothing"
        at = f" at {cls.viewport.name}" if cls.viewport is not None else ""
        return f"{cls.__name__:12} on {where:20} takes {takes:8} {cls.does}{at}".rstrip()

    def __str__(self) -> str:
        text = type(self).__name__ + (f" {self.of}" if self.of is not None else "")
        if self.by is None:
            return text + " (by nobody)"
        return text if self.by is SOLE else f"{text} (by {self.by})"
