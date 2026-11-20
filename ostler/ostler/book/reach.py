"""How a person gets from one screen to another, read from the book alone: the screens a person can open directly, the
interactions that lead from a screen to the next, and the screens that stand inside another."""

from __future__ import annotations

from collections import deque
from typing import Any

from ostler.book.screen import Interaction, Screen
from ostler.book.service import Service


def entries(service: Service[Any]) -> list[type[Screen]]:
    """The screens a person can open directly, then the screens an interaction outside the screens leads to."""
    found: dict[type[Screen], None] = {screen: None for screen in service.screens if screen.first}
    for interaction in service.interactions:
        if interaction.screen is None and interaction.leads_to is not None:
            found[interaction.leads_to] = None
    return list(found)


def edges(service: Service[Any]) -> list[tuple[type[Screen], type[Interaction[Any]], type[Screen]]]:
    """Each interaction that starts on a screen and leads to one, in the order the book declares them."""
    return [(i.screen, i, i.leads_to) for i in service.interactions if i.screen is not None and i.leads_to is not None]


def arrivals(service: Service[Any], screen: type[Screen]) -> list[type[Interaction[Any]]]:
    """The interactions that lead to the screen."""
    return [i for i in service.interactions if i.leads_to is screen]


def hosted(service: Service[Any], screen: type[Screen]) -> list[type[Screen]]:
    return [s for s in service.screens if s.inside is screen]


def walked(service: Service[Any]) -> dict[type[Screen], tuple[type[Interaction[Any]], ...]]:
    """Every screen a walk from an entry reaches, with the shortest chain of interactions it took. A screen another one
    hosts is reached with its host, by the host's chain, and ties go to the interaction declared first."""
    found: dict[type[Screen], tuple[type[Interaction[Any]], ...]] = {}
    queue: deque[type[Screen]] = deque()

    def reach(screen: type[Screen], chain: tuple[type[Interaction[Any]], ...]) -> None:
        if screen in found:
            return
        found[screen] = chain
        queue.append(screen)
        for inner in hosted(service, screen):
            reach(inner, chain)

    for screen in entries(service):
        reach(screen, ())
    leaving = edges(service)
    while queue:
        here = queue.popleft()
        for start, interaction, end in leaving:
            if start is here:
                reach(end, (*found[here], interaction))
    return found


def chain(service: Service[Any], screen: type[Screen]) -> list[type[Interaction[Any]]] | None:
    """The shortest interactions from an entry to the screen, or to its host for a hosted one, and None where no walk reaches it."""
    found = walked(service).get(screen)
    return None if found is None else list(found)


def unreached(service: Service[Any]) -> list[type[Screen]]:
    """The screens no walk from an entry reaches."""
    found = walked(service)
    return [s for s in service.screens if s not in found]


def step(interaction: type[Interaction[Any]]) -> str:
    return f"{interaction.__name__} on {interaction.screen.__name__}" if interaction.screen is not None else interaction.__name__


def route_text(service: Service[Any], screen: type[Screen]) -> str:
    """The chain to the screen in words: `A on X then B on Y`, `an entry` where none is needed, or that no walk reaches it."""
    found = chain(service, screen)
    if found is None:
        return "no walk reaches it"
    return " then ".join(step(i) for i in found) if found else "an entry"


def reach_line(service: Service[Any], screen: type[Screen]) -> str:
    """Where the screen is and how a person gets there, as `on X, reached by A then B`. A hosted screen names its host
    first: `on X, hosted by H, an entry` or `on X, hosted by H, reached by A then B`."""
    where = f"on {screen.__name__}" + (f", hosted by {screen.inside.__name__}" if screen.inside is not None else "")
    found = chain(service, screen)
    if found is None:
        return f"{where}, no walk from an entry reaches it"
    if screen.inside is not None and not found:
        return f"{where}, an entry"
    return f"{where}, reached by {route_text(service, screen)}"


def described(service: Service[Any], screen: type[Screen], lang: str) -> str:
    """The screen as `describe` prints it, with the interactions that lead to it."""
    return screen.describe(lang, arrivals(service, screen))
