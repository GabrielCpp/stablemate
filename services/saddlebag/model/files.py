"""The files of the sandbox the book watches, and what the model keeps for each: its path and which
of the declared strings it holds."""

from __future__ import annotations

from typing import ClassVar

from ostler.book import Mark, Watched

CONFIG = "config.toml"
DOTENV = "app.env"
VAULT_TOKEN = "home/.vault-token"
PROJECT_SETTINGS = ".claude/settings.json"
USER_SETTINGS = "home/.claude/settings.json"

BACKEND_KEYRING = 'backend = "keyring"'
BACKEND_DAEMON = 'backend = "daemon"'
DOTENV_LINES = (
    "# app settings",
    "PORT=8080",
    "PORT=9090",
    "LOG_LEVEL=info",
    "API_TOKEN=abc",
    "ACME_PW=hunter2hunter2",
    "STAGING_URL=https://ana:pw@example.com/db",
    "REGION=eu",
)
HOOK = "guard --hook"
EXISTING_SETTINGS = '"theme": "dark"'

INITIAL_DOTENV = tuple(line for line in DOTENV_LINES if line not in ("PORT=9090", "REGION=eu"))
EXPORT = "backup.saddlebag.json"
BROKEN = "broken.saddlebag.json"
FOREIGN = "foreign.json"
EXPORT_TEXT = ('{"format": "saddlebag-export", "version": 1, "secrets": [{"name": "imported", "var": "IMPORTED_PW", '
               '"tags": [["origin", "export"]], "values": {"password": "exported-secret"}}]}\n')
SEEDED = {
    DOTENV: "\n".join(INITIAL_DOTENV) + "\n",
    EXPORT: EXPORT_TEXT,
    BROKEN: "{\n",
    FOREIGN: '{"x": 1}\n',
}

MARKS = (
    Mark(CONFIG, BACKEND_KEYRING, BACKEND_DAEMON),
    Mark(DOTENV, *DOTENV_LINES),
    Mark(EXPORT, "saddlebag-export"),
    Mark(BROKEN, "{"),
    Mark(FOREIGN, '"x": 1'),
    Mark(VAULT_TOKEN, "vault-token"),
    Mark("*.claude/settings.json", EXISTING_SETTINGS, HOOK),
)


class FileRecord(Watched):
    """A watched file the sandbox holds."""

    marks = MARKS
    source: ClassVar[tuple[str, ...]] = ("saddlebag/saddlebag/preference.py", "saddlebag/saddlebag/dotenv.py",
                                         "saddlebag/saddlebag/guard.py::install")
