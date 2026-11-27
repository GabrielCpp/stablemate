# Commit

Load [stablemate-commit](.agents/skills/stablemate-commit/SKILL.md) before you stage or commit anything. It holds the
procedure: one concern per commit, the gate before the commit, staging by explicit
path, and a subject release-please can read. The `commit-msg` hook rejects a subject
that breaks it, and `--no-verify` only gets an unreleasable commit in.

---

## The book comes first

Each service has a book under `services/<repo>/<name>/` in the artifacts folder, or
`services/<name>/` in a repository that keeps its book (`book.home: repo`). Below,
`<module>` is `services.<repo>.<name>` or `services.<name>`. The book's Python
states what every endpoint, screen and command does, which rule refuses a call, and
which journeys a user lives through. Its `decisions/` folder says why. Read the book
before the code whenever the question is *what* something does, *why* it is so, or
*how a user reaches it*:

```bash
ostler search <term> [--root books,pages,docs] [--service <module>] [--kind rule|endpoint|interaction|action|journey|screen|decision|company|team|product|question|event|outside]
ostler book explain <module> <ClassName>       # everything the book says of one element
ostler book decisions <module> [--story <id>]  # each decision and the story behind it
ostler book pages [--level company|team|product]      # the pages above every service, one line each
```

A grep over source that starts before a search over the book gets it wrong wherever
the code has a legacy twin. Read the code to learn *how it is implemented*. A story
writer and an implementer both read the decisions a story touches before they write.

Four books hold the rules: service, product, team and company. Agents write service
and product pages. People write team and company pages. When two disagree the order
of authority is company, team, product, service decision, story. Report a conflict
and settle neither side.

## A story is done when the book plays it

The story's delta lands in the book in the same change as the code. Finished means
all of:

- Every element the story changed states the new current behaviour.
- Every assumption or tradeoff settled for the story is a file under the
  book's `decisions/`, or a line in the decision that already covers it.
- `ostler book check <module> --app <code repo root>` passes.
- `ostler book run <module>` is green on the story's code.

A service with no book gets a book first, from the okf-book workflow
(`workhorse-okf-book run python_book`) or by hand. The `ostler-book` skill carries
where the book lives, how its branch lands, the format and the bar.

---

## Private project names stay out

This repo is public. A private project name never enters a tracked file, a path or
a commit message. Write a neutral placeholder instead: acme, globex, api-service,
web-app, mobile-app, example.com. The list lives in `$STABLEMATE_PRIVATE_NAMES` or
`$GIT_DIR/private-names`. Never print it or copy it into a tracked file.

A commit check refuses each staged line that carries a name. A name already in
history needs `git filter-repo --replace-text`, not a removal commit.

---

## Staged Python passes ruff, ty and basedpyright

`make lint` runs all three over the whole tree. Every agent commit runs them over
the staged Python files as the index holds them, and a refusal lists each finding.
Fix the file, restage, and commit again. A change that breaks a caller in an
unstaged file shows up only in `make lint`.

---

## This is a `uv` workspace monorepo

One `uv.lock` and one root venv serve every member. Run `uv sync --all-packages`
and run every tool from the root with `uv run <cmd>`. A bare `uv sync` or
`uv run` installs the root alone, so an import of another member dies with
`ModuleNotFoundError` on a healthy machine. Python ≥ 3.12.

- A member's dependency goes in that member's `pyproject.toml`, not the root's.
- Read a member's README before changing it. No member carries a nested
  `AGENTS.md`.
