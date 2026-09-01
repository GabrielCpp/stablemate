---
name: commit-and-push
description: "The standing procedure every finished change lands under: one concern per commit, the gate before the commit, staged by explicit path never `-A`, a Conventional Commits subject release-please can read, and a push over HTTPS with `gh` holding the credential rather than the human's SSH key. The scope vocabulary, the gate command and the story-id footer are templated per repo; a repo with a follow-on step adds it through `commit_epilogue`."
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
{{ template.commit_gate | default("make lint") }}
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

{{ template.commit_ticket_trailer | default("Story: <story id>") }}
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
  tracked top-level directory — {{ template.commit_scopes | default("the repo's tracked top-level directories") }} — or one of
  {{ template.commit_extra_scopes | default("`deps`, `release`, `ci`") }}. Omit the parentheses
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

{{ template.commit_epilogue | default("") }}
