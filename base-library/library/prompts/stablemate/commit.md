---
description: Commit the finished work on the current branch and push it — one concern per commit, staged by explicit path, with a Conventional Commits subject
argument-hint: "[what to commit, if the tree holds more than one concern]"
---

# Commit and push

Land the work that is finished right now. Not the session's whole diff — the
concern that just became complete.

$ARGUMENTS

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

Run the repo's gate, not just the test you were staring at. In stablemate:

```bash
make lint          # ruff + ty, every subproject in one pass, from the repo root
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
- **scope**: the *package* that gets released, not the module inside it —
  `fix(workhorse):`, not `fix(runner):`. Omit the parentheses for a repo-wide
  change.
- Subject ≤ 72 characters, no capital first word, no trailing period.

A repaired defect labelled `chore:` ships to nobody, and the omission surfaces
weeks later as a bug report against a version that never contained the fix.

The `commit-msg` hook rejects a subject that violates this. `--no-verify` is not
a way to get a commit in; it is a way to get an unreleasable commit in.

## 6. Stay on the branch you are on

Do not create a branch, switch branches, or open a PR unless you were asked to.
The work goes onto whatever branch is checked out.

## 7. Push it now

```bash
git push
```

Right after the commit, before starting the next concern. A local commit is still
invisible to review, to CI and to release-please, and it still dies with the
machine — which for an agent run in a throwaway container is the normal ending,
not the unlucky one.

**When the push is rejected, reconcile — do not force.** The remote moved, which
is information: fetch, rebase onto the new tip, re-run the gate, push again.
`--force` onto a shared branch discards whatever moved it, which in a repo
several agents push to is somebody else's committed work.

### When an SSH push hangs instead of failing

An `ssh://` or `git@` remote can block forever: a passphrase prompt with no
terminal to answer it, an unknown host key waiting on a `yes`, an agent socket
not forwarded into the container. Make it fail in seconds instead:

```bash
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
  timeout 60 git push
```

When that errors out, push over HTTPS with a GitHub token:

```bash
gh auth setup-git && timeout 60 git push          # preferred: gh owns the credential
```

Without `gh`, pass the token to that one push and let it disappear:

```bash
timeout 60 git push "https://x-access-token:${GITHUB_TOKEN}@github.com/<org>/<repo>.git" HEAD
```

**Never persist that URL.** `git remote set-url` with a token in it writes the
secret into `.git/config`, where it survives the session and shows up in any
diagnostic that dumps the remote. Do not echo the token, and never paste a push
command containing one into a commit message, an issue, or a PR body. If no token
is available, say so and leave the commit local — an unpushed commit the user
knows about is recoverable; a pushed secret is not.

## 8. If the change touches code a live run is holding

A push does not reach a run that is already going. If you changed anything under
`workflows/` or `workhorse/` and a run is in flight, the commit is not the last
step — reload each run that holds the old copy. See the `reload-runs` command.
