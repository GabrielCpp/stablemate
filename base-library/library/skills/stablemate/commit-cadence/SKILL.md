---
name: commit-cadence
description: "Commit and push as you go, on the branch you are already on, with a Conventional Commits subject — one commit per finished concern, staged by explicit path, never `git add -A`, pushed before the next concern starts. Covers when to commit (each coherent unit, not at the end of the session), when to push (right after each commit), how to reconcile a rejected push without forcing, what to do when an SSH push hangs instead of failing (fail fast with BatchMode, then fall back to a GitHub token without persisting it), what the subject must be (release-please reads it and nothing else), and how to stage safely in a tree another process is also writing to. Load when finishing any unit of work in a git repo, before running `git commit` or `git push`, when deciding whether to batch changes, or when a working tree holds changes that are not yours."
applyTo: ""
tags: [standards, workflow]
---

# Commit cadence

> A finished change that is still only in the working tree is not finished — it is a
> change one `git checkout` away from never having existed, and it is invisible to
> everyone reviewing, bisecting, or releasing. Commit each concern as it lands, and
> push it before you start the next one.

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

## Push as you go

Push each commit as you make it — `git push` right after `git commit`, on the branch you
are already on. Do not save the pushing for the end of the session either.

A local commit fixes only the first of the three costs above. The other two survive:

- **A local commit is still invisible.** Nobody can review it, CI has not run it, and
  release-please has not seen it. Work that exists only on one machine is work the rest
  of the system is still waiting on.
- **A local commit is still one laptop away from gone.** `git commit` protects against
  `git checkout`; it does not protect against a dead disk, a discarded container, or a
  worktree someone cleans up. An agent run in a throwaway environment is the common case
  here, and its commits vanish with the environment unless they were pushed.

Pushing per commit also keeps the push itself cheap. Twenty commits pushed at once is one
event that either lands or is rejected as a block; a rejected push after a long session is
where "just rebase it" turns into an afternoon. Pushing each commit surfaces divergence at
the first commit that diverged, when it is still one commit to reconcile.

**When a push is rejected, reconcile — do not force.** A rejection means the remote moved,
which is information, not an obstacle. Fetch, rebase your commit onto the new tip, re-run
the gate, and push again. `--force` onto a shared branch discards whatever moved it, which
in a repo several agents are pushing to is somebody else's committed work.

The exceptions are narrow and worth naming, because outside them there is no reason to
hold a commit back:

- The remote is one you were not asked to publish to, or the branch is not yours to move.
- The work is deliberately staged locally for a rebase you are mid-way through.
- Pushing would trigger something outward-facing — a deploy, a release, a notification —
  that the user has not agreed to. Ask first; the commit can wait one message.

### When an SSH push hangs, fall back to the token

An `ssh://` or `git@` remote can block forever rather than fail: a passphrase prompt with
no terminal to answer it, an unknown host key waiting on a `yes`, or an agent socket that
is not forwarded into the container. A human sees the prompt and types; an agent sees a
command that never returns, and the commit stays unpushed.

Make the hang fail fast instead, so you find out in seconds:

```bash
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
  timeout 60 git push
```

`BatchMode=yes` turns every interactive prompt into an immediate error, and the `timeout`
catches the cases it does not cover. When that errors out, push over HTTPS with a GitHub
token instead:

```bash
gh auth setup-git && timeout 60 git push          # preferred: gh owns the credential
```

`gh` writes a credential helper rather than a secret, which is why it is the first choice.
Without `gh`, pass the token in the URL for that one push:

```bash
timeout 60 git push "https://x-access-token:${GITHUB_TOKEN}@github.com/<org>/<repo>.git" HEAD
```

**Never persist that URL.** `git remote set-url` with a token in it writes the secret into
`.git/config`, where it survives the session, gets read by every later command, and shows
up in any diagnostic that dumps the remote. Pass it to the single `push` invocation and let
it disappear. For the same reason, do not echo the token, and do not paste a push command
containing one into a commit message, an issue, or a PR body.

If no token is available either, say so and leave the commit local — an unpushed commit the
user knows about is recoverable; a pushed secret is not.

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

Run the gate *before* the commit, not between the commit and the push. Pushing is the step
that makes a failure everyone's problem, so the gate belongs on the near side of it — and a
green gate is the thing that makes pushing immediately safe rather than reckless.
