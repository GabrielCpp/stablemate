# Commit

Load [stablemate-commit](.agents/skills/stablemate-commit/SKILL.md) before you stage or commit anything. It holds the
procedure: one concern per commit, the gate before the commit, staging by explicit
path, and a subject release-please can read. The `commit-msg` hook rejects a subject
that breaks it, and `--no-verify` only gets an unreleasable commit in.

---

## The book comes first

Each service has a book under `services/<name>/` under the book root: the repository
root in a monorepo, the artifacts folder in a multi-repo workspace. The book is
the current spec of the service. Its Python states what every endpoint, screen
and command does, which rule refuses a call, and which journeys a user lives
through. Ostler plays it against the running app. Its `decisions/` folder holds,
in markdown, why a behaviour is so and which story settled it.

Read the book before the code whenever the question is *what* something does,
*why* it is so, or *how a user reaches it*:

```bash
ostler book search <term> [--service services.<name>] [--kind rule|endpoint|interaction|action|journey|screen|decision|company|team|product|question|event|outside]
ostler book explain services.<name> <ClassName>       # everything the book says of one element
ostler book decisions services.<name> [--story <id>]  # each decision and the story behind it
ostler book pages [--level company|team|product]      # the pages above every service, one line each
```

Four books hold the rules, by reach: the service book under `services/<name>/`,
the product book in `product/`, the team book in `teams/<team>/` and the company
book in `company/` of the artifacts dir. Agents write service and product pages.
People write team and company pages. When two disagree the order of authority is
company, team, product, service decision, story. Report a conflict and settle
neither side.

Read the code to learn *how it is implemented*. A grep over source that starts
before a search over the book re-derives what is already written down, and gets
it wrong wherever the code has a legacy twin the book would have steered you
away from. A story writer and an implementer both read the decisions a story
touches before they write.

## A story is done when the book plays it

A story is a delta. The book is the whole. The story is finished when the delta
is in the book in the same change as the code. In a multi-repo workspace that
change is two commits: the book's in the artifacts folder, the code's in its
repository. Finished means all of:

- Every record, rule, action, endpoint, screen and journey the story changed
  states the new current behaviour. Restructure the book when the story needs
  it. The structure a first pass chose is not a contract.
- Every assumption or tradeoff settled for the story, at the start or along the
  way, is a file under `services/<name>/decisions/`, or a line added to the
  decision that already covers it. A decision that lives only in a chat or a
  story file is lost to the next reader.
- Every `source=` pointer names code that exists:
  `ostler book check services.<name> --app <code repo root>` passes. A pointer into
  another repository is `repo://<member>/<path>`.
- `ostler book run services.<name>` is green on the story's code. A claim no
  call and no screen can observe is checked by the story's QA and stays out of
  the book.

Write the book with the `ostler-book` skill. It carries the format, the order of
work and the bar for each element.

## A service with no book yet

A service with no `services/<name>/service.py` has no book. Write one from its
source with the okf-book workflow, `workhorse-okf-book run python_book`, or by
hand with the `ostler-book` skill. The book is the only form of spec this
repository keeps.

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

## Staged Python passes ruff

`make lint` runs ruff over the whole tree, so a staged Python file that fails the
repository's ruff config turns it red. Every agent commit runs ruff over the staged
Python files, as the index holds them, and a refusal lists each finding. Fix the
file, restage, and commit again.

## Staged Python passes ty and basedpyright

`make lint` also runs ty and basedpyright, so a staged Python file that fails either
turns it red. Every agent commit exports the index to a scratch tree and runs both
over the staged Python files there, under the repository's `pyproject.toml` and the
root's `.venv`. Each file is judged as the index holds it, next to the other files
the index holds. A refusal lists each finding with its file and line. Fix the file,
restage, and commit again.

Both checkers run over the staged files only. A file that is not staged is not
re-judged, so a change that breaks a caller in an unstaged file shows up in
`make lint` and not in this check.

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
