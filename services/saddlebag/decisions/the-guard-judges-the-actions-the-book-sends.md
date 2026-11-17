story: none
date: 2026-11-16
elements: GuardHook, GuardInstall, GuardBare

The guard reads a PreToolUse payload from stdin, prints one JSON deny decision when the action would read a dotenv, a key
file or an export, and prints nothing otherwise (saddlebag/saddlebag/guard.py). The book models the readers and the
protected names the payloads it sends reach: cat of a dotenv, a Read of a key file or an export, an example file, an action
no rule names, and `saddlebag exec` leading a command. A line of shell the parser would split differently is outside it.

`guard install` writes the hook into the project's or the home's `.claude/settings.json`, keeping what the file held.
