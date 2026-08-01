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
make install  # once per clone: venv + hooks (`make hooks` for the hooks alone)
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

## A workflow reads no environment (load-bearing)

`os.environ` / `os.getenv` are **prohibited** anywhere under
`workflows/src/workhorse_workflows/`. Everything a node or a state needs is an argument
or a workflow parameter — a field on the `Workflow` subclass, settable with `--param`.
A value read from the environment is in no checkpoint (so a resume silently takes a
different one) and in no telemetry, and `--params` cannot set it.

The process boundary is where the environment belongs, and it is outside that package:
`workhorse/cli/run.py` and `workhorse/entrypoint.sh` translate `$FOO` into `--params`
once, on the way in. The one allowlisted module is `kit/credentials.py`, and for the
opposite reason — a secret must *never* become a checkpointed `--param`.

```bash
make check-no-env    # also runs as part of `make test`
```

The full rule, including `Workflow.injects` for the ambient paths
(`repo_dir`/`docs_path`/`workspace_file`), is in
[workflows/README.md](workflows/README.md).

## Python linting (load-bearing)

This repo is linted with **ruff** *and* type-checked with **ty**. Keep both clean — zero
findings is the bar, and a change isn't done until `make lint` passes.

```bash
make lint               # both, from the repo root — every subproject in one pass
ruff check . --fix      # apply the autofixable ones (unused imports, etc.)
```

`make test` runs `make lint` first, so a type error fails the suite rather than waiting
for a reviewer.

- Run it from the **repo root** before wrapping up any Python change, so all of
  workhorse/farrier/ostler are covered in one pass.
- Fix the finding, don't silence it: prefer correcting the code over adding
  `# noqa` / `# ty: ignore` or broadening ignores. Reach for config/ignores only when a
  rule is genuinely wrong for this codebase, and say why.
- The same bar applies to test files — unused imports, ambiguous names (`l`/`I`/`O`),
  multi-statement semicolon lines, and a fake that has drifted from the port it stands
  in for are findings, not style preferences.
- `# type: ignore[...]` is mypy's spelling and is **inert** for ty. The one that
  suppresses is `# ty: ignore[rule]`, and it names the rule.
- Config for both lives in the root `pyproject.toml` (`[tool.ruff]`, `[tool.ty]`); keep
  it there so every subproject shares one ruleset. ty runs with every rule at its default
  severity and no ignore list — the only exception is a path in `[tool.ty.src] exclude`.

The full rationale, and the fixes that recur, are in the `python-cli`, `python-testing`
and `python-architecture` skills.

## Commit messages are Conventional Commits (load-bearing)

Releases are cut by **release-please**, which reads commit subjects and nothing else.
The type is therefore not a style preference — it is the input that decides whether a
package ships and at what version:

| Subject                    | Effect on the package named by the scope |
| -------------------------- | ---------------------------------------- |
| `feat:`                    | minor bump                               |
| `fix:` / `perf:` / `refactor:` | patch bump                           |
| `<type>!:` or a `BREAKING CHANGE:` body paragraph | major bump        |
| `docs:` `test:` `build:` `ci:` `chore:` | **no release at all**       |

A repaired defect labelled `chore:` ships to nobody, and the omission surfaces weeks
later as a bug report against a version that never contained the fix. That is the
failure this rule exists to prevent.

```
<type>(<scope>): <lowercase imperative description>

<optional body, wrapped at 72 columns, explaining why — not what>
```

- **types**: `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore` `revert`.
  Pick by what the change *is*, not how large it is: a rename, a move or an extraction
  is `refactor`, never `feat`.
- **scope**: one tracked top-level directory — `core`, `workhorse`, `workflows`,
  `farrier`, `ostler`, `groom`, `saddlebag`, `base-library`, `benchmarks`, `docs`,
  `scripts` — or one of `deps`, `release`, `ci`, `lint`, `hooks`. It names the
  *package*, not the module inside it: `fix(workhorse):`, not `fix(runner):`, because
  the package is what gets released. Omit the parentheses entirely for a repo-wide change.
- Subject ≤ 72 characters, no capital first word, no trailing period.
- **One concern per commit.** A stage spanning four unrelated changes cannot be labelled
  correctly by any single type, so whichever type is chosen withholds a release from the
  other three. Split first, then label.

```bash
make install  # installs .githooks/commit-msg alongside the private-names hook
```

`.githooks/commit-msg` rejects a subject that violates the above, deriving the valid
scopes from the tracked top-level directories so a new workspace member needs no edit.
`git commit --no-verify` bypasses it. A generated message — Zed's *Generate commit
message*, an agent's — only ever biases toward this format; the hook is what makes it
hold.
