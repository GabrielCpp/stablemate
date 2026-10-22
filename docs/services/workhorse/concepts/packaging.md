---
type: concept
title: Packaging
---
# Packaging

Workhorse is a library, so nobody runs a command called `workhorse`. The distribution is
`workhorse-agent`, version 4.0.0, under the MIT license, and it needs Python 3.12 or newer. It
declares no console script. A workflow distribution binds its own script, such as
`workhorse-coder`, to what `console_script(...)` returns, as [CLI dispatch](cli-dispatch.md)
describes. Installing that distribution pulls workhorse in as a dependency.

OpenTelemetry is a hard dependency, so an installed run is always observable. The `otel` extra
is kept empty, so an old `workhorse-agent[otel]` install line still resolves. The `test` extra
adds pytest and pytest-xdist.

A workflow's prompts render from the directory its package occupies on disk, so the package has
to be installed unpacked. Any wheel that pip or uv installs is unpacked. A zipapp, a zip-safe egg
or a namespace package split across roots is not, and the run refuses it at startup with
`... is not a real directory on disk`. A package name that does not import fails with
`cannot locate package '<package>'`. The [`version`](../workhorse.md#version) command prints the installed distribution's
version. The changelog records each release's breaking changes, features and fixes.

- code: `workhorse/workhorse/packaged.py::package_dir` @7eeb988b4091
- code: `workhorse/workhorse/packaged.py::PackagedWorkflowError` @7eeb988b4091
- code: `workhorse/pyproject.toml` @f025c95695b7
- code: `workhorse/README.md` @dcfcb86a041c
- code: `workhorse/workhorse/README.md` @ae6c81203345
- code: `workhorse/CHANGELOG.md` @c90a5202513a
- code: `workhorse/LICENSE` @cfa64d417f35
