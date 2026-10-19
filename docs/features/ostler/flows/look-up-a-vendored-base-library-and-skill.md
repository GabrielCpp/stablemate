---
type: flow
slug: look-up-a-vendored-base-library-and-skill
title: Look up a vendored base library and skill
---
# Look up a vendored base library and skill

- start: `STABLEMATE_BASE_DIR` names a directory holding `library/`, and a `claude`-harness
  skills folder holds one skill
- steps:
  - [vendor-base-library-and-skill-lookup](../standalone-programs.md#vendor-base-library-and-skill-lookup)
- end: the vendored copy resolves the named base library, rejects a profile its config does not
  define, and renders the one skill's link and slash command the same way the unvendored copy
  would
- verify: exit_status(code=0)
- fixture: [vendor scratch base and skills](../fixtures/vendor-scratch-base-and-skills.md)
- detail: [Vendored stablemate-core](../concepts/vendored-stablemate-core.md)
