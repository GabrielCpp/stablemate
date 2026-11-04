---
type: format
slug: home-entry-ledger
title: Home entry ledger
---
# Home entry ledger

The home entry ledger is the JSON file, `~/.agents/.farrier-home.json`, that names each
[merged home entry](../concepts/merged-home-entry.md) farrier installed. It maps a home-relative file
to a container key to a list of entry names, such as `{".claude.json": {"mcpServers": ["playwright"]}}`.
The name of a [home guard](../concepts/home-guard.md) is the command it runs, under the container `hooks.PreToolUse`. It holds names only, so it holds no value of any server. Farrier writes it before it edits a shared
file, so an interrupted install still owns what it wrote. A file that does not parse stops the install.

- file: `~/.agents/.farrier-home.json`, written only once the home holds an entry farrier installed
- code: `farrier/farrier/home_entries.py::read_ledger` @395465036a31
- code: `farrier/farrier/home_entries.py::write_ledger` @7b043b64478c
- detail: [merged home entry](../concepts/merged-home-entry.md)
