"""Harnesses that read one skill folder, grouped so the folder renders once."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from farrier._vendor.stablemate_core.harness import HARNESSES, spec
from farrier.renderer import user_harness_dir
from farrier.sources import Source

__all__ = ["RenderGroup", "render_groups", "skill_forms"]

Selection = tuple[list[Source], list[Source]]


@dataclass(frozen=True)
class RenderGroup:
    """The harnesses that share one skill folder, and what that folder renders."""

    folder: str
    harnesses: tuple[str, ...]
    skills: list[Source]
    prompts: list[Source]
    skill_ref: str


def _folder(scope: str, harness: str) -> str | None:
    if scope == "home":
        return f"{user_harness_dir(harness)}/skills"
    layout = spec(harness).repo
    return None if layout is None else layout.skills


def render_groups(scope: str, selections: Mapping[str, Selection]) -> list[RenderGroup]:
    """Each skill folder once, from the union of its members' selections.

    A group whose members share one reference syntax keeps it. A group
    with mixed syntax uses the path form every harness can follow.
    """
    members: dict[str, list[str]] = {}
    for harness in (h.name for h in HARNESSES if h.name in selections):
        folder = _folder(scope, harness)
        if folder is not None:
            members.setdefault(folder, []).append(harness)
    groups: list[RenderGroup] = []
    for folder, harnesses in members.items():
        refs = {spec(h).skill_ref for h in harnesses}
        groups.append(
            RenderGroup(
                folder=folder,
                harnesses=tuple(harnesses),
                skills=list(
                    dict.fromkeys(s for h in harnesses for s in selections[h][0])
                ),
                prompts=list(
                    dict.fromkeys(p for h in harnesses for p in selections[h][1])
                ),
                skill_ref=next(iter(refs)) if len(refs) == 1 else "path",
            )
        )
    return groups


def skill_forms(groups: list[RenderGroup]) -> dict[str, str]:
    """The reference form each harness renders its skill references with."""
    return {harness: group.skill_ref for group in groups for harness in group.harnesses}
