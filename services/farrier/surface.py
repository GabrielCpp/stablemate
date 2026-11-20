"""farrier run in a sandbox: the seed it starts from and the environment it sees."""

from __future__ import annotations

from ostler.book import CommandSurface, Environment, Seed

SEED = Seed(
    {
        "config.toml": "config_version = 2\n",
        "home/.keep": "",
        "base/library/.keep": "",
        "lib/library/skills/demo.md": '---\nname: demo\ndescription: "A skill."\n---\n\nUse it.\n',
        "lib/scaffolds/service-gitignore.yml": (
            "service-gitignore:\n  description: Ignore rules for a service\n  params:\n    dir: api\n  tree:\n"
            "    $dir/.gitignore: |\n      node_modules\n      # $dir\n"
        ),
    },
    name="acme",
)

ENVIRONMENT = {"HOME": "<sandbox>/home", "STABLEMATE_CONFIG": "<sandbox>/config.toml", "STABLEMATE_BASE_DIR": "<sandbox>/base"}


class FarrierCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, ENVIRONMENT)
