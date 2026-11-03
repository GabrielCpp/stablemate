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

# Commit

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

plus the affected test package.

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
- **trailer block stays contiguous**: a trailer added after the story id, such
  as an attribution line like `Co-Authored-By:`, goes directly under it with no
  blank line in between. Git's trailer parser reads only the last contiguous
  run of `key: value` lines in the message. A blank line before
  `Co-Authored-By:` ends that run one line early, so the story id trailer above
  it stops parsing, even though it still reads fine on the page.

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

## 7. Keep your commit local by default

You may be working in a local repository or one with a remote so keep your commit local by default.

---

## The book comes first

This repository carries an OKF book under `docs/services/`. It is the current
spec of every service here: what each screen, command and endpoint does, the
concepts behind them, how a user reaches a surface, and which of two similar
things to use. It is indexed, so its size is no reason to skip it.

Read the book before the code whenever the question is *what* something is,
*why* it exists, or *how a user reaches it*:

```bash
ostler search <term> [--type concept|flow|endpoint|screen|command]
ostler trace <id|slug|path>     # walk the graph from a node
ostler reach <screen>           # the documented click-path
```

Read the code to learn *how it is implemented*. A grep over source that starts
before a search over the book re-derives what is already written down, and gets
it wrong wherever the code has a legacy twin the book would have steered you
away from.

## A story is done when the book says so

A story is a delta. The book is the whole. The story is not finished until the
delta is merged into the book in the same change as the code, which means all of:

- Every node whose behaviour changed describes the new current reality
  completely. Never "this story added X".
- Every file a `code:` bullet cites and the change touched is restamped:
  `ostler stamp --node <id>`.
- Every assumption or tradeoff settled for the story, at the start or along the
  way, is a `concept` node with a `rule:` bullet, or a `rule:` added to the
  concept that already covers it. A decision that lives only in a chat or a
  story file is lost to the next reader.
- `ostler doctor` raises no finding on a page the change touched that was not
  there before the change.

Author through `ostler scaffold`, `ostler fmt` and `ostler doctor`, never by
hand-writing frontmatter or a `docs/services/` path. The `ostler-okf` skill
carries the per-type bar and the merge procedure.
