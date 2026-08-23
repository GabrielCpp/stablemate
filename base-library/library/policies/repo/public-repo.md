---
name: public-repo
description: "The standing rule for a repository that ships publicly while its author also works on private ones: no private project's name may appear in the tree, examples use neutral placeholders, and the denylist itself lives outside the repo because a denylist publishes the words it bans. Carries the two-layer enforcement (a commit hook over staged changes, a whole-tree-and-history sweep over everything else) with the script and command names templated."
---

## This repo is public (load-bearing)

This repository ships publicly. **No private project's name may appear in it** —
not in prose, not in a fixture, not in a code comment, not in a path. Examples
use neutral placeholders:

| Placeholder                            | Stands for                       |
| -------------------------------------- | -------------------------------- |
| `acme`, `globex`                       | a client repo / brand            |
| `api-service`, `web-app`, `mobile-app` | repos in a multi-repo workspace   |
| `example.com`, `example-org`           | hostnames, GitHub orgs           |

The banned names are deliberately **not written down anywhere in the tree** — a
denylist publishes the words it bans, and so does a hash of one.
The resolver reads them from an untracked source instead — the environment variable
`${{ template.private_names_env | default("PRIVATE_NAMES") }}`, or `$GIT_DIR/private-names`,
one name per line (`.git/` is never committed). It lives in
`{{ template.private_names_script | default("scripts/private_names.py") }}`.

```bash
{{ template.private_names_install | default("make install") }}  # once per clone: the hooks that enforce this
```

The hook blocks any commit whose staged paths or added lines carry a configured
name. With no list configured — a public contributor — it is a no-op.

The same resolver backs the whole-tree sweep the hook cannot be, since the hook
only ever sees staged changes. It scans every **tracked** file (path and
content), walks the **reachable git history** (a name committed and later
removed still ships in every clone, and only a rewrite fixes it), and asserts
that what this repo publishes stands alone — that nothing tracked here depends
on the private overlay to work.

```bash
{{ template.check_public_command | default("make check-public") }}
```

Both failure modes are invisible on the one machine where the private overlay is
configured and shadows everything, which is why they need a check rather than
attention.
