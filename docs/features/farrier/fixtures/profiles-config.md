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
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### config

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/c.toml")" && printf '%s\n' '[powers.high]' 'model = "opus"' '' '[profiles.cheap]' 'cli = "claude"' '' '[profiles.cheap.powers.high]' 'model = "haiku"' > "$dir/c.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
