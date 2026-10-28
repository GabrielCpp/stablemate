---
type: fixture
title: Missing editable source
---
# Missing editable source

A `pipx` stub that lists an editable distribution whose source directory does not exist.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### pipx-stub

- kind: seed
- run: mkdir -p "$dir/pipx-stub-bin" && mkdir -p "$(dirname "$dir/pipx-stub-bin/pipx")" && printf '%s\n' '#!/bin/sh' 'printf '"'"'%s\n'"'"' '"'"'{"pipx_spec_version":"0.1","venvs":{"workhorse-workflows":{"metadata":{"main_package":{"package":"workhorse-workflows","package_or_url":"/nonexistent/acme-source","pip_args":["--editable"],"package_version":"1.2.0","apps":["workhorse-coder"],"include_apps":true}}}}}'"'"'' 'exit 0' > "$dir/pipx-stub-bin/pipx" && chmod +x "$dir/pipx-stub-bin/pipx"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
