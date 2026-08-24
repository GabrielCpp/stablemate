"""Front-matter validation for a library's skills and prompts.

The failure this module exists to catch is **silent**: ``_front_matter`` answers a
malformed YAML block with ``{}`` rather than an exception, because a generated file
legitimately has no front matter and a parse error there is not farrier's business to
raise. For a *library source* the same leniency is a trapdoor — a skill whose fence does
not parse loses its ``description``, its ``applyTo`` and its ``tags`` at once, and every
downstream symptom points somewhere else:

- the skill still installs, so nothing errors;
- its description falls back to "Use for <repo> work involving <first heading>", which
  reads like an authoring choice rather than a loss;
- its tags are gone, so ``find_by_tags`` quietly stops returning it — and a tag query
  that comes back short is indistinguishable from a repo that installs nothing matching.

Two YAML details cause nearly all of it, and neither looks like a mistake:

    applyTo: **/*.go                  # `*` opens an ALIAS -> parse error
    applyTo: {{ template.x }}/**      # `{` opens a FLOW MAPPING -> parse error
    description: "... default("app")" # the scalar ends at the inner quote

Quoting the value fixes all three, which is why ``fragile`` findings name the quote as
the remedy rather than describing the YAML rule.

The quieter half of the problem is a value YAML *accepts* and reads as something other
than the text written — ``description: Use for API work # and the CLI`` loses its second
half, ``description: &ref A thing`` loses the ``&ref`` to an anchor. Those cannot be seen
from the parsed mapping, where the loss has already happened. They are read here off
``yaml.parse``'s event stream instead, which reports each scalar's quoting style, anchor,
tag and source span — the parser's own account of how it read the line, rather than this
module guessing at the grammar with a regex.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

from farrier.naming import compose_name, kebab, strip_known_suffix
from farrier.skill_hooks import findings as hook_findings

__all__ = ["Finding", "check_library", "check_text", "format_findings"]

_MD = MarkdownIt("commonmark").use(front_matter_plugin)

# Keys farrier reads back off a library source. A value lost here is a value the
# renderer silently substitutes a default for.
_LOAD_BEARING = frozenset({"name", "description", "applyTo", "tags"})


@dataclass(frozen=True)
class Finding:
    """One problem with one file. *level* is ``"error"`` or ``"warning"``."""

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
    """Each load-bearing top-level key mapped to the parser's event for its value.

    The event is the useful object rather than the parsed value: it carries ``style``
    (``None`` for an unquoted scalar), any ``anchor`` or ``tag`` the parser consumed on
    the way, and the source span the value actually occupied — everything needed to ask
    whether YAML read the line as the text the author wrote.
    """
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
    """``(as written, as installed)`` for each tag YAML did not resolve as a string.

    A tag is a query key, so it only has to survive as *itself*. Most of the vocabulary
    is safe unquoted — `standards`, `planning`, `go` are plain scalars YAML resolves to
    the text written. But YAML 1.1 resolves ten-odd words to other types, and
    ``normalize_tags`` then ``str()``s whatever it is back into a tag: ``[on, docs]``
    installs ``true``. Nothing errors and no tag goes missing — one is simply spelled
    differently than the file says, so it answers a query nobody asks.
    """
    node = yaml.compose(fence + "\n")
    if not isinstance(node, yaml.MappingNode):
        return []
    retyped: list[tuple[str, str]] = []
    for key_node, value_node in node.value:
        if getattr(key_node, "value", None) != "tags":
            continue
        items = value_node.value if isinstance(value_node, yaml.SequenceNode) else []
        for item in items:
            # `item.tag` is the parser's own resolution, so this asks YAML what it
            # decided rather than re-deriving the 1.1 bool/null/int tables here.
            if isinstance(item, yaml.ScalarNode) and item.tag != "tag:yaml.org,2002:str":
                installed = str(yaml.safe_load(f"[{item.value}]")[0]).strip().lower()
                retyped.append((item.value, installed))
    return retyped


def _trailing_text(fence: str, event: yaml.ScalarEvent) -> str:
    """Whatever sits between the end of *event*'s value and the end of its line.

    Source marks are optional on an event in general (a re-emitted stream carries none),
    but always present on one the parser produced. Without a span there is no line to
    look past, so the honest answer is "nothing trailing" rather than a guess.
    """
    if event.end_mark is None:
        return ""
    rest = fence[event.end_mark.index :]
    return rest.split("\n", 1)[0].strip()


def check_text(text: str, path: Path, *, require_tags: bool = True) -> list[Finding]:
    """Every finding for one library markdown source.

    Scalar-level checks read the parser's *event stream* rather than the parsed mapping,
    because the shapes worth reporting are the ones YAML resolves without complaint: a
    value truncated at an unquoted ``#`` parses to a shorter string, not to an error, and
    by the time it is a Python object the loss is unrecoverable.
    """
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

    # `description` is a warning, not an error: farrier does render without one. But the
    # fallback is "Use for <repo> work involving <first heading>" — a restatement of the
    # title, and on a harness that selects skills by description alone that is the whole
    # ranking signal spent saying nothing.
    if not str(data.get("description") or "").strip():
        add("warning", "missing-description",
            "no `description:` — farrier substitutes the first heading, which restates "
            "the title. On Claude the description is the entire selection signal.")

    # Deliberately no `name:` requirement. farrier derives the installed name from the
    # source's path (public_name), never from this key, so a missing one costs nothing —
    # but one that *disagrees* with the directory misleads every human who reads it.
    declared = str(data.get("name") or "").strip()
    if declared and path.name == "SKILL.md" and declared != path.parent.name:
        add("warning", "name-mismatch",
            f"`name: {declared}` but the skill directory is {path.parent.name!r}; farrier "
            "installs it under the directory name and ignores this key.")

    # Only *unquoted* scalars are at risk, and only where a scalar is what was meant.
    # `tags: [go, backend]` opens with a YAML indicator because a flow sequence is the
    # documented spelling for it — the question is never "how does this line start" but
    # "did YAML read this value as the text the author meant, or as structure".
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

    # A `hooks:` block is a claim that farrier will run one of this skill's scripts at
    # every commit in every repo that selects it. It is checked here rather than at
    # install because the gate has to fail on the machine that *authors* the library —
    # by install time the malformed entry is already shipped, and the shape farrier
    # cannot read is the one it treats as no hooks at all.
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
    """A warning when a source's basename repeats its own parent folder.

    ``flutter/flutter-api`` installs as ``flutter-api``, exactly as ``flutter/api``
    does — the group join collapses an adjacent duplicate, so both spellings are
    correct and neither moves an installed name. The stutter is therefore never a
    build failure, and never worth a flag day across two libraries.

    It is still worth saying: the repetition is invisible in the installed name, so
    nothing else in the toolchain ever reports it, and a library drifts back into it
    one file at a time. A warning here is the only place the drift is visible.
    """
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
    """``(findings, files_checked)`` over every markdown source under *roots*.

    Prompts are checked with the same parser as skills — a prompt's front matter carries
    its ``description``, and it fails the same way — but only skills are asked for tags,
    since a prompt is addressed by name and answers no capability query.
    """
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
                # A bundled reference (references/api.md and friends) carries no front
                # matter by design; only files that open a fence are making claims.
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
