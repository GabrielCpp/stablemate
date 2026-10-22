---
type: flow
slug: set-up-the-machine
title: Set up the machine
---
# Set up the machine

An operator points farrier at their prompt library, reads back the setting and checks the installed farrier before touching a repository.

- start: the shared config file holds no library setting
- steps:
  - [print the version](../farrier-invocations.md#print-the-version)
  - [record the library](../farrier-invocations.md#record-the-library)
- end: the shared config file names the library directory (commands: [version](../farrier-commands-init.md#version), [config](../farrier-commands-init.md#config))
- verify: contents(subject="c208/c.toml", text="library_dir")
- fixture: library-dir-with-packs dir=c208
- detail: [home config](../formats/home-config.md)
