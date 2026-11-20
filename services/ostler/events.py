"""What a person does to the plan repository between commands, outside ostler."""

from __future__ import annotations

from ostler.book import Outside, Sandbox

from .model.actions import CopyOldEpic
from .model.files import LEGACY, LEGACY_STORY, OLD_EPIC, OLD_STORY

OLD_EPIC_PAGE = (f"---\ntype: epic\nid: {LEGACY}\ntitle: Legacy epic\nstatus: planned\n---\n# Epic: Legacy epic\n\n"
                 f"## Seeds\n\n## Stories\n\n### echo\n- title: Story echo\n- id: {LEGACY_STORY}\n- covers: (none)\n")
OLD_STORY_PAGE = (f"---\ntype: story\nid: {LEGACY_STORY}\nslug: echo\nstatus: Not started\n---\n# Story: Story echo\n\n"
                  "## Implementation Status\n\n- **Status**: Not started\n")


class CopyInAnOldEpic(Outside):
    does = ("A person copies in an epic from a shelf in the old layout: a folder named 0004-legacy whose epic.md records "
            "an id and no slug, and a story folder named by its slug.")
    carries = CopyOldEpic

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write(OLD_EPIC, OLD_EPIC_PAGE)
        sandbox.write(OLD_STORY, OLD_STORY_PAGE)
