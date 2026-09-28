"""The health findings the QA context packet reports about the book: citations that resolve nowhere and relation subjects named too broadly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


RELATION_FANOUT = 6


@dataclass(frozen=True, slots=True)
class HealthRow:
    """One health finding about the book, as the packet's health lists it once serialized."""

    kind: str
    severity: str
    message: str
    node: str = ""
    ref: str = ""
    key: str = ""

    def row(self) -> dict[str, str]:
        """The finding as the packet lists it, leaving out the fields it does not name."""
        named = {"node": self.node, "ref": self.ref, "key": self.key}
        return {"kind": self.kind, "severity": self.severity, **{name: value for name, value in named.items() if value}, "message": self.message}


def resolve_groundings(
    code_refs_by_node: dict[str, tuple[str, ...]], resolves: Callable[[str], bool]
) -> tuple[set[str], list[HealthRow]]:
    """The nodes with a code citation that resolves, and a health row per citation that resolves nowhere. Each distinct citation is resolved once."""
    grounded: set[str] = set()
    dangling: list[HealthRow] = []
    ref_resolves: dict[str, bool] = {}
    for node_id, code_refs in code_refs_by_node.items():
        for normalized in code_refs:
            if normalized not in ref_resolves:
                ref_resolves[normalized] = resolves(normalized)
            if ref_resolves[normalized]:
                grounded.add(node_id)
            else:
                dangling.append(
                    HealthRow(
                        kind="dangling-grounding",
                        severity="error",
                        node=node_id,
                        ref=normalized,
                        message="code grounding resolves in neither base nor head",
                    )
                )
    return grounded, dangling


def relation_fanout_warnings(subjects_by_node: dict[str, set[str]], required_subjects: set[str]) -> list[HealthRow]:
    """A health row per required relation subject that more nodes name than a change can owe evidence for."""
    owners_by_subject: dict[str, list[str]] = {}
    for node_id, subjects in subjects_by_node.items():
        for subject in subjects & required_subjects:
            owners_by_subject.setdefault(subject, []).append(node_id)
    return [
        HealthRow(
            kind="relation-fanout",
            severity="warning",
            ref=subject,
            message=(
                f"relation subject `{subject}` binds {len(owners_by_subject[subject])} nodes; a change"
                " reaching any of them owes live evidence for all of them, which"
                " usually means the subject is named more broadly than the record"
            ),
        )
        for subject in sorted(required_subjects)
        if len(owners_by_subject.get(subject, [])) > RELATION_FANOUT
    ]
