# Contributing to stablemate

Thanks for looking. This file is the short version of the rules CI enforces, so you can
find out from a paragraph rather than from a red build.

Three of them are unusual enough to be worth reading before you write any code: commit
messages decide releases, workflows may not read the environment, and this repository is
public in a way that is actively checked. Each has its own section below.

## Setting up

```bash
git clone https://github.com/GabrielCpp/stablemate.git && cd stablemate
make install    # the workspace venv, the Chromium binary, and the git hooks
make test       # ~2 minutes; should be green before you change anything
```

`make install` rather than `make sync`, because git ships no hook configuration: a fresh
clone runs nothing, so the commit guards are silently off until something installs them
— and the commit that needed stopping is usually the first one. The wiring is farrier's:
`make hooks` runs `farrier hooks`, which reads `hooks: manager: githooks` from
`agents.yml`, splices its own fenced region into `.githooks/pre-commit` and points
`core.hooksPath` at that directory. The guards themselves are the standalone scripts
there, runnable by hand when you are working out why a commit was blocked.

`make help` lists every target. The ones you will use:

| Command | What it does |
| --- | --- |
| `make lint` | ruff + ty over the whole workspace. Zero findings is the bar. |
| `make test` | lint, then every package's suite, then the repo's guards. |
| `make -C <pkg> test` | one package (`core`, `workhorse`, `workflows`, `ostler`, `farrier`, `groom`, `saddlebag`). |

Run `make lint` from the **repo root**, not from a package: a member that lints itself
lints a different tree than CI does.

## Commit messages decide what ships

Releases are cut by [release-please](https://github.com/googleapis/release-please), which
reads commit subjects and **nothing else**. The type is therefore not a style preference —
it is the input that decides whether a package is released and at what version.

```
<type>(<scope>): <lowercase imperative description>

<optional body, wrapped at 72 columns, explaining why — not what>
```

| Type | Effect on the package named by the scope |
| --- | --- |
| `feat` | minor bump |
| `fix` / `perf` / `refactor` | patch bump |
| `<type>!` or a `BREAKING CHANGE:` body paragraph | major bump |
| `docs` `test` `build` `ci` `chore` | **no release at all** |

That last row is the one that bites. A repaired defect labelled `chore:` ships to nobody,
and the omission surfaces weeks later as a bug report against a version that never
contained the fix.

- Pick the type by what the change *is*, not how large it is: a rename, a move or an
  extraction is `refactor`, never `feat`.
- **scope** is one tracked top-level directory — `core`, `workhorse`, `workflows`,
  `farrier`, `ostler`, `groom`, `saddlebag`, `base-library`, `benchmarks`, `docs`,
  `scripts` — or one of `deps`, `release`, `ci`, `lint`, `hooks`. It names the *package*,
  not the module inside it: `fix(workhorse):`, not `fix(runner):`. Omit the parentheses
  for a repo-wide change.
- Subject ≤ 72 characters, no capital first word, no trailing period.
- **One concern per commit.** A commit spanning four unrelated changes cannot be labelled
  correctly by any single type, so whichever type you pick withholds a release from the
  other three. Split first, then label.

`.githooks/commit-msg` rejects a subject that violates any of the above, and CI runs that
same hook over every commit in your PR — so a message that passed locally passes there.
`git commit --no-verify` bypasses the hook but not CI.

## A workflow reads no environment

`os.environ` and `os.getenv` are **prohibited** anywhere under
`workflows/src/workhorse_workflows/`. Everything a node or a state needs is an argument or
a workflow parameter — a field on the `Workflow` subclass, settable with `--param`.

The reason is resume. A value read from the environment is in no checkpoint, so a run that
crashes on Tuesday and resumes on Wednesday silently takes a different one; it is also in
no telemetry, and `--params` cannot set it. The process boundary is where the environment
belongs, and it is outside that package: `workhorse/cli/run.py` and
`workhorse/supervisor.py` translate `$FOO` into `--params` once, on the way in.

```bash
make check-no-env    # runs as part of make test
```

`workflows/README.md` has the full rule, including `Workflow.injects` for the ambient
paths.

## This repository is public, and it is checked

stablemate ships publicly, and it is developed alongside a private overlay library. No
private project's name may appear here — not in prose, not in a fixture, not in a code
comment. Examples use neutral placeholders: `acme` / `globex` for a client repo,
`api-service` / `web-app` for repos in a workspace, `example.com` for a hostname.

The banned names are deliberately not written down anywhere in the tree — a denylist
publishes the words it bans. `scripts/private_names.py` reads them from an untracked
source instead, so **with no list configured this guard is a no-op** and you will never
see it. That is the expected experience for an outside contributor.

```bash
make check-public    # runs as part of make test
```

## Other guards

`make test` also runs these. Each exists because its failure mode is invisible on the
machine where the code was written:

| Guard | Rule |
| --- | --- |
| `make check-parsers` | a format with a grammar gets a parser, not a regex |
| `make check-portability` | a shipped package runs on the user's OS, not ours |
| `make check-vendor` | `core/` and its two vendored copies match byte for byte |
| `make check-library` | the base library's front matter parses |

`core/stablemate_core` is vendored into `workhorse/` and `farrier/` rather than depended
on. If you change it, run `make vendor` and commit the copies in the same commit — that is
also what makes release-please bump both tools, since it decides what to ship from the
paths a commit touched.

## Opening a pull request

- Branch from `main`. Keep the PR to one concern where you can.
- Make sure `make test` is green locally; CI runs the same command.
- Say *why* in the description. The what is in the diff.
- New behaviour wants a test. The bar for test code is the same as for shipped code —
  unused imports and a fake that has drifted from the port it stands in for are findings,
  not style preferences.

## Docs

Every subproject has a README; read it before changing that component. A workflow is
**Python**, not YAML — the YAML engine is retired, and there is no `workflow.yml`. If you
find prose describing one, it is stale and fixing it is welcome.

- [`workhorse/docs/AUTHORING.md`](workhorse/docs/AUTHORING.md) — writing a workflow
- [`workhorse/docs/WORKFLOW.md`](workhorse/docs/WORKFLOW.md) — the retired YAML schema
  mapped construct-by-construct to what replaces it
- [`docs/features/`](docs/features/) — the generated knowledge graph for the tools

## Reporting a vulnerability

See [SECURITY.md](SECURITY.md). Please do not open a public issue for one.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
