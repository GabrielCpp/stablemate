---
type: concept
title: Prompt rendering
---
# Prompt rendering

A node's prompt is a Jinja2 template, rendered with the run's values just before its
[agent turn](agent-turns.md). A prompt file resolves against the workflow directory and the
folder beside it. An inline prompt written in the state's own
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

A workflow can render a prompt without running a turn, through `Workflow.render_prompt(prompt,
args)`. It returns the text the turn would send with those values, and it writes no step and no
node record. A workflow uses it to keep a brief on disk, so a later turn can read it again. A dry
run returns `(dry-run) <prompt>` instead of the text.

A retired helper, such as `skill_file` or `prompt_ref`, fails the render and names the helper
that replaced it.

Every run scans the prompts under `prompts/` before it starts. The scan reports each skill a
prompt names that is not installed, and each retired helper call. A reference inside an
`{% if has_skill(...) %}` block is skipped, because the guard keeps it from rendering. The report
starts `N skill reference(s) will fail to render:` and tells the operator to install the skill
with `farrier install`. A live run prints it as a `[workhorse] WARNING:` and goes on. A dry run
prints it as a `[workhorse] ERROR:` and exits 1. The [shared core](shared-core.md) holds the catalog the helpers resolve
against.

- rule: a repository changes what a turn says through its instruction files and skills, or for a coder role through `workflow.prompts`, and no path under `.agents/` overrides a prompt file.
- code: `workhorse/workhorse/templates.py::render` @c276df74955b
- code: `workhorse/workhorse/templates.py::template_globals` @886c35bc48ef
- code: `workhorse/workhorse/references.py::missing_references` @8e2d760ce437
- code: `workhorse/workhorse/references.py::format_missing` @076d76edf355
- code: `workhorse/docs/CHECKING.md` @792e2e8e883a
- code: `workhorse/workhorse/pyflow/workflow.py::Workflow.render_prompt` @be399583fec8
- tests: `workhorse/tests/test_pipeline.py::test_a_dry_run_render_returns_the_placeholder`
- tests: `workhorse/tests/test_pipeline.py::test_a_render_returns_the_text_a_turn_would_send_and_writes_no_step`
