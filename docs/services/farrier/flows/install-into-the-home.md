---
type: flow
slug: install-into-the-home
title: Install into the home
---
# Install into the home

An operator selects personal skills in the shared config and installs them for every project at once.

- start: the shared config holds a `[user_library.claude]` table
- steps:
  - [install the user library](../farrier-invocations.md#install-the-user-library)
- end: the selected skills sit in the harness home directory (commands: [install --user](../farrier-commands-install.md#install---user))
- verify: created(subject="c204/home/.claude/skills/demo/SKILL.md")
- fixture: user-library-home dir=c204
- detail: [user library](../concepts/user-library.md)
