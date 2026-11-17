"""What a person does to the repository between commands, outside farrier."""

from __future__ import annotations

from ostler.book import Outside, Sandbox

from .model.actions import AddUserLibrary, SelectByHand, WriteByHand


class HandWriteConfig(Outside):
    does = "A person writes agents.yml by hand: a Claude-only config with no packs line."
    carries = WriteByHand

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("agents.yml", "agents:\n  claude: true\n# hand-written\n")


class ListWhatIsWanted(Outside):
    does = "A person lists the demo skill under skills: and the scaffold under scaffolds: in agents.yml, as init's next step asks."
    carries = SelectByHand

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.append("agents.yml", "skills:\n  - demo\nscaffolds:\n  - service-gitignore\n")


class ListUserLibrary(Outside):
    does = "A person adds a [user_library.claude] table naming the demo skill to the home config."
    carries = AddUserLibrary

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.append("config.toml", '\n[user_library.claude]\nskills = ["demo"]\n')
