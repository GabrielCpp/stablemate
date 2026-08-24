---
type: format
slug: generated-file-metadata
title: Generated-file metadata block
---
# Generated-file metadata block

The `metadata:` mapping farrier stamps into every generated skill/command's YAML front matter, via
`skill_metadata_block`. Without it, an agent editing a generated file "fixes" a copy — the edit is
lost on the next `make agent-install`. Skills carry it natively (the openskill format defines
`metadata`); Claude commands carry the same block — the slash-command parser ignores keys it
doesn't recognise, so the block is inert to the consuming agent. [`farrier source`](farrier.md#source)
reads the block back via `frontmatter_metadata` to resolve a generated file to its editable library
origin.

- file: front matter of any farrier-generated `SKILL.md` / command `.md` under `.claude/`,
  `.agents/`, or `.github/`
- code: `farrier/farrier/renderer.py::skill_metadata_block` — read back by
  `farrier/farrier/frontmatter.py::frontmatter_metadata`

## Fields

### generated_by    <!-- required -->
- type: `string` — required: yes — default: `"farrier"` (constant)

Always the literal string `farrier`; marks the file as tool-generated rather than hand-authored.

It is also what makes the file *deletable*: install removes only files carrying this mark, so a
hand-written skill kept next to the generated ones survives, and a path farrier wants to write that
holds an unmarked file aborts the install instead of overwriting it. See
[ownership](farrier.md#ownership) — and note that a generated `SKILL.md` covers its bundled
`references/`/`scripts/` too, which carry no front matter of their own.

### source    <!-- required -->
- type: `string` — required: yes — default: none

The generated file's origin within the prompt library, as a **library-anchored, machine-independent
path** — anchored at the last `library/` path segment (e.g. `library/skills/go/go-qa/SKILL.md`), so
the same value is identical across machines and stable under `install --check`. Computed by
`library_source_path`. Joined under the resolved [library directory](concepts/library-directory.md)
by `farrier source` to print this machine's absolute editable path.

### resolve    <!-- required -->
- type: `string` — required: yes — default: none

A copy-pasteable command, `farrier source <dest_rel>`, where `dest_rel` is the generated file's own
repo-root-relative path. Running it prints the real editable source path on the current machine.

### do_not_edit    <!-- required -->
- type: `string` — required: yes — default: fixed warning text

A human-readable warning: run the `resolve` command for this machine's editable source path, edit
that, then `make agent-install` to regenerate this file.

### tags
- type: `list<string>` — required: no — default: omitted

The library source's own `tags:`, normalized (lowercased, deduplicated, order-preserving) and
emitted as a YAML flow list — `tags: [web, tests]` — only when the source declares any. Tags say
what the skill *answers* rather than what it is called, which is how a workflow prompt asks for a
capability it has no name for; the run-time half of that query is workhorse's
`find_by_tags(*tags)`, reading the same values out of the [context
manifest](../workhorse/context-manifest.md#instruction_tags). They ride inside `metadata:` rather
than at the front matter's top level for the same reason the rest of this block does: it is the
namespace every harness's parser already ignores.
