# stablemate

A `uv` workspace monorepo of the agent-workflow tooling: **workhorse** (the runner
driving an agent CLI through a checkpointed Python state machine), **workflows**
(those state machines), **farrier** (the installer), **ostler** (the doc-graph
validator), plus `core`, `groom`, `saddlebag`, `base-library` and `benchmarks`.
Python ≥ 3.12. Every subproject has a README — read it before changing that
component. Only `workhorse/` also has a nested `CLAUDE.md`; the other eight are
README-only, so don't hunt for per-package instruction files that aren't there.

A workflow is **Python**, not YAML. The YAML engine is retired — no `workflow.yml`,
no `requires:` block, no node-graph document. Prose describing one is stale; fix it.

## stablemate is public (load-bearing)

This repo ships publicly. No private overlay project's name may appear in it — not in
prose, not in a fixture, not in a code comment. Examples use neutral placeholders:

| Placeholder                          | Stands for                          |
| ------------------------------------ | ----------------------------------- |
| `acme`, `globex`                     | a client repo / brand               |
| `api-service`, `web-app`, `mobile-app` | repos in a multi-repo workspace    |
| `example.com`, `example-org`         | hostnames, GitHub orgs              |

The banned names are deliberately **not written down anywhere in the tree** — a denylist
publishes the words it bans, and so does a hash of one. `scripts/private_names.py` reads
them from an untracked source instead: `$STABLEMATE_PRIVATE_NAMES`, or
`$GIT_DIR/private-names` (one per line; `.git/` is never committed).

```bash
make hooks    # once per clone: installs .githooks/pre-commit
```

The hook blocks any commit whose staged paths or added lines carry a configured name.
With no list configured (a public contributor) it is a no-op.

The same resolver backs `scripts/check_public.py` — the whole-tree sweep the hook cannot
be, since the hook only ever sees staged changes. It scans every **tracked** file (path
and content) and also asserts the base library stands alone, i.e. that no base skill or
workflow depends on the private overlay. Both failure modes are invisible on a machine
where the overlay is configured and shadows everything, which is why they need a check
rather than attention.

```bash
make check-public    # also runs as part of `make test`
```

## Python linting (load-bearing)

This repo is linted with **ruff**. Keep it clean — zero findings is the bar, and a
change isn't done until `ruff check` passes.

```bash
ruff check .            # from the repo root: lint every subproject
ruff check . --fix      # apply the autofixable ones (unused imports, etc.)
```

- Run it from the **repo root** before wrapping up any Python change, so all of
  workhorse/farrier/ostler are covered in one pass.
- Fix the finding, don't silence it: prefer correcting the code over adding
  `# noqa` or broadening ignores. Reach for config/ignores only when a rule is
  genuinely wrong for this codebase, and say why.
- The same bar applies to test files — unused imports, ambiguous names (`l`/`I`/`O`),
  and multi-statement semicolon lines are findings, not style preferences.
- ruff config, when present, lives in the root `pyproject.toml` under `[tool.ruff]`;
  keep it there so every subproject shares one ruleset.
