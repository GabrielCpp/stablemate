---
agent: agent
---

# Document the story (OKF UI profile)

The implementation just passed review and is about to enter QA context generation. Your
job is to **record or refresh its implementation grounding** in the docs graph so the
diff-to-OKF mapper sees current `code:` and `verify:` references. This is the incremental,
one-story update, not a bulk build or a change to author-owned normative behavior.

Load the skill and follow it: {{ skill_load_ref("stablemate-documentation", skill_dir() + "/stablemate-documentation/SKILL.md") }}
It carries the full loop (scaffold → author → fmt → doctor), the node-type vocabulary, and
the linter rules; obey it. The reference for the type table and bullets is the
`stablemate-ostler` skill it links to.

## Inputs

- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- OKF features root: `{{ workhorse_var('features_root') }}`

## Steps

1. **Scope what changed.** Read the story's acceptance criteria and its `spec_dir`
   (`plan-context.json` lists the services/repos it touched). From the diff/working tree,
   identify what *user-facing surface, element, behavior, concept, or format* the story
   added or changed — a screen/component/interaction (GUI), a cli/command (CLI), a
   server/endpoint/invocation (HTTP/WS), a domain or code `concept`, a `flow`, or a
   `format`.
2. **If the story touched no documentable surface** (pure internal refactor, test-only,
   config), output `{"doc_status": "skipped"}` and stop. Do **not** invent nodes.
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
   for the nodes you touched. Never silence a finding by deleting a meaningful bullet.

Fail soft: if ostler is unavailable or the docs don't use the profile, output
`{"doc_status": "skipped"}` — never block the story.

## Output

Output JSON only:

```json
{"doc_status": "documented"}
```

`doc_status` is one of `documented` (you wrote/updated nodes and `doctor` is green),
`skipped` (nothing to document, or the repo doesn't use OKF), or `partial` (you updated
docs but a pre-existing unrelated `doctor` error remains).
