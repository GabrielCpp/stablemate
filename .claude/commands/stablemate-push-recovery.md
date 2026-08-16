---
description: "Get a stuck `git push` to land — bound an SSH remote that hangs instead of failing, then fall back to HTTPS with a token that never outlives the push"
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

## 1. Make an SSH remote fail in seconds

An `ssh://` or `git@` remote can block forever: a passphrase prompt with no
terminal to answer it, an unknown host key waiting on a `yes`, an agent socket
not forwarded into the container. None of those ever time out on their own.

```bash
GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' \
  timeout 60 git push
```

## 2. When that errors out, push over HTTPS

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
command containing one into a commit message, an issue, or a PR body.

## 3. When no transport works, stop and say so

Leave the commit local and tell the user which transports you tried and how each
failed. An unpushed commit the user knows about is recoverable; a pushed secret is
not, and neither is a silent hang nobody was told about.

## When the push is rejected rather than stuck

That is a different problem with a different answer: the remote moved. Fetch,
rebase onto the new tip, re-run the gate, push again — never `--force` onto a
shared branch, which discards whatever moved it. The `commit` command covers it.
