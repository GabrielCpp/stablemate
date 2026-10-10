"""`ostler doctor`'s check that one observation is not pinned under several claims of a node.

A check written once under a list of claims observes that list. The same check written again
under another claim that sends the same request observes nothing new: the second claim reads as
proven while no assertion looks at what it says. Under a claim that arranges a different request,
the same check observes a different response, and proves that claim on its own. A node that
repeats a check for one request has usually padded every claim with whichever check was at hand,
so the claims that have no observation of their own stop showing as debt.
"""

from __future__ import annotations

from ostler import checks, refs as refs_mod, registry
from ostler.finding import Finding
from ostler.model import Graph, UINode


def _spelled(value: str) -> str:
    """The check's canonical spelling, so two bullets that differ only in argument order match."""
    parsed = checks.parse_check(value)
    return parsed.text() if isinstance(parsed, checks.CheckCall) else " ".join(value.split())


def _repeated(node: UINode) -> list[tuple[str, list[int], set[tuple[str, int]]]]:
    """Each check this node writes at two or more `verify:` bullets of claims arranging the same acts: the check, those indexes, and the claims they bind to."""
    _, bound = registry.attributed_check_bullets(node.type, node.bullet_order, node.combiners)
    _, acts = registry.attributed_acts(node.type, node.bullet_order, node.combiners)
    seen: dict[tuple[str, frozenset[str]], tuple[set[int], set[tuple[str, int]]]] = {}
    for claim, values in bound.items():
        arranged = frozenset(" ".join(act.split()) for act in acts.get(claim, []))
        for verify_index, value in values:
            indexes, claims = seen.setdefault((_spelled(value), arranged), (set(), set()))
            indexes.add(verify_index)
            claims.add(claim)
    repeated = [(text, sorted(indexes), claims) for (text, _), (indexes, claims) in seen.items() if len(indexes) >= 2]
    return sorted(repeated, key=lambda found: (found[0], found[1]))


def check_shared_checks(graph: Graph, f: list[Finding]) -> None:
    """Each check a node writes observes the one claim, or the one list of claims, it sits under."""
    for node in graph.ui_nodes:
        keys = registry.check_keys(node.type)
        if not keys:
            continue
        verify_key = keys[0]
        rel = node.path.resolve().relative_to(graph.root.resolve()).as_posix()
        for text, indexes, claims in _repeated(node):
            named = ", ".join(f"`{key}:{index}`" for key, index in sorted(claims))
            f.append(Finding(
                "error", "shared-check",
                f"{node.id}: `{verify_key}: {text}` is written {len(indexes)} times, under {named}. "
                f"One observation proves the claim it was written for, and the copies prove "
                f"nothing about the others. Give each claim the check that would fail if that "
                f"claim were false. When no such check exists yet, delete the copy, and the claim "
                f"shows as `undeclared-obligation` debt instead of passing unobserved",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, verify_key, indexes[1])))


__all__ = ["check_shared_checks"]
