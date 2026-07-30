---
agent: agent
---

# Document the story (OKF UI profile)

The implementation just passed review and is about to enter QA context generation. Your
job is to **merge everything this story changed into the current OKF book** so new services,
screens, components, commands, endpoints, interactions, concepts, formats, and flows are
documented before QA derives obligations. This is an incremental one-story update, not a
changelog or a bulk build.

Load the skill and follow it: {{ skill_load_ref("stablemate-documentation", skill_dir() + "/stablemate-documentation/SKILL.md") }}
It carries the full loop (scaffold → author → fmt → doctor), the node-type vocabulary, and
the linter rules; obey it. The reference for the type table and bullets is the
`stablemate-ostler` skill it links to.

## Inputs

- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- OKF features root: `{{ workhorse_var('features_root') }}`
- Context mode: `{{ workhorse_var('context_mode') }}`
- Context notes: `{{ workhorse_var('context_notes') }}`
- Previous deterministic gate notes: `{{ workhorse_var('gate_notes') }}`
- Previous semantic review notes: `{{ workhorse_var('review_notes') }}`

## Steps

1. **Scope what changed.** Read the story's acceptance criteria and its `spec_dir`
   (`plan-context.json` lists the services/repos it touched). Inspect both the working tree and
   commits made on the current story/epic branch since its base, including QA, regression, CI, and
   merge remediation. From that complete implementation delta,
   identify what *user-facing surface, element, behavior, concept, or format* the story
   added or changed — a screen/component/interaction (GUI), a cli/command (CLI), a
   server/endpoint/invocation (HTTP/WS), a domain or code `concept`, a `flow`, or a
   `format`.
2. **If the story touched no documentable contract** (pure internal refactor, test-only,
   or configuration with no externally observable contract), return `not_required` with
   exact reasons. Do **not** invent nodes. New source files or symbols are not automatically
   internal: represent a new service, surface, element, behavior, domain/code concept, or
   format unless the diff proves otherwise.
3. **Otherwise, apply the skill's loop from existing code (Playbook B):** `ostler search`
   / `ostler list` for the node if it exists; `ostler scaffold` it if not; author the
   as-built prose and structured bullets; set `code:` / `verify:` to the **real**
   `path::symbol` you just wrote (omit `verify:` rather than invent a test that doesn't
    exist). Keep every path link resolving.
   Never weaken an invariant, journey completion condition, persistence rule, event
   contract, or concurrency requirement merely to match the implementation. Such drift
   is a product/author decision, not a grounding edit.
4. **Converge:** run `ostler fmt <the docs you touched>` then `ostler doctor` (from the
   docs root, `-C` if needed). Fix any error by its named remedy until `doctor` is green
   for the nodes you touched. In `semantic` multi-repo mode, repository-local doctor cannot
   resolve service-repo `code:` paths beneath the separate docs root: report its
   `dangling-code-ref` / `missing-code-symbol` findings for independent review, but do not return
   `blocked` for those two grounding codes alone. Every structural, relation, schema, and local
   grounding error remains blocking. Never silence a finding by deleting a meaningful bullet.

This is a hard gate. If the graph cannot be updated without changing an author-owned
normative decision, return `blocked`; never claim success or remove requirements to pass.

## Output

Output JSON only:

```json
{"documentation_result": {"status": "documented", "nodes": ["docs/features/acme/gui/screens/example.md#example-panel"], "notes": "Updated the current OKF contracts and grounding for the reviewed implementation."}}
```

`documentation_result.status` is one of `documented`, `not_required`, or `blocked`.
`documented` means the full current contracts are updated and `doctor` has no error finding in
the affected nodes. Report unrelated pre-existing findings but do not rewrite unrelated books.
`not_required` requires a precise explanation of why no observable contract changed.
For `documented`, `nodes` must list every affected OKF node by exact graph identity, preserving
section anchors. For `not_required`, return an empty `nodes` list.
