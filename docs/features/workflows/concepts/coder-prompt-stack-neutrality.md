---
type: concept
slug: coder-prompt-stack-neutrality
title: Coder prompt stack neutrality
---
# Coder prompt stack neutrality

A Coder prompt envelope has never met the repo it will run against, so it may not hardcode a
technology stack in its prose. It refers to an installed capability only behind a guard such as
`{% raw %}{% if has_skill("ostler-cli") %}{% endraw %}`, or hands the choice of skill to a subagent
that reads the repo's own skills. A tag helper such as `find_by_tags` renders nothing when the repo
installs no match, so a sentence around one carries a `default(...)` or an `{% raw %}{% if %}{% endraw %}` guard.

The defect this holds the line against was not hypothetical: a repo with a React web app and a
docs site, and no mobile code anywhere, rendered the planning prompt with ten mentions of
Flutter and Dart. The reference helpers correctly dropped the unresolved skill names; the body
prose around them still enumerated a fixed menu of every stack the author had thought of. The
agent believed the prose.

Every prompt envelope under every Coder flow package (`coder/*/prompts/*.md`) is rendered once
per registered stack (`web`, `mobile`, `backend`, `infra`). Each render runs against a repo whose
`.claude/skills` holds only that stack's skills and the docs skill. The render must not raise
`MissingSkill`. A raise means the prompt named a skill by a name no repo is obliged to install,
when it should have asked for it by tag or guarded it with `has_skill`. The rendered output must
also carry no other stack's product-name vocabulary, such as `Flutter`, `Dart` or `Riverpod` in a
web-only render. Value vocabulary the workflow itself understands is exempt. A backticked or quoted
`services[].type` value from `plan-context.json` documents an accepted value, which is not a claim
that the repo has that stack.

A tag that the test does not also add to `STACKS` in its fixtures would make every neutrality
assertion trivially pass, so the test's own skill set is exhaustive over the stacks it checks.

- code: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-story.md` @83320cf5160a
- tests: `workflows/tests/coder/test_prompt_stack_neutrality.py::test_each_prompt_is_neutral_for_the_stack_that_renders_it`
- detail: [Coder prompt role resolution](coder-prompt-role-resolution.md)
- detail: [`find_by_tags`](../../workhorse/concepts/prompt-rendering.md#prompt-rendering)
- detail: [prompt rendering](../../workhorse/concepts/prompt-rendering.md)
