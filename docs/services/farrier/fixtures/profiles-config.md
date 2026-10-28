---
type: fixture
title: Profiles config
---
# Profiles config

A config file `c.toml` in `dir` with `[profiles.cheap.powers.high]` model `haiku` and a top-level `[powers.high]` model `opus`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### config

- kind: seed
- run: mkdir -p "$(dirname "$dir/c.toml")" && printf '%s\n' '[powers.high]' 'model = "opus"' '' '[profiles.cheap]' 'cli = "claude"' '' '[profiles.cheap.powers.high]' 'model = "haiku"' > "$dir/c.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
