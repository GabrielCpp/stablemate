---
type: cli
slug: farrier
title: farrier — render the agent prompt library into a repository
---
# farrier — render the agent prompt library into a repository

farrier renders an agent-neutral prompt library into a target repository's Codex/Claude/Copilot
adapters, driven by that repo's `agents.yml`. It ships no library content of its own — it renders
from a [layer stack](concepts/library-directory.md#the-layer-stack): an optional *overlay* library,
located by the `--library` flag, the `$FARRIER_LIBRARY_DIR` env var or `library_dir` in the
[shared home config file](formats/home-config.md) (set with `farrier config set-library`), stacked above the
*base* library that ships with stablemate. Either alone is a working setup; with neither, farrier
exits with a setup hint. `farrier [--repo DIR]` with a leading flag rather than a recognized
subcommand is treated as `install`; a bare `farrier` with no arguments at all prints the top-level
help instead, the same as `farrier --help`. Both rules live in `main`. Repository installs also
refresh [QA-evidence ignore rules](concepts/qa-evidence-ignore-rules.md) when they render the
staged-files gate.

- binary: `farrier` (the console script is declared as `farrier.install:main`, which re-exports
  `main` from `farrier.cli` — `install.py` is a compatibility facade that declares nothing of its
  own)
- code: `farrier/farrier/cli.py::main` @0244d6a97e3b
- detail: [hook manager wiring](concepts/hook-manager-wiring.md)
- detail: [QA-evidence ignore rules](concepts/qa-evidence-ignore-rules.md)
- detail: [selection error reporting](concepts/selection-errors.md)
- detail: [vendored core package](concepts/vendored-core-package.md)
- detail: [drift report](concepts/drift-report.md)
- detail: [repository diagnosis](concepts/doctor-diagnosis.md)
- detail: [library front-matter check](concepts/library-frontmatter-check.md)
- detail: [front-matter parsing](concepts/frontmatter-parsing.md)
- detail: [library view](concepts/library-view.md)
- detail: [output installation](concepts/output-installation.md)
- detail: [output cleanup](concepts/output-cleanup.md)
- detail: [scaffold operations](concepts/scaffold-operations.md)
- detail: [template values](concepts/template-values.md)
- detail: [user library](concepts/user-library.md)
- detail: [CLI internals](concepts/cli-internals.md)
- detail: [compatibility facade](concepts/compatibility-facade.md)
- detail: [runtime clock](concepts/runtime-clock.md)
- detail: [initialize and render repository](flows/initialize-and-render-repository.md)
- detail: [inspect and maintain library](flows/inspect-and-maintain-library.md)
- detail: [verify and repair generated outputs](flows/verify-and-repair-generated-outputs.md)
- detail: [Farrier CLI and Make drivers](ops/farrier-cli-and-make-drivers.md)

**Exit codes:** `0` on success; commands raise `SystemExit(message)` on error, which propagates as
a nonzero exit with the message printed to stderr. `install --check` specifically returns `1` when
any generated file is missing or would be rewritten, `0` when the repo's generated files are
already current.

## Commands

- [farrier-commands-init](farrier-commands-init.md)
- [farrier-commands-install](farrier-commands-install.md)
- [farrier-commands-workflows](farrier-commands-workflows.md)

## Invocations

- [farrier-invocations](farrier-invocations.md)
