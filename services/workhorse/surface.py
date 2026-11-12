"""workhorse's loop runner run in a sandbox: the seed it starts from and the environment it sees."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ostler.book import CommandSurface, Environment, Seed

SEED = Seed(
    {
        "config.toml": "config_version = 2\n",
        "home/.keep": "",
    },
    name="acme",
)

ENVIRONMENT = {
    "PATH": os.pathsep.join([str(Path(sys.executable).parent), os.environ.get("PATH", "")]),
    "HOME": "<sandbox>/home",
    "STABLEMATE_CONFIG": "<sandbox>/config.toml",
    "GROOM_URL": "http://127.0.0.1:9",
}


class WorkhorseCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, ENVIRONMENT)
