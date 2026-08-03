"""The starter ``agents.yml`` that ``farrier init`` writes.

The template is a module constant rather than a packaged data file. The wheel ships
only the ``farrier`` package (see the hatch wheel target in ``pyproject.toml``), so
``agents.example.yml`` — the full reference this is a pruned version of — is in the
sdist and the repo but is *not* on disk next to an installed farrier. A `pipx install
farrier` has to be able to produce this file with nothing else present.

Nothing here reads the library either, so `farrier init` works before
`farrier config set-library` and its output is the same on every machine.
"""

from __future__ import annotations

from string import Template

from farrier.naming import yaml_quote

# `$name` is substituted; every brace in here is literal, which is why this is a
# `string.Template` rather than `str.format` — the file it renders is full of the
# `{{ template.<key> }}` spelling a reader is meant to copy verbatim.
_TEMPLATE = Template("""\
# agents.yml — what farrier renders into this repository.
#
#   farrier install          render the selection below into the adapter directories
#   farrier install --check  verify those generated files are current (writes nothing)
#
# Only `agents` is required. Every key, with its accepted spellings and defaults, is
# documented inline in farrier's agents.example.yml.

# Repository identity. `name` is prepended to every installed skill and prompt
# (library skill `db.md` -> `<name>-db`), and defaults to this directory's name.
repo:
  name: $name

# Which assistant adapters to generate. At least one must be truthy.
#   claude  -> .claude/skills/<name>/SKILL.md, .claude/commands/<name>.md
#   codex   -> .agents/skills/<name>/SKILL.md, .agents/prompts/<name>.prompt.md
#   copilot -> .github/instructions/, .github/skills/, .github/prompts/
agents:
  claude: true
  # codex: true
  # copilot: true

# Named bundles from the library's packs/ directory, without the .yml suffix. A pack
# selects skills, prompts, roots and scaffold ids, and may include other packs; all
# the packs listed here are merged. An empty list renders nothing — fill it in.
packs: []

# Individual selections ADDED on top of what the packs pull in (globs allowed).
# skills:
#   - planning/*
# prompts:
#   - review/*

# Scaffold ids this repo may apply on demand with `farrier scaffold <id>`; run
# `farrier scaffold --list` to see the ones the selection above makes available.
# scaffolds:
#   - shared-docs

# Suppress items a pack pulls in but this repo does not want (globs, matched
# against library paths).
# exclude:
#   skills:
#     - go/experimental-*

# Jinja2 values injected into every rendered skill and prompt, referenced in the
# library source as `{{ template.<key> }}`.
# template:
#   app_path: app

# An opaque block farrier passes through untouched — the workflow distributions you
# install read their own keys out of it.
# workflow:
#   githubTokenEnv: GH_TOKEN
""")


def default_config(repo_name: str) -> str:
    """Render the starter ``agents.yml`` for a repository directory named *repo_name*.

    The name is quoted through the same helper the renderer uses, so a directory whose
    name YAML would otherwise read as something else — ``no``, ``2024``, one with a
    colon in it — still round-trips as the string it is.
    """
    return _TEMPLATE.substitute(name=yaml_quote(repo_name))
