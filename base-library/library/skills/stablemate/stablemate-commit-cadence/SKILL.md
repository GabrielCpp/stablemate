---
name: stablemate-commit-cadence
description: "Commit as you go, on the branch you are already on, with a Conventional Commits subject — one commit per finished concern, staged by explicit path, never `git add -A`. Covers when to commit (each coherent unit, not at the end of the session), what the subject must be (release-please reads it and nothing else), and how to stage safely in a tree another process is also writing to. Load when finishing any unit of work in a git repo, before running `git commit`, when deciding whether to batch changes, or when a working tree holds changes that are not yours."
applyTo: ""
tags: [standards, workflow]
---

# Commit cadence

> A finished change that is still only in the working tree is not finished — it is a
> change one `git checkout` away from never having existed, and it is invisible to
> everyone reviewing, bisecting, or releasing. Commit each concern as it lands.

## Commit as you go

Do not accumulate a session's work into one commit at the end. When a unit of work is
complete — a fix plus its regression test, a doc section, a refactor — commit it before
starting the next one.

Batching costs three things that are hard to recover:

- **Bisect resolution.** Twelve unrelated changes in one commit means `git bisect` lands
  on "the big one" and tells you nothing.
- **A correct release.** release-please picks *one* type per commit. A batch spanning a
  `fix` and a `refactor` and a `docs` change gets whichever label was chosen, and the
  other concerns ship under a version that does not describe them — or do not ship at all.
- **Recoverable state.** A long-running agent loop that crashes mid-session loses
  everything uncommitted. Committed work survives.

**Stay on the current branch.** Committing as you go does not mean branching as you go —
do not create a branch, switch branches, or open a PR unless asked. The work goes onto
whatever branch is checked out.

**One concern per commit.** This is the same rule as the message format, applied earlier:
a commit that cannot be labelled by a single type should have been two commits. Split
first, then label.

## The subject is the release input

Every commit subject is a Conventional Commit, because release-please reads commit
subjects and squash-merge PR titles and *nothing else*:

```
<type>(<scope>): <lowercase imperative description>

<optional body, wrapped at 72 columns, explaining why — not what>
```

| Subject                                           | Effect on the package named by the scope |
| ------------------------------------------------- | ---------------------------------------- |
| `feat:`                                           | minor bump                               |
| `fix:` / `perf:` / `refactor:`                    | patch bump                               |
| `<type>!:` or a `BREAKING CHANGE:` body paragraph | major bump                               |
| `docs:` `test:` `build:` `ci:` `chore:`           | **no release at all**                    |

The type is therefore not a style preference. A repaired defect labelled `chore:` ships to
nobody, and the omission surfaces weeks later as a bug report against a version that never
contained the fix.

- **types**: `feat` `fix` `perf` `refactor` `docs` `test` `build` `ci` `chore` `revert`.
  Pick by what the change *is*, not how large it is — a rename, a move or an extraction is
  `refactor`, never `feat`.
- **scope**: the *package* that gets released, not the module inside it —
  `fix(workhorse):`, not `fix(runner):`. Omit the parentheses for a repo-wide change.
- Subject ≤ 72 characters, no capital first word, no trailing period.

## Stage by path, never by wildcard

`git add -A`, `git add .` and `git commit -a` stage whatever else is in the tree. In a
repo where a concurrent agent, a background run, or the human is also editing, that
silently sweeps someone else's half-finished work into your commit — and then into
their next `git status`, where it has vanished.

```bash
git status --porcelain                       # look first: whose changes are these?
git add path/to/changed.py path/to/test.py   # name every path
git commit -m "fix(workflows): stop a heading label doubling in its subject"
```

If a path you need to change is one you did not write — a file another process has staged
— stop and say so rather than committing over it.

## Before you commit

Run the repo's gate, not just the test you were staring at. In stablemate that is
`make lint` from the root (ruff *and* ty, every subproject in one pass) plus the affected
test package. A commit that fails the gate is a commit someone else has to bisect to.

The `commit-msg` hook rejects a subject that violates the format above. `--no-verify`
bypasses it; that is not a way to get a commit in, it is a way to get an unreleasable
commit in.
