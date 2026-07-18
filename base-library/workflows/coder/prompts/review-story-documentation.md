---
agent: agent
---

# Review Story Documentation

Independently review the frozen implementation diff and the current OKF book after the
documentation author has finished. Do not edit code or documentation. Your decision is a hard
gate before QA.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- Features root: `{{ workhorse_var('features_root') }}`
- Author status: `{{ workhorse_var('author_status') }}`
- Author notes: `{{ workhorse_var('author_notes') }}`
- Deterministic gate: `{{ workhorse_var('gate_notes') }}`

Read the story, plan context, working tree, branch commits since the story/epic base, and affected
OKF nodes. Include QA, regression, CI, merge-resolution, and inline-fix mutations made after the
initial review. Approve only when the book
describes the complete current system rather than this story as a changelog. In particular:

- every new or changed service, screen, component, interaction, CLI command, endpoint,
  invocation, flow, concept, and format has the correct typed node and reachable relationships;
- structured bullets contain the full behavioral contract, including states, fields,
  preconditions, effects, errors, accessibility, and boundaries where applicable;
- `code:` and `verify:` cite real implementation and tests without using broad or invented refs;
- unchanged surrounding behavior remains complete, so the documented node could guide a
  behavior-equivalent implementation;
- author-owned requirements were not weakened to match code;
- `not_required` is used only when the diff is genuinely internal and changes no observable or
  reusable contract. A new service, screen, component, endpoint, command, flow, concept, or format
  is never `not_required`.

Return JSON only:

```json
{"documentation_review": {"status": "approved", "notes": "The current OKF book fully covers the reviewed implementation delta."}}
```

Use `status=revise` with precise node/path findings when the author can correct the book. Use
`status=blocked` only when convergence requires a product or author decision. Never approve on
the promise of a later documentation update.
