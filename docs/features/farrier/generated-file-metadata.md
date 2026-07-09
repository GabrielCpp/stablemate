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
- code: `farrier/farrier/install.py::skill_metadata_block` — read back by
  `farrier/farrier/install.py::frontmatter_metadata`

## Fields

### generated_by    <!-- required -->
- type: `string` — required: yes — default: `"farrier"` (constant)

Always the literal string `farrier`; marks the file as tool-generated rather than hand-authored.

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
