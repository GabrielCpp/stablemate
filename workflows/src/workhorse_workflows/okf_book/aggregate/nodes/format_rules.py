"""The book's page format, rendered from ostler's registry for a writer that runs no tool."""
from __future__ import annotations

from ostler.registry import UI_TYPES, BulletKey, UINodeType

UNWRITTEN_TYPES = frozenset({"entries", "untyped"})
CITATION_KEYS = frozenset({"tests"})
_FLAG_WORDS = (
    ("required", "required"),
    ("nested", "a nested list"),
    ("link", "a markdown link"),
    ("normative", "a claim"),
    ("refusal", "a refusal"),
    ("check", "a check call"),
    ("performs", "one literal call"),
    ("arrange", "a fixture"),
    ("alias", "an alias of the key above"),
)


def _bullet_line(bullet: BulletKey) -> str:
    cites = bullet.owns or bullet.key in CITATION_KEYS
    words = [word for flag, word in _FLAG_WORDS if getattr(bullet, flag) and not (cites and flag == "link")]
    if cites:
        words.append("a code citation `path::symbol`")
    if bullet.value_kind:
        words.append(f"a {bullet.value_kind}")
    return f"- `{bullet.key}:` {', '.join(words)}" if words else f"- `{bullet.key}:`"


def _place(node_type: UINodeType, folder: str) -> str:
    if node_type.kind == "file":
        context = f"{node_type.context}/" if node_type.context else ""
        return f"a file page `{folder}/{context}<slug>.md`, with frontmatter `type: {node_type.name}`, `slug` and `title`"
    named = ", the id spelled as the code spells it" if node_type.literal_id else ""
    return f"a `### <id>` section under `## {node_type.heading}`{named}"


def _binds_to_claim(bullet: BulletKey) -> bool:
    return bool(bullet.check or bullet.performs or bullet.arrange)


def _type_rules(node_type: UINodeType, folder: str) -> str:
    lines = [f"### {node_type.name}", "", f"Written as {_place(node_type, folder)}."]
    if node_type.required_sections:
        headings = ", ".join(f"`## {spec.heading}`" for spec in node_type.required_sections)
        lines.append(f"It must hold {headings}.")
    claims = any(bullet.normative or bullet.refusal for bullet in node_type.bullet_keys)
    bound = [bullet for bullet in node_type.bullet_keys if claims and _binds_to_claim(bullet)]
    if node_type.bullet_keys:
        lines.extend(("Its bullets, in this order:", ""))
        lines.extend(_bullet_line(bullet) for bullet in node_type.bullet_keys if bullet not in bound)
    if bound:
        lines.extend(("", "Each claim is followed by its own bullets, in this order:", ""))
        lines.extend(_bullet_line(bullet) for bullet in bound)
    return "\n".join(lines)


def format_rules(folder: str, types: tuple[UINodeType, ...] = UI_TYPES) -> str:
    """Each node type a writer may write under `folder`: where it lives, what it must hold, and its bullets in order."""
    return "\n\n".join(_type_rules(t, folder) for t in types if t.name not in UNWRITTEN_TYPES)
