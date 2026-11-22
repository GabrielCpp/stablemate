---
name: commit-and-push
description: "The standing procedure every finished change lands under: one concern per commit, the gate before the commit, staged by explicit path never `-A`, a Conventional Commits subject release-please can read, and a push over HTTPS with `gh` holding the credential rather than the human's SSH key. The scope vocabulary, the gate command and the story-id footer are templated per repo; a repo with a follow-on step adds it through `commit_epilogue`."
hooks:
  - stage: commit-msg
    run: scripts/check_commit_message.py
---

# Commit

Load {{ skill_link("commit") }} before you stage or commit anything. It holds the
procedure: one concern per commit, the gate before the commit, staging by explicit
path, and a subject release-please can read. The `commit-msg` hook rejects a subject
that breaks it, and `--no-verify` only gets an unreleasable commit in.
