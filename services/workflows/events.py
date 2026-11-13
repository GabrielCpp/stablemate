"""What a person does to the repository between commands, outside workflows."""

from __future__ import annotations

from ostler.book import Outside, Sandbox

from .model.actions import InstallSkillsByHand
from .model.files import SKILL_NAME, SKILLS


class InstallSkills(Outside):
    does = "A person installs the ostler-book skill into the repository, as `farrier install` would."
    carries = InstallSkillsByHand

    def happen(self, sandbox: Sandbox) -> None:
        for skill in SKILLS:
            sandbox.write(
                f".claude/skills/{skill}/SKILL.md",
                f'---\n{SKILL_NAME.format(skill)}\ndescription: "A skill."\n---\n\nUse it.\n',
            )
