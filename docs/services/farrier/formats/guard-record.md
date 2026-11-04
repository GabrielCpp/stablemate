---
type: format
slug: guard-record
title: Guard record
---
# Guard record

A guard record is one YAML file, `library/hooks/<name>/hook.yml`, that declares one [home guard](../concepts/home-guard.md)
in no harness's tool names. The folder name is the name a `[user_library.<harness>]` table lists in `hooks`.
The guard's scripts sit beside the record and install with it, except a `tests` or `__pycache__` folder.
An unknown key stops the install and names the file.

- file: `library/hooks/<name>/hook.yml` in any library layer, the highest layer holding the name winning
- code: `farrier/farrier/home_guards.py::Guard` @49a3b45636c9
- detail: [home guard](../concepts/home-guard.md)

## Fields

### field: command
- type: string
- required: true
- semantics: the command the harness runs on a watched call, with `{dir}` standing for the shell-quoted folder the guard installs into, `~/.agents/hooks/<name>`

### field: watches
- type: list of `shell`, `edit`, `read`, `search`
- required: true
- semantics: the kinds of tool call the guard checks, in the order the matcher lists them, each spelled by the harness's own tool names

### field: timeout
- type: integer
- required: false
- semantics: the seconds the harness gives the command, left out of the group when absent, and 60 in the OpenCode bridge when absent

### field: status
- type: string
- required: false
- semantics: the message the harness shows while the command runs, written as `statusMessage`

### field: not_on
- type: list of harness names
- default: `[]`
- semantics: the harnesses this guard must not reach, because it would block ordinary work there, so a table of such a harness selecting it installs nothing and prints a note
