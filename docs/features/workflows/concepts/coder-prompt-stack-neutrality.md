---
type: concept
slug: coder-prompt-stack-neutrality
title: Coder prompt stack neutrality
---
# Coder prompt stack neutrality

A Coder prompt envelope has never met the repo it will run against, so it may not hardcode a
technology stack in its prose. It asks for an installed capability by tag —
`{% raw %}{{ find_by_tags("web", "tests") }}{% endraw %}` — and the sentence around that call
carries a `default(...)` or an `{% raw %}{% if %}{% endraw %}` guard, because the helper renders
nothing when the repo installs no match.

The defect this holds the line against was not hypothetical: a repo with a React web app and a
docs site, and no mobile code anywhere, rendered `plan-story`'s prompt with ten mentions of
Flutter and Dart. The reference helpers correctly dropped the unresolved skill names; the body
prose around them still enumerated a fixed menu of every stack the author had thought of. The
agent believed the prose.

Every prompt envelope under every Coder flow package (`coder/*/prompts/*.md`) is rendered once
per registered stack (`web`, `mobile`, `backend`, `infra`) against a manifest holding only that
stack's skills, and the rendered output is checked three ways: no other stack's product-name
vocabulary survives (`Flutter`, `Dart`, `Riverpod` in a web-only render, and so on for each
stack), no skill belonging to another stack is named as a `generated <skill> instruction file`,
and no rendered `generated <name> instruction file when installed` placeholder is left in the
output — that placeholder means a prompt named a skill by a name no repo is obliged to install,
rather than asking for it by tag. Value vocabulary the workflow itself understands (a
backticked or quoted `services[].type` value from `plan-context.json`) is exempted, because
documenting an accepted value is not a claim that the repo has that stack.

The tag vocabulary the coder prompts query is `runbook`, `standards`, `tests`, `qa`, and
`codegen`, each paired with a layer (`backend`, `cli`, `web`, `mobile`, `infra`); it is taught to
skill authors in the `agent-library` skill in base-library, which is where a `tags:` addition is
made. A tag the test does not also add to `STACKS` in its fixtures would make every neutrality
assertion trivially pass, which is why the test's own manifest is exhaustive over the stacks it
checks, and a companion check confirms the stack a repo does have still reaches the rendered
prompt.

- code: `workflows/src/workhorse_workflows/coder/dev/prompts/plan-story.md`
- code: `workflows/tests/coder/test_prompt_stack_neutrality.py::test_each_prompt_is_neutral_for_the_stack_that_renders_it`
- tests: `workflows/tests/coder/test_prompt_stack_neutrality.py::test_each_prompt_is_neutral_for_the_stack_that_renders_it`
- detail: [Coder prompt role resolution](coder-prompt-role-resolution.md)
- detail: [`find_by_tags`](../../workhorse/concepts/farrier-globals.md)
- detail: [prompt rendering](../../workhorse/concepts/render-prompt.md)
