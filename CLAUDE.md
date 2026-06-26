# stablemate

A `uv` workspace monorepo of the agent-workflow tooling: **workhorse** (the YAML
workflow runner/engine), **farrier** (the installer), and **ostler** (the doc-graph
validator). Python ≥ 3.12. Each subproject has its own README/CLAUDE.md — read those
before changing that component.

## Python linting (load-bearing)

This repo is linted with **ruff**. Keep it clean — zero findings is the bar, and a
change isn't done until `ruff check` passes.

```bash
ruff check .            # from the repo root: lint every subproject
ruff check . --fix      # apply the autofixable ones (unused imports, etc.)
```

- Run it from the **repo root** before wrapping up any Python change, so all of
  workhorse/farrier/ostler are covered in one pass.
- Fix the finding, don't silence it: prefer correcting the code over adding
  `# noqa` or broadening ignores. Reach for config/ignores only when a rule is
  genuinely wrong for this codebase, and say why.
- The same bar applies to test files — unused imports, ambiguous names (`l`/`I`/`O`),
  and multi-statement semicolon lines are findings, not style preferences.
- ruff config, when present, lives in the root `pyproject.toml` under `[tool.ruff]`;
  keep it there so every subproject shares one ruleset.
