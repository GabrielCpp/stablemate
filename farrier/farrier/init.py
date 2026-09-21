"""The starter ``agents.yml`` that ``farrier init`` writes."""

from __future__ import annotations

from pathlib import Path
from string import Template

from farrier.naming import repo_prefix

_TEMPLATE = Template("""\
# agents.yml — what farrier renders into this repository.
#
#   farrier install          render the selection below into the adapter directories
#   farrier install --check  verify those generated files are current (writes nothing)
#
# Only `agents` is required. Every key, with its accepted spellings and defaults, is
# documented inline in farrier's agents.example.yml.
#
# The repo's name is this directory's name, kebab-cased. It is not configurable: it is
# also the prefix on every skill installed here (library skill `db.md` -> `$name-db`)
# and the name the workflow tooling reads off the checkout, and those must agree.

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
# the packs listed here are merged.
#
# The two seeded here are the base library's, and every repo takes both: `general`
# is the cross-cutting craft a repo owes whatever it is written in (architecture,
# testing, accessibility, vertical slicing, bug diagnosis, code review) and
# `stablemate` is the toolchain that reads it (farrier, ostler, groom, workhorse).
# Add the stack pack for what this repo is built with — `go`, `flutter`,
# `python-workflow`, `react-router`, `pulumi`, `infra` — beneath them.
packs:
  - general
  - stablemate

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


def default_config(repo: Path) -> str:
    """Render the starter ``agents.yml`` for the repository rooted at *repo*."""
    return _TEMPLATE.substitute(name=repo_prefix(repo))
