"""From a state, every action the domain would turn away and the rule it breaks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book.model import Defect, Model, Rule


@dataclass(frozen=True)
class Denial:
    action: object
    rule: Rule[Any, Any] | Defect[Any, Any]

    def __str__(self) -> str:
        if isinstance(self.rule, Defect):
            return f"{self.action} meets a known defect: {self.rule.message} ({self.rule.name}, {self.rule.status})"
        return f"you cannot {self.action}: {self.rule.message} ({self.rule.name}, {self.rule.status})"


def denied(model: Model, candidates: Iterable[object]) -> list[Denial]:
    out = []
    for action in candidates:
        rule = model.explain(action)
        if rule is not None:
            out.append(Denial(action, rule))
    return out
