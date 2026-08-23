---
name: python-lint-clean
description: "The standing bar for a Python repo linted with ruff and type-checked with ty: zero findings from both, one lint command from the repo root, a change is not done until it passes, and the finding gets fixed rather than silenced. Includes the one spelling that actually suppresses under ty, since mypy's is inert and looks like it worked."
---

## Python linting (load-bearing)

This repo is linted with **ruff** *and* type-checked with **ty**. Keep both
clean — zero findings is the bar, and a change isn't done until
`{{ template.lint_command | default("make lint") }}` passes.

```bash
# both, from the repo root — every package in one pass
{{ template.lint_command | default("make lint") }}
# apply the autofixable ruff findings (unused imports, etc.)
ruff check . --fix
```

Run it from the **repo root** before wrapping up any Python change, so every
package is covered in one pass. The test target runs it first, so a type error
fails the suite rather than waiting for a reviewer.

- **Fix the finding, don't silence it.** Prefer correcting the code over adding
  `# noqa` / `# ty: ignore` or broadening an ignore. Reach for config only when a
  rule is genuinely wrong for this codebase, and say why.
- **The same bar applies to test files** — unused imports, ambiguous names
  (`l`/`I`/`O`), multi-statement semicolon lines, and a fake that has drifted
  from the port it stands in for are findings, not style preferences.
- **`# type: ignore[...]` is mypy's spelling and is inert for ty.** The one that
  suppresses is `# ty: ignore[rule]`, and it names the rule.
