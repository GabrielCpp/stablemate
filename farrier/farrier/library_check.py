"""Front-matter validation for a library's skills and prompts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

from farrier.frontmatter import front_matter_end
from farrier.naming import compose_name, kebab, strip_known_suffix
from farrier.skill_hooks import findings as hook_findings

__all__ = ["Finding", "check_library", "check_text", "format_findings"]

_MD = MarkdownIt("commonmark").use(front_matter_plugin)

_LOAD_BEARING = frozenset({"name", "description", "applyTo", "tags"})


@dataclass(frozen=True)
class Finding:
    """One problem with one file."""

    path: Path
    level: str
    code: str
    message: str

    def render(self, root: Path | None = None) -> str:
        shown = self.path
        if root is not None:
            try:
                shown = self.path.relative_to(root)
            except ValueError:
                pass
        return f"{self.level}: {shown}: [{self.code}] {self.message}"


def _fence(text: str) -> str | None:
    """The raw front-matter block, or None when the file opens without one."""
    tokens = _MD.parse(text.replace("\r\n", "\n").replace("\r", "\n"))
    if not tokens or tokens[0].type != "front_matter":
        return None
    return tokens[0].content


def _top_level_scalars(fence: str) -> dict[str, yaml.ScalarEvent]:
    """Each load-bearing top-level key mapped to the parser's event for its value."""
    events: dict[str, yaml.ScalarEvent] = {}
    depth = 0
    key: str | None = None
    for event in yaml.parse(fence + "\n"):
        if isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent)):
            depth += 1
            key = None
            continue
        if isinstance(event, (yaml.MappingEndEvent, yaml.SequenceEndEvent)):
            depth -= 1
            continue
        if depth != 1 or not isinstance(event, yaml.ScalarEvent):
            continue
        if key is None:
            key = event.value
        else:
            if key in _LOAD_BEARING:
                events[key] = event
            key = None
    return events


def _retyped_tags(fence: str) -> list[tuple[str, str]]:
    """``(as written, as installed)`` for each tag YAML did not resolve as a string."""
    node = yaml.compose(fence + "\n")
    if not isinstance(node, yaml.MappingNode):
        return []
    retyped: list[tuple[str, str]] = []
    for key_node, value_node in node.value:
        if getattr(key_node, "value", None) != "tags":
            continue
        items = value_node.value if isinstance(value_node, yaml.SequenceNode) else []
        for item in items:
            if isinstance(item, yaml.ScalarNode) and item.tag != "tag:yaml.org,2002:str":
                installed = str(yaml.safe_load(f"[{item.value}]")[0]).strip().lower()
                retyped.append((item.value, installed))
    return retyped


def _trailing_text(fence: str, event: yaml.ScalarEvent) -> str:
    """Whatever sits between the end of *event*'s value and the end of its line."""
    if event.end_mark is None:
        return ""
    rest = fence[event.end_mark.index :]
    return rest.split("\n", 1)[0].strip()


NAME_LIMIT = 64
DESCRIPTION_LIMIT = 1024
BODY_LIMIT = 500


def _spec_findings(
    text: str, data: dict, path: Path, declared: str, description: str
) -> list[Finding]:
    """Where one SKILL.md breaks the Open Agent Skills spec — errors, all of them."""
    found: list[Finding] = []
    add = lambda code, msg: found.append(Finding(path, "error", code, msg))  # noqa: E731

    if not declared:
        add("missing-name",
            "no `name:` — required by the Open Agent Skills spec. Copilot rejects a "
            f"skill without one; it must be {path.parent.name!r}, the folder name.")
    elif declared != path.parent.name:
        add("name-mismatch",
            f"`name: {declared}` but the skill directory is {path.parent.name!r}. The "
            "spec requires the two to match — farrier installs under the directory "
            "name, so a harness validating the key sees a skill that is not there.")
    if len(declared) > NAME_LIMIT:
        add("name-too-long",
            f"`name:` is {len(declared)} characters; the spec allows {NAME_LIMIT}. The "
            "installed name is longer still — the library group prefixes it.")

    if not description:
        add("missing-description",
            "no `description:` — required by the spec, and it is the entire signal a "
            "harness ranks this skill by. farrier's fallback restates the title.")
    elif len(description) > DESCRIPTION_LIMIT:
        add("description-too-long",
            f"`description:` is {len(description)} characters; the spec allows "
            f"{DESCRIPTION_LIMIT}. Move the detail into the body — the description is "
            "read to *choose* the skill, not to follow it.")

    body = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")[front_matter_end(text):]
    if body and not body[0].strip():
        body = body[1:]
    if body and not body[-1].strip():
        body = body[:-1]
    lines = len(body)
    if lines > BODY_LIMIT:
        add("body-too-long",
            f"body is {lines} lines; the spec allows {BODY_LIMIT}. Split the overflow "
            "into `references/` beside the SKILL.md — bundled files ship with it and "
            "cost nothing until the agent opens one.")
    return found


def check_text(text: str, path: Path, *, require_tags: bool = True) -> list[Finding]:
    """Every finding for one library markdown source."""
    found: list[Finding] = []
    add = lambda level, code, msg: found.append(Finding(path, level, code, msg))  # noqa: E731

    fence = _fence(text)
    if fence is None:
        add("error", "no-frontmatter",
            "no front-matter block — the file must open with a `---` fence. "
            "Every key farrier reads (name, description, applyTo, tags) is lost without it.")
        return found

    try:
        data = yaml.safe_load(fence + "\n") or {}
    except yaml.YAMLError as exc:
        detail = str(exc).split("\n")[0].strip()
        add("error", "unparsable",
            f"front matter is not valid YAML ({detail}). farrier reads this as *no* front "
            "matter, so name, description, applyTo and tags are all silently dropped. "
            "Usually an unquoted value starting with `*`, `{` or `[`, or a double-quoted "
            "value containing an inner `\"` — wrap the value in single quotes.")
        return found

    if not isinstance(data, dict):
        add("error", "not-a-mapping",
            "front matter must be a YAML mapping of key: value pairs.")
        return found

    description = str(data.get("description") or "").strip()
    declared = str(data.get("name") or "").strip()

    if path.name == "SKILL.md":
        found.extend(_spec_findings(text, data, path, declared, description))
    elif not description:
        add("warning", "missing-description",
            "no `description:` — farrier substitutes the first heading, which restates "
            "the title. On Claude the description is the entire selection signal.")

    for key, event in _top_level_scalars(fence).items():
        if event.style is not None:
            continue
        trailing = _trailing_text(fence, event)
        if trailing.startswith("#"):
            add("error", "truncated-by-comment",
                f"`{key}:` is unquoted and contains ` #`, so YAML reads {trailing!r} as a "
                f"comment and the value silently becomes {event.value!r}. Quote the value.")
        elif event.anchor or event.tag:
            consumed = f"&{event.anchor}" if event.anchor else str(event.tag)
            add("warning", "fragile",
                f"`{key}:` opens with `{consumed}`, which YAML consumed as "
                f"{'an anchor' if event.anchor else 'a tag'} rather than text — the value "
                f"is {event.value!r}, not the whole line. Quote the value.")
        elif "{{" in event.value:
            add("warning", "fragile",
                f"`{key}:` is unquoted and contains a template expression; a later edit to "
                "it can turn the line into a mapping or a parse error. Quote the value.")

    for written, installed in _retyped_tags(fence):
        add("error", "tag-retyped",
            f"tag `{written}` is not a string to YAML, so it installs as `{installed}` — "
            f"a skill that answers find_by_tags({installed!r}) and never "
            f"find_by_tags({written!r}). Quote it.")

    if data.get("hooks") is not None and path.name != "SKILL.md":
        add("error", "hooks-not-a-skill",
            "only a SKILL.md may declare `hooks:` — a prompt bundles no scripts, so "
            "there is nothing for farrier to install and run.")
    else:
        for level, code, message in hook_findings(data, path.parent):
            add(level, code, message)

    if require_tags and path.name == "SKILL.md" and not data.get("tags"):
        add("warning", "untagged",
            "no `tags:` — the skill can never be the answer to a find_by_tags query, so "
            "any workflow that asks for this capability gets nothing and reports nothing.")

    return found


def _stutter_finding(root: Path, sub: str, path: Path) -> Finding | None:
    """A warning when a source's basename repeats its own parent folder."""
    rel = path.relative_to(root / sub)
    if path.name == "SKILL.md":
        parts = rel.parent.parts
    else:
        parts = rel.with_name(strip_known_suffix(rel)).parts
    if len(parts) < 2:
        return None
    group, base = kebab(parts[-2]), kebab(parts[-1])
    if base != group and not base.startswith(f"{group}-"):
        return None
    installed = compose_name(group, base)
    return Finding(
        path=path,
        level="warning",
        code="group-stutter",
        message=(
            f"basename repeats its folder {group!r}; installs as {installed!r} either "
            f"way, so dropping the repetition from the source renames nothing"
        ),
    )


def check_library(roots: list[Path], *, require_tags: bool = True) -> tuple[list[Finding], int]:
    """``(findings, files_checked)`` over every markdown source under *roots*."""
    findings: list[Finding] = []
    checked = 0
    seen: set[Path] = set()
    for root in roots:
        for sub in ("skills", "prompts"):
            directory = root / sub
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*.md")):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                text = path.read_text(encoding="utf-8")
                if sub == "prompts" and _fence(text) is None:
                    continue
                if path.name != "SKILL.md" and sub == "skills" and _fence(text) is None:
                    continue
                checked += 1
                findings.extend(check_text(text, path, require_tags=require_tags))
                stutter = _stutter_finding(root, sub, path)
                if stutter is not None:
                    findings.append(stutter)
    return findings, checked


def format_findings(findings: list[Finding], checked: int, root: Path | None = None) -> str:
    """The report, ordered errors-first so a truncated terminal still shows what fails."""
    errors = [f for f in findings if f.level == "error"]
    warnings = [f for f in findings if f.level == "warning"]
    lines = [f.render(root) for f in errors] + [f.render(root) for f in warnings]
    if not findings:
        lines.append(f"ok: {checked} library sources, all front matter parses")
    else:
        lines.append("")
        lines.append(
            f"{len(errors)} error(s), {len(warnings)} warning(s) across {checked} sources"
        )
    return "\n".join(lines)
