"""The subagents a turn may hand narrow work to, on the cheaper models the operator's profile names."""

from __future__ import annotations

from dataclasses import dataclass

from workhorse._vendor.stablemate_core.profiles import PowerMapping


@dataclass(frozen=True, slots=True)
class Delegate:
    """One named subagent, as a CLI defines it at launch."""

    name: str
    model: str
    effort: str | None
    description: str
    instructions: str
    read_only: bool


@dataclass(frozen=True, slots=True)
class _Role:
    description: str
    instructions: str
    read_only: bool


ROLES: dict[str, _Role] = {
    "lookup": _Role(
        description=(
            "Read-only lookup: find where something lives, list callers, summarise a file or a log, "
            "or answer one narrow factual question about the code."
        ),
        instructions=(
            "You answer one narrow question about the code or a log. Read, search and run read-only "
            "commands. Leave every file as you found it. Answer with the facts and the paths and lines "
            "they come from."
        ),
        read_only=True,
    ),
    "worker": _Role(
        description=(
            "Bounded task the caller specifies in full: one service, one layer, one layer's tests or "
            "one group of fixes. Reports what changed and the evidence."
        ),
        instructions=(
            "You do one bounded task the caller specifies in full. Touch only the files it assigns. "
            "Run the command it names to prove your part. Report the files you changed and that "
            "command's result."
        ),
        read_only=False,
    ),
}

_warned: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    print(f"[workhorse] WARNING: {message}", flush=True)


def delegates_for(mappings: dict[str, PowerMapping]) -> tuple[Delegate, ...]:
    """The catalog roles ``mappings`` assigns a model, in catalog order."""
    for name in mappings.keys() - ROLES.keys():
        _warn_once(
            f"role:{name}",
            f"delegates.{name} is not a subagent role (known: {', '.join(ROLES)}); ignoring it",
        )
    return tuple(
        Delegate(
            name=name,
            model=mapping.model,
            effort=mapping.effort,
            description=role.description,
            instructions=role.instructions,
            read_only=role.read_only,
        )
        for name, role in ROLES.items()
        if (mapping := mappings.get(name)) is not None and mapping.model
    )


def warn_unsupported(cli: str, delegates: tuple[Delegate, ...]) -> None:
    """Say once that ``cli`` takes no subagents at launch, so the profile's delegates go unused."""
    if delegates:
        _warn_once(
            f"cli:{cli}",
            f"{cli} defines no subagents at launch; the profile's delegates go unused",
        )
