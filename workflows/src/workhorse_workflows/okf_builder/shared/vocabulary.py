"""The check vocabulary, rendered for a prompt."""

from __future__ import annotations

from ostler import acts, checks, registry


def check_vocabulary() -> str:
    """Every check, its signature, and the defect it exists to exclude — one per line."""
    return "\n".join(f"- `{spec.signature()}` — excludes: {spec.excludes}" for spec in checks.CHECKS)


_FLAG_WORDS: tuple[tuple[str, str], ...] = (
    ("required", "must be present — `none` is a verified claim, not a default"),
    ("nested", "value is a child-bullet list, one child per entry"),
    ("link", "value is a reference ostler resolves — a doc link or a code ref"),
    ("check", "value is a call from the check vocabulary above"),
    ("fixture", "value names a fixture this repo declares"),
    ("performs", "value is an act from the act vocabulary below, performed on this node's own surface"),
    ("normative", "each value mints ONE QA obligation a scenario must prove"),
    ("owns", "value names the file this node is documented against"),
    ("alias", "a second accepted spelling of the key above it"),
)


def _flags_of(b: registry.BulletKey) -> list[str]:
    on = {"required": b.required, "nested": b.nested, "link": b.link, "check": b.check,
          "fixture": b.arrange, "performs": b.performs, "normative": b.normative, "owns": b.owns, "alias": b.alias}
    return [word for word, _ in _FLAG_WORDS if on[word]]


def act_vocabulary() -> str:
    """Every act an `arrange:` bullet may perform, its signature, and what performing it leaves."""
    return "\n".join(
        f"- `{spec.signature()}` — establishes: {spec.establishes} "
        f"(drivers: {', '.join(spec.drivers)})" for spec in acts.ACTS)


def bullet_grammar() -> str:
    """Every UI node type and its ordered bullet keys, flagged — the whole grammar, inlined."""
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
