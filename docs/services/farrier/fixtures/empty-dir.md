---
type: fixture
title: Empty directory
---
# Empty directory

A directory named by `dir` inside the scenario checkout, holding nothing. The checkout root holds the real `agents.yml`, so a command that expects none runs in this directory instead. Its config holds only `config_version` and its home directory `home` is empty.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
