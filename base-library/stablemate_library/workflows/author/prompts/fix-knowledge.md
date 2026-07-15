---
agent: agent
---

# Repair the knowledge record: `{{ workhorse_var('record_path') }}`

The deterministic knowledge validator rejected this surface knowledge record. Your only job is to
make it **parse and validate** again **without changing what it says**. This is a mechanical repair,
not a re-gather: do not investigate the surface, do not add or remove components/gaps, do not restate
findings — just fix the defect the validator flagged.

## Inputs (authoritative)

- Record file to repair: `{{ workhorse_var('record_path') }}`
- Validator errors to fix:

```
{{ workhorse_var('knowledge_errors') }}
```

## What the record is

A Markdown file whose leading `---` fenced block is **YAML front-matter** carrying the structured
fields (the machine source of truth); the prose body beneath it is human-only. The most common
defect is a **YAML syntax error** in that front-matter — and the most common cause is a string value
that was written unquoted (or half-quoted) so YAML mis-parses it. Examples that BREAK and their fix:

- `component: 'default' label in datasheet picker` → a quoted scalar (`'default'`) cannot be followed
  by more text. Quote the **whole** value: `component: "'default' label in datasheet picker"`.
- A value containing a colon-space (`foo: bar`), a leading `>`/`|`/`@`/`` ` ``/`[`/`{`/`*`/`&`/`!`,
  or a trailing `:` — wrap the whole value in double quotes and escape any inner `"` as `\"`.
- A `:` or stray indentation that breaks the block structure — re-indent to match its siblings.

## Task

1. Read `{{ workhorse_var('record_path') }}`.
2. Make the **minimal** edit that resolves every validator error. Prefer quoting/escaping a value
   over rewording it. **Preserve the meaning and wording of every field** — if a value must be
   quoted, keep the same text inside the quotes.
3. Leave the prose body below the front-matter untouched unless it is itself the flagged problem.
4. Do **not** invent fields, drop gaps/components, or change any `id` (downstream stories reference
   gap ids — they must stay byte-stable).

If the error is genuinely a content problem you cannot resolve by a mechanical syntax/structure fix
(e.g. a component truly has no traceable `dataSource` and the fix would require investigating the
surface), make the smallest honest correction the validator demands and note it — do not fabricate.

## Final response (REQUIRED, exact shape)

```json
{
  "fix_knowledge_result": {
    "status": "fixed" | "unfixable",
    "notes": "What you changed (the defect and the edit), or why it cannot be mechanically fixed."
  }
}
```
