<!--
Thanks for the PR. The checklist below is what CI checks anyway — it is here so a red
build is not the first time you hear about it. CONTRIBUTING.md has the reasoning.
-->

## What and why

<!-- The diff says what changed. Use this space for why. -->

## Type of change

<!--
The commit subject is what release-please reads, and it decides whether a package ships
at all — `chore:` on a repaired defect releases to nobody. Check the row that matches
your commits.
-->

- [ ] `feat` — new behaviour (minor bump)
- [ ] `fix` / `perf` / `refactor` — patch bump
- [ ] `docs` / `test` / `build` / `ci` / `chore` — **no release**
- [ ] Breaking (`!` in the subject, or a `BREAKING CHANGE:` body paragraph)

## Checklist

- [ ] `make test` is green from the repo root (this runs `make lint` first)
- [ ] Commit subjects are Conventional Commits, one concern per commit
- [ ] New behaviour has a test
- [ ] Touched `core/`? Ran `make vendor` and committed the copies in the same commit
- [ ] Touched `workflows/`? No `os.environ` / `os.getenv` — inputs are parameters
- [ ] Prose that describes a retired YAML workflow engine was fixed, not left alone
