---
type: fixture
slug: vendor-scratch-base-and-skills
title: vendor scratch base and skills
---
# vendor scratch base and skills

Seeds `vendor-scratch/`, holding two things the vendored `stablemate_core` copy resolves on its
own: `base-lib/library/`, an empty directory shaped like a usable base library root, and
`.claude/skills/demo-skill/SKILL.md`, a one-skill library a `claude` harness would load, named
`demo-skill` in its own front matter.

## Steps

### write-vendor-scratch

- kind: seed
- run: mkdir -p vendor-scratch/base-lib/library vendor-scratch/.claude/skills/demo-skill vendor-scratch/home && printf -- '---\nname: demo-skill\n---\n# Demo skill\n' > vendor-scratch/.claude/skills/demo-skill/SKILL.md
