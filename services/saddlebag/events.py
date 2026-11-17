"""What a person does to the sandbox between commands, outside saddlebag."""

from __future__ import annotations

from ostler.book import Outside, Sandbox

from .model.actions import LeaveSettings as SettingsLeft
from .model.actions import PreferDaemon, PreferKeyring, PutVaultToken


class ChooseDaemon(Outside):
    does = "A person writes `backend = \"daemon\"` under [saddlebag] in the home config, though no daemon runs."
    carries = PreferDaemon

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("config.toml", 'config_version = 2\n\n[saddlebag]\nbackend = "daemon"\n')


class ChooseKeyring(Outside):
    does = "A person writes `backend = \"keyring\"` under [saddlebag] in the home config."
    carries = PreferKeyring

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("config.toml", 'config_version = 2\n\n[saddlebag]\nbackend = "keyring"\n')


class LeaveVaultToken(Outside):
    does = "A person leaves a Vault token in ~/.vault-token."
    carries = PutVaultToken

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("home/.vault-token", "vault-token\n")


class LeaveSettings(Outside):
    does = "A person has Claude Code settings of their own in the project, with a theme and nothing about hooks."
    carries = SettingsLeft

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write(".claude/settings.json", '{\n  "theme": "dark"\n}\n')
