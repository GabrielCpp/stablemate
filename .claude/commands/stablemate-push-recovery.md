---
description: "Get a stuck `git push` to land — push through `gh` over HTTPS rather than the human's SSH key, and keep every token inside the one push that uses it"
argument-hint: "[what the push did — hung, refused, asked for a password]"
metadata:
  generated_by: farrier
  source: library/prompts/stablemate/push-recovery.md
  resolve: "farrier source .claude/commands/stablemate-push-recovery.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Recovering a push that will not land

A push that hangs is worse than one that fails: the commit is finished, the work
looks done, and nothing says otherwise. Bound it, then walk down to a transport
that works.

$ARGUMENTS

## 1. Push over HTTPS with `gh` holding the credential

This is the first thing to try, not the fallback. `gh` is already authenticated
for this account, and it needs nothing from the human at push time.

```bash
GIT_TERMINAL_PROMPT=0 timeout 120 git -c credential.helper='!gh auth git-credential' \
  push "https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner).git" \
  "HEAD:refs/heads/$(git branch --show-current)"
```

The remote is left as it is. `gh auth setup-git` does nothing for a `git@` remote,
so naming the `https://` URL explicitly is what actually changes the transport.

Without `gh`, pass a token to that one push and let it disappear:

```bash
timeout 60 git push "https://x-access-token:${GITHUB_TOKEN}@github.com/<org>/<repo>.git" HEAD
```

**Never persist that URL.** `git remote set-url` with a token in it writes the
secret into `.git/config`, where it survives the session and shows up in any
diagnostic that dumps the remote. Do not echo the token, and never paste a push
command containing one into a commit message, an issue, or a PR body.

## 2. Do not fall back to the SSH remote

An agent reaching for `git@` is spending the human's key. It is usually
passphrase-protected, so it blocks forever on a prompt with no terminal to answer
it, an unknown host key waiting on a `yes`, or an agent socket not forwarded into
the container — none of which ever time out on their own. If a human asks for it
anyway, bound it so it fails in seconds rather than hanging:

```bash
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
  timeout 60 git push
```

## 3. When no transport works, stop and say so

Leave the commit local and tell the user which transports you tried and how each
failed. An unpushed commit the user knows about is recoverable; a pushed secret is
not, and neither is a silent hang nobody was told about.

## When the push is rejected rather than stuck

That is a different problem with a different answer: the remote moved. Fetch,
rebase onto the new tip, re-run the gate, push again — never `--force` onto a
shared branch, which discards whatever moved it. The `commit` command covers it.
