## This is a `uv` workspace monorepo

One `uv.lock` and one venv at the root serve every member. A member is not a
separate environment to activate — it is a package in the same resolution.

```bash
uv sync --all-packages   # every member importable
uv run <cmd>             # from the ROOT, against that one venv
```

`--all-packages` is load-bearing, not thoroughness. A bare `uv sync` (and the
implicit sync a bare `uv run` performs) resolves **this root and its dev group
only** — every other member is absent, and code that imports one dies with
`ModuleNotFoundError` on a machine where nothing is wrong. That failure reads as
a broken import, which is why it costs an afternoon.

Python ≥ 3.12.

- **A member's dependency belongs in that member's `pyproject.toml`**, not the
  root's. The root pins the workspace and the dev tooling; a dependency added
  there is invisible to the package that actually needs it the moment that
  package is installed on its own.
- **Every member has a README, and it is the thing to read before changing that
  member** — before its source, and instead of hunting for a per-package
  instruction file. Assume no member carries a nested `CLAUDE.md` / `AGENTS.md`
  — one that does is the exception, and it is there in the directory to be seen.
- **Run tools from the root**, so one pass covers every member. A lint or a type
  check run inside a single package sees a subset of the code and a subset of
  the config.

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
`$STABLEMATE_PRIVATE_NAMES`, or `$GIT_DIR/private-names`,
one name per line (`.git/` is never committed). It lives in
`scripts/private_names.py`.

```bash
make install  # once per clone: the hooks that enforce this
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
make check-public    # also runs as part of `make test`
```

Both failure modes are invisible on the one machine where the private overlay is
configured and shadows everything, which is why they need a check rather than
attention.

---

## No ad-hoc shell scripts (load-bearing)

A capability goes into the **unified CLI** — a subcommand or module in the
package that owns the concern, or a guard under
`scripts/` for a repo-level check. Never a
new `.sh` beside the last one.

The reason is mechanical, not aesthetic. A shell script is outside every gate
this repo has: the linter does not read it, the type checker does not read it,
and the test runner cannot import it. So the discipline that holds everywhere
else stops at its first line — and because a script is the cheapest thing to
write, they accumulate: three files that each do two-thirds of the same job
under names that do not say so, and no test that would notice when one of them
stops working. "I'll just add a quick script" is how a codebase acquires a
second, unversioned, untested build system.

The rewrite is usually smaller than it looks. A script that greps a tree and
exits non-zero is a function plus a `main()`; what it gains is a name in an
import graph, a test that can call it directly, and a reviewer who can see it.

Shell is allowed exactly where **another program dictates the interface** — git
execs a hook, Docker execs an entrypoint as PID 1. Those files delegate on their
second line to the real language, which is the shape this rule asks for. They
are named in the guard's `ALLOWED` set, and adding to it is a decision somebody
makes on purpose, not a step in getting a task done.

```bash
make check-no-shell   # also runs as part of `make test`
```

Two enforcement points, one rule, one file —
`scripts/check_no_shell.py`.
A `PreToolUse` hook runs it with `--hook` and denies the tool call *before* the
file exists — the point at which the decision is still free — and the sweep
above scans every **tracked** file, because a hook only ever covers the machine
it is installed on. A script committed from a clone with no hook configured is
in the tree forever otherwise.

---

## Python linting (load-bearing)

This repo is linted with **ruff** and type-checked with **ty** *and*
**basedpyright**. Keep all three clean — zero findings is the bar, and a change
isn't done until `make lint` passes.

```bash
# all three, from the repo root — every package in one pass
make lint
# apply the autofixable ruff findings (unused imports, etc.)
ruff check . --fix
```

Run it from the **repo root** before wrapping up any Python change, so every
package is covered in one pass. The test target runs it first, so a type error
fails the suite rather than waiting for a reviewer.

**Two type checkers is deliberate.** ty is fast and follows this repo's own
calls; basedpyright carries pyright's inference and its bundled third-party
stubs, so it sees through libraries ty treats as opaque. They disagree often
enough that each catches defects the other misses — neither one is the
redundant one, and a finding from either is a finding.

- **Fix the finding, don't silence it.** Prefer correcting the code over adding
  `# noqa` / `# ty: ignore` / `# pyright: ignore` or broadening an ignore. Reach
  for config only when a rule is genuinely wrong for this codebase, and say why.
- **The same bar applies to test files** — unused imports, ambiguous names
  (`l`/`I`/`O`), multi-statement semicolon lines, and a fake that has drifted
  from the port it stands in for are findings, not style preferences.
- **`# type: ignore[...]` is mypy's spelling and is inert for both.** ty reads
  `# ty: ignore[rule]`; basedpyright reads `# pyright: ignore[rule]`. Each names
  the rule, and each is ignored by the other checker — a suppression that
  silences one still has to answer to the other.
- **Run basedpyright with `-p <config>`.** Invoked without it, it does not read
  the `[tool.basedpyright]` table in `pyproject.toml`: it silently falls back to
  its own default mode over its own default tree, and reports a different set of
  findings than the gate does.

---

# Commit and push

Land the work that is finished right now. Not the session's whole diff — the
concern that just became complete.

## 1. Look at the tree before you touch it

```bash
git status --porcelain
git diff
```

Someone else may be writing here. A concurrent agent, a background run, or the
human may own some of these paths. Anything you did not change is not yours to
commit — leave it, and say so if it blocks you.

## 2. Split into one concern per commit

If what is uncommitted spans a fix, a refactor and a doc change, that is three
commits, not one. The reason is mechanical, not aesthetic: release-please reads
one type per commit, so a batch ships under whichever label you picked and the
other concerns ship under a version that does not describe them — or do not ship
at all.

Split first, then label.

## 3. Run the gate, before the commit

Run the repo's gate, not just the test you were staring at:

```bash
make lint          # ruff + ty + basedpyright, every subproject in one pass, from the root
```

plus the affected test package. The gate belongs on the *near* side of the push,
because pushing is what makes a failure everyone's problem.

## 4. Stage by explicit path

```bash
git add path/to/changed.py path/to/test_changed.py
```

Never `git add -A`, `git add .`, or `git commit -a`. Those sweep in whatever else
is in the tree — and in a repo several processes are editing, that silently takes
someone else's half-finished work and makes it vanish from *their* `git status`.

## 5. Write the subject release-please can read

```
<type>(<scope>): <lowercase imperative description>

<optional body, wrapped at 72 columns, explaining why — not what>

Story: <story id>
```

| Subject                                           | Effect on the package named by the scope |
| ------------------------------------------------- | ---------------------------------------- |
| `feat:`                                           | minor bump                               |
| `fix:` / `perf:` / `refactor:`                    | patch bump                               |
| `<type>!:` or a `BREAKING CHANGE:` body paragraph | major bump                               |
| `docs:` `test:` `build:` `ci:` `chore:`           | **no release at all**                    |

- **types**: `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore`
  `revert`. Pick by what the change *is*, not how large it is — a rename, a move
  or an extraction is `refactor`, never `feat`.
- **scope**: the *package* that gets released, not the module inside it. One
  tracked top-level directory — `core`, `workhorse`, `workflows`, `farrier`, `ostler`, `groom`, `saddlebag`, `base-library`, `paddock`, `docs`, `scripts` — or one of
  `deps`, `release`, `ci`, `lint`, `hooks`. Omit the parentheses
  entirely for a repo-wide change.
- Subject ≤ 72 characters, no capital first word, no trailing period.
- **story id**: every commit that answers a tracked piece of work carries its
  identifier as a footer at the **end of the message**, spelled exactly as the
  block above and nowhere else. Not in the subject — those 72 characters belong
  to the type, the scope and the description release-please reads, and a
  bracketed id both eats a fifth of them and says the same thing twice. One
  spelling is the whole point: the footer is a key git itself parses
  (`git log --format=%(trailers:key=Story)`), it is what tooling joins a commit
  to its story by, and a second copy in another shape is a second thing to keep
  in sync. The link then survives a rebase, a squash and a changelog render, and
  the commit is findable from the story months later without a full-text search.
  Do not invent one: a change with no story behind it — a drive-by typo fix, a
  release chore — omits the footer rather than making an id up, because a wrong
  id points a reader at somebody else's work.

A repaired defect labelled `chore:` ships to nobody, and the omission surfaces
weeks later as a bug report against a version that never contained the fix.

The `commit-msg` hook derives those scopes from the tracked top-level
directories, so a new package needs no edit, and it rejects a subject that
violates any of this. A generated message — an editor's *Generate commit
message*, an agent's — only ever biases toward the format; the hook is what
makes it hold. `--no-verify` is not a way to get a commit in; it is a way to get
an unreleasable commit in.

## 6. Stay on the branch you are on

Do not create a branch, switch branches, or open a PR unless you were asked to.
The work goes onto whatever branch is checked out.

## 7. Push it now — over HTTPS, with `gh` holding the credential

```bash
GIT_TERMINAL_PROMPT=0 timeout 120 git -c credential.helper='!gh auth git-credential' \
  push "https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner).git" \
  "HEAD:refs/heads/$(git branch --show-current)"
```

Right after the commit, before starting the next concern. A local commit is still
invisible to review, to CI and to release-please, and it still dies with the
machine — which for an agent run in a throwaway container is the normal ending,
not the unlucky one.

**Do not push over the remote's `git@` URL.** The SSH key is the human's, it is
usually passphrase-protected, and an agent that reaches for it either hangs on a
prompt nobody can answer or spends the user's key on its own behalf. `gh` is
already authenticated for this account, so the explicit `https://` URL above is
what an agent pushes with — the remote itself is left alone, and the token lives
in the one push that uses it. It never goes into `.git/config`, a commit message
or a PR body, and `git remote set-url` with a token in it is how it gets there.

`git push -u` cannot set upstream through an ad-hoc URL. Do it once, separately,
so `git status` still reports ahead/behind:

```bash
git branch --set-upstream-to="origin/$(git branch --show-current)"
```

**When the push is rejected, reconcile — do not force.** The remote moved, which
is information: fetch, rebase onto the new tip, re-run the gate, push again.
`--force` onto a shared branch discards whatever moved it, which in a repo
several agents push to is somebody else's committed work.

**A push that hangs is not a push that failed.** The commit is finished, the work
looks done, and nothing says otherwise — so bound every push with `timeout`, as the
command above does. When it errors out rather than landing, leave the commit local
and say which transport you tried and how it failed. An unpushed commit the user
knows about is recoverable; a silent hang nobody was told about is not.

## 8. If the change touches code a live run is holding

A push does not reach a run that is already going. If you changed anything under
`workflows/` or `workhorse/` and a run is in flight, the commit is not the last
step — reload each run that holds the old copy, rather than restarting it. The
procedure is in the `workhorse-scripting` skill
(`references/reloading-a-live-run.md`).
