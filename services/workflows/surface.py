"""The workflows commands run in a sandbox: the seed it starts from and the environment it sees."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ostler.book import CommandSurface, Environment, Seed

SEED = Seed({"home/.keep": ""}, name="acme")

BIN = str(Path(sys.executable).parent)

ENVIRONMENT = {
    "HOME": "<sandbox>/home",
    "AGENT_REPO_DIR": "<sandbox>",
    "AGENT_CLI": "claude",
    "PATH": BIN + os.pathsep + os.environ.get("PATH", ""),
}


class WorkflowsCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, ENVIRONMENT)
