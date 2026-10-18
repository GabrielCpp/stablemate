---
type: fixture
title: Two workflows from pipx
---
# Two workflows from pipx

A `pipx` stub in `pipx-stub-bin` that lists one distribution `workhorse-workflows` at version 1.2.0 providing the workflows `planner` and `coder`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### pipx-stub

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/pipx-stub-bin" && mkdir -p "$(dirname "$dir/pipx-stub-bin/pipx")" && printf '%s\n' '#!/bin/sh' 'printf '"'"'%s\n'"'"' '"'"'{"pipx_spec_version":"0.1","venvs":{"workhorse-workflows":{"metadata":{"main_package":{"package":"workhorse-workflows","package_or_url":"workhorse-workflows","pip_args":[],"package_version":"1.2.0","apps":["workhorse-planner","workhorse-coder"],"include_apps":true}}}}}'"'"'' 'exit 0' > "$dir/pipx-stub-bin/pipx" && chmod +x "$dir/pipx-stub-bin/pipx"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
