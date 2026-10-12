---
type: concept
title: Prompt rendering
---
# Prompt rendering

A node's prompt is a Jinja2 template, rendered with the run's values just before its
[agent turn](agent-turns.md). A prompt file resolves against the workflow directory and the
folder beside it. A repository can override one prompt by placing a file of the same name under
`.agents/flavors/<workflow>/`, and the override wins. An inline prompt written in the state's own
source renders in the same environment as a prompt file.

An undefined value renders empty and logs a `[template] ⚠` warning, so one missing value does not
stop the turn. Every prompt can call these helpers:

- `workhorse_var(name)` reads one run value, or an empty string.
- `get_node_output(node, key)` reads a key from an earlier node's `output.json`.
- `agent_cli()` names the CLI the turn runs on.
- `skill_link(name)`, `skill_path(name)` and `skill_command(name)` point at an installed skill.
  `skill_command` renders `/<skill>` for claude and copilot, `$<skill>` for codex, and a sentence
  telling the agent to read the file for any other CLI.
- `find_by_tags(...)` links every installed skill carrying all the given tags.
- `has_skill(name)` tells whether a skill is installed.

A retired helper, such as `skill_file` or `prompt_ref`, fails the render and names the helper
that replaced it.

Every run scans the prompts under `prompts/` before it starts. The scan reports each skill a
prompt names that is not installed, and each retired helper call. A reference inside an
`{% if has_skill(...) %}` block is skipped, because the guard keeps it from rendering. The report
starts `N skill reference(s) will fail to render:` and tells the operator to install the skill
with `farrier install`. A live run prints it as a `[workhorse] WARNING:` and goes on. A dry run
prints it as a `[workhorse] ERROR:` and exits 1. The [shared core](shared-core.md) holds the catalog the helpers resolve
against.

- code: `workhorse/workhorse/templates.py::render` @921bcf52f398
- code: `workhorse/workhorse/templates.py::template_globals` @921bcf52f398
- code: `workhorse/workhorse/references.py::missing_references` @c6ff9b16296e
- code: `workhorse/workhorse/references.py::format_missing` @c6ff9b16296e
- code: `workhorse/docs/CHECKING.md` @4a88f2550736
