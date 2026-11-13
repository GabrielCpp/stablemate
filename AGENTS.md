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

## Private project names stay out

This repo is public. A private project name never enters a tracked file, a
path or a commit message. Write a neutral placeholder instead: acme, globex,
api-service, web-app, mobile-app, example.com.

The names themselves live outside the repo, in `$STABLEMATE_PRIVATE_NAMES` or
`$GIT_DIR/private-names`. Never copy them into a tracked file, and never print
the list.

Every agent commit runs a check over the staged files and the commit message.
A refusal lists each line that carries a name. Replace each one, restage, and
commit again. A name already in history needs a rewrite with
`git filter-repo --replace-text`, not a removal commit.

---

## The book comes first

Each service of this repository has a book under `services/<name>/`. The book is
the current spec of the service. Its Python states what every endpoint, screen
and command does, which rule refuses a call, and which journeys a user lives
through. Ostler plays it against the running app. Its `decisions/` folder holds,
in markdown, why a behaviour is so and which story settled it.

Read the book before the code whenever the question is *what* something does,
*why* it is so, or *how a user reaches it*:

```bash
ostler book search <term> [--service services.<name>] [--kind rule|endpoint|action|journey|screen|decision]
ostler book explain services.<name> <ClassName>       # everything the book says of one element
ostler book decisions services.<name> [--story <id>]  # each decision and the story behind it
```

Read the code to learn *how it is implemented*. A grep over source that starts
before a search over the book re-derives what is already written down, and gets
it wrong wherever the code has a legacy twin the book would have steered you
away from. A story writer and an implementer both read the decisions a story
touches before they write.

## A story is done when the book plays it

A story is a delta. The book is the whole. The story is finished when the delta
is in the book in the same change as the code, which means all of:

- Every record, rule, action, endpoint, screen and journey the story changed
  states the new current behaviour. Restructure the book when the story needs
  it. The structure a first pass chose is not a contract.
- Every assumption or tradeoff settled for the story, at the start or along the
  way, is a file under `services/<name>/decisions/`, or a line added to the
  decision that already covers it. A decision that lives only in a chat or a
  story file is lost to the next reader.
- Every `source=` pointer names code that exists:
  `ostler book check services.<name> --app <app root>` passes.
- `ostler book run services.<name>` is green on the story's code. A claim no
  call and no screen can observe is checked by the story's QA and stays out of
  the book.

Write the book with the `ostler-book` skill. It carries the format, the order of
work and the bar for each element.

## A service with no book yet

A service with no `services/<name>/service.py` has no book. Write one from its
source with the okf-book workflow, `workhorse-okf-book run python_book`, or by
hand with the `ostler-book` skill. The book is the only form of spec this
repository keeps. No page under `docs/services/` is read or written.

---

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
