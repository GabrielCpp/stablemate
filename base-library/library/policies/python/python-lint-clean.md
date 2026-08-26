---
name: python-lint-clean
description: "The standing bar for a Python repo linted with ruff and type-checked with ty and basedpyright: zero findings from all three, one lint command from the repo root, a change is not done until it passes, and the finding gets fixed rather than silenced. Includes each checker's own suppression spelling, since the one everybody types is mypy's and is inert under both."
---

## Python linting (load-bearing)

This repo is linted with **ruff** and type-checked with **ty** *and*
**basedpyright**. Keep all three clean — zero findings is the bar, and a change
isn't done until `{{ template.lint_command | default("make lint") }}` passes.

```bash
# all three, from the repo root — every package in one pass
{{ template.lint_command | default("make lint") }}
# apply the autofixable ruff findings (unused imports, etc.)
ruff check . --fix
```

Run it from the **repo root** before wrapping up any Python change, so every
package is covered in one pass. The test target runs it first, so a type error
fails the suite rather than waiting for a reviewer.

**Two type checkers is deliberate.** ty is fast and follows this repo's own
calls; basedpyright carries pyright's inference and its bundled third-party
stubs, so it sees through libraries ty treats as opaque. They disagree often
enough that each catches defects the other misses — neither one is the
redundant one, and a finding from either is a finding.

- **Fix the finding, don't silence it.** Prefer correcting the code over adding
  `# noqa` / `# ty: ignore` / `# pyright: ignore` or broadening an ignore. Reach
  for config only when a rule is genuinely wrong for this codebase, and say why.
- **The same bar applies to test files** — unused imports, ambiguous names
  (`l`/`I`/`O`), multi-statement semicolon lines, and a fake that has drifted
  from the port it stands in for are findings, not style preferences.
- **`# type: ignore[...]` is mypy's spelling and is inert for both.** ty reads
  `# ty: ignore[rule]`; basedpyright reads `# pyright: ignore[rule]`. Each names
  the rule, and each is ignored by the other checker — a suppression that
  silences one still has to answer to the other.
- **Run basedpyright with `-p <config>`.** Invoked without it, it does not read
  the `[tool.basedpyright]` table in `pyproject.toml`: it silently falls back to
  its own default mode over its own default tree, and reports a different set of
  findings than the gate does.
