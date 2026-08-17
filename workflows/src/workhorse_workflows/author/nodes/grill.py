"""Find the slash command that opens the operator's grilling session.

The grill node writes a brief to the outbox and needs to tell the operator which
command starts the conversation. That command is whatever this repo's farrier install
rendered from `base-library/library/prompts/stablemate/grill.md` — its own repo-root
relative filename, under whatever prefix this install chose — so it is found by
scanning the rendered Claude commands for the `tags: [grill]` farrier stamps onto it
(`farrier/renderer.py`'s `generated_command`), not guessed at.
"""
from __future__ import annotations

import logging

import yaml

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.author.nodes._blueprint import blueprint
from workhorse_workflows.author.shared.paths import survey_repo_root

#: `farrier/farrier/outputs.py` — where a Claude command adapter lands, repo-root
#: relative, one flat `.md` file per command.
COMMAND_DIR = ".claude/commands"


def _front_matter(text: str) -> dict:
    """The YAML front matter of a rendered adapter, or `{}` when it has none."""
    if not text.startswith("---\n"):
        return {}
    _, _, rest = text.partition("---\n")
    block, sep, _ = rest.partition("\n---")
    if not sep:
        return {}
    parsed = yaml.safe_load(block)
    return parsed if isinstance(parsed, dict) else {}


@blueprint.node
def resolve_grill_trigger(logger: logging.Logger, repo_dir: str = "") -> str:
    """The `/…` command that opens a grilling session, found by its rendered tag.

    Fails loudly rather than guessing a command name: a wrong trigger sends the
    operator to a command that does not exist, or worse, one that does something else.
    """
    root = survey_repo_root(repo_dir)
    command_dir = root / COMMAND_DIR
    for candidate in sorted(command_dir.glob("*.md")) if command_dir.is_dir() else []:
        tags = _front_matter(candidate.read_text(encoding="utf-8")).get("metadata", {})
        tags = tags.get("tags", []) if isinstance(tags, dict) else []
        if isinstance(tags, list) and "grill" in tags:
            logger.info("grill trigger resolved to /%s", candidate.stem)
            return f"/{candidate.stem}"
    raise WorkflowFailed(
        f"no command under {command_dir} carries `tags: [grill]` — this repo's "
        "farrier install is missing the grill prompt, or needs `make agent-install` "
        "re-run after it was added"
    )


__all__ = ["resolve_grill_trigger"]
