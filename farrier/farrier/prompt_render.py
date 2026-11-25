"""A library prompt rendered as a harness command, or as a skill the user runs by name."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from farrier.banners import skill_metadata_block
from farrier.frontmatter import first_heading, frontmatter_mapping
from farrier.naming import yaml_quote
from farrier.sources import Source, public_name

if TYPE_CHECKING:
    from farrier.renderer import Renderer

ARGUMENTS = "$ARGUMENTS"
ARGUMENTS_CALL = "{{ arguments }}"
COMMAND_ARGUMENTS = {"copilot": "${input:arguments}"}
SKILL_ARGUMENTS = "<arguments>"
CODEX_NAME_ONLY = "policy:\n  allow_implicit_invocation: false\n"


def strip_arguments_placeholder(body: str) -> str:
    """Drop a command's ``$ARGUMENTS`` line when its body is aggregated instead."""
    lines = [line for line in body.splitlines() if line.strip() != ARGUMENTS]
    return "\n".join(lines)


def command_description(
    prefix: str, source: Source, header: dict[str, str], body: str
) -> str:
    """The `description` for a generated command's or prompt skill's front matter."""
    if header.get("description"):
        return header["description"]
    return first_heading(body, public_name(prefix, source))


def command_text(
    renderer: Renderer, source: Source, target: str, output_path: Path
) -> str:
    """Render a library prompt with target-specific fields and shared provenance."""
    header, body = renderer.rendered_source(source, target, output_path)
    description = command_description(renderer.prefix, source, header, body)
    if target == "copilot":
        rendered = renderer.render_templates(
            source.path.read_text(encoding="utf-8"), target, output_path
        )
        native_header = frontmatter_mapping(rendered)
        native_header.pop("metadata", None)
        native_header["description"] = description
        lines = [
            "---",
            yaml.safe_dump(native_header, sort_keys=False, allow_unicode=True).rstrip(
                "\n"
            ),
        ]
    else:
        lines = ["---", f"description: {yaml_quote(description)}"]
        for key, aliases in (
            ("argument-hint", ("argument-hint", "argumentHint")),
            ("model", ("model",)),
            ("allowed-tools", ("allowed-tools", "allowedTools")),
        ):
            value = next((header[a] for a in aliases if header.get(a)), None)
            if value:
                lines.append(f"{key}: {yaml_quote(value)}")
    lines.append(_metadata(renderer, source, output_path).rstrip("\n"))
    lines.append("---")
    return "\n".join(lines) + "\n\n" + f"{body}\n"


def prompt_skill_text(
    renderer: Renderer, source: Source, target: str, output_path: Path
) -> str:
    """A library prompt as a skill the user runs by name, for a harness with no prompt folder."""
    header, body = renderer.rendered_source(source, target, output_path)
    description = command_description(renderer.prefix, source, header, body)
    hint = header.get("argument-hint") or header.get("argumentHint")
    if hint or SKILL_ARGUMENTS in body:
        usage = f"`{SKILL_ARGUMENTS}` stands for the text after this skill's name when the user runs it"
        usage += f": `{hint}`." if hint else "."
        head, _, rest = body.partition("\n")
        body = (
            f"{head}\n\n{usage}\n{rest}"
            if head.startswith("# ")
            else f"{usage}\n\n{body}"
        )
    return (
        "---\n"
        f"name: {public_name(renderer.prefix, source)}\n"
        f"description: {yaml_quote(description)}\n"
        "disable-model-invocation: true\n"
        f"{_metadata(renderer, source, output_path)}"
        "---\n"
        "\n"
        f"{body}\n"
    )


def _metadata(renderer: Renderer, source: Source, output_path: Path) -> str:
    return skill_metadata_block(
        source,
        renderer.dest_rel(output_path),
        renderer.skill_tags(source),
        renderer.regenerate,
    )
