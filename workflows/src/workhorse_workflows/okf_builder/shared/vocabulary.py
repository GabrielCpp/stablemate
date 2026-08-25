"""The check vocabulary, rendered for a prompt.

A repair turn writes `verify:` bullets, and doctor parses them against `ostler.checks` —
one closed vocabulary with fixed argument names. Telling the prompt where the list lives is
not enough: the first live backfill produced `count(subject=…, expected=1)` (the argument is
`equals`) and `visible(locator="PDFEngine output", …)` for a Go function returning bytes,
both of which re-entered the book as fresh `unparsed-check` findings. The vocabulary is
small enough to inline, so the prompt carries it and the turn has nothing to guess.

It is rendered from `checks.CHECKS` rather than transcribed, so a check added to ostler
reaches the prompt in the same commit — a transcription would drift silently, and the drift
would look exactly like the defect above.
"""

from __future__ import annotations

from ostler import checks, registry


def check_vocabulary() -> str:
    """Every check, its signature, and the defect it exists to exclude — one per line.

    `excludes` is included on purpose: it is the sentence that says *why* one check is not
    another, which is the judgment a repair turn is actually being asked to make.
    """
    return "\n".join(f"- `{spec.signature()}` — excludes: {spec.excludes}" for spec in checks.CHECKS)


#: The flag words a `BulletKey` can carry, in render order, each with the one-line meaning
#: the registry itself does not store (its flags are booleans; the prose is this module's).
_FLAG_WORDS: tuple[tuple[str, str], ...] = (
    ("required", "must be present — `none` is a verified claim, not a default"),
    ("nested", "value is a child-bullet list, one child per entry"),
    ("link", "value is a reference ostler resolves — a doc link or a code ref"),
    ("check", "value is a call from the check vocabulary above"),
    ("fixture", "value names a fixture this repo declares"),
    ("normative", "each value mints ONE QA obligation a scenario must prove"),
    ("owns", "value names the file this node is documented against"),
    ("alias", "a second accepted spelling of the key above it"),
)


def _flags_of(b: registry.BulletKey) -> list[str]:
    on = {"required": b.required, "nested": b.nested, "link": b.link, "check": b.check,
          "fixture": b.arrange, "normative": b.normative, "owns": b.owns, "alias": b.alias}
    return [word for word, _ in _FLAG_WORDS if on[word]]


def bullet_grammar() -> str:
    """Every UI node type and its ordered bullet keys, flagged — the whole grammar, inlined.

    The same argument as `check_vocabulary`, on the other half of the contract: the drift
    wave that stranded the existing books was mostly *bullet* drift — keys renamed, keys
    made required, keys reclassified as normative — and a prompt that names the registry
    instead of containing it repairs a node against the grammar it remembers. Rendered from
    `registry.UI_TYPES`, so a registry change reaches the prompt in the same commit.

    All types are rendered, not just the item's: a repair turn on one node routinely writes
    a sibling section (an interaction under a component, a step under a runbook), and the
    item's type is not derivable at flow time anyway — the finding names a node, not a type.
    """
    lines = [
        "Key flags: " + " · ".join(f"**{w}** — {m}" for w, m in _FLAG_WORDS) + ".",
        "Normative on every type: "
        + ", ".join(f"`{k}:`" for k in registry.SHARED_NORMATIVE_KEYS) + ".",
    ]
    for t in registry.UI_TYPES:
        where = (f"a file with frontmatter `type: {t.name}`" if t.kind == "file"
                 else f"`### <id>` under `## {t.heading}`")
        lines.append(f"\n**{t.name}** — {where}")
        lines.extend(
            f"- `{b.key}:`" + (f" — {', '.join(flags)}" if (flags := _flags_of(b)) else "")
            for b in t.bullet_keys
        )
    return "\n".join(lines)
