# stablemate

A [uv](https://docs.astral.sh/uv/) workspace housing the publishable Python
packages that work alongside an agent prompt library:

| Package | PyPI | Role |
| --- | --- | --- |
| [`workhorse/`](workhorse/) | [`workhorse-agent`](https://pypi.org/project/workhorse-agent/) | Fail-soft runner that drives the Claude CLI through a YAML workflow graph, unattended for days. |
| [`farrier/`](farrier/) | [`farrier`](https://pypi.org/project/farrier/) | Renders an agent-neutral prompt library into a repository's Codex/Claude/Copilot adapters and launcher. |

The prompt-library **content** (skills, prompts, scaffolds, workflows) lives in a
separate repository. `farrier` ships no content; it is pointed at the library via:

```bash
farrier config set-library /path/to/the/library
```

## Development

```bash
make sync                            # create the workspace venv (all members)
make build                           # build wheels + sdists for both packages
make test                            # run both test suites
make -C farrier check                # inspect a built wheel's contents
```

`make sync` runs `uv sync --all-packages` so both members are installed. (Plain
`uv sync` targets the workspace root, which is an intentionally non-packaged
anchor — it has a `[project]` table but no `[build-system]`, so uv never builds
or installs the root itself.) Use `uv run --package <name>` to run within a
specific member.

Each package is independently versioned and published (`make -C <pkg> publish`).
See each package's README for details.

## Releasing

Each package is released independently, with its next version inferred from the
[Conventional-Commit](https://www.conventionalcommits.org) history since its last
release tag (`<dist-name>-v<version>`, e.g. `farrier-v1.3.0`). Only commits that
touch the package's own directory count, so the two packages bump separately.

| Commit since last tag | Bump |
| --- | --- |
| `feat!:` / `fix(x)!:` / `BREAKING CHANGE:` in body | major |
| `feat:` | minor |
| anything else (`fix:`, `perf:`, `docs:`, …, or none) | patch |

```bash
make next-version                    # show what each package WOULD bump to
make release DRY_RUN=1               # preview the full release for both packages
make release                         # release both: bump, build, publish, commit, tag, push
make -C farrier release              # release just one package
```

`make release` stamps the new version into `pyproject.toml`, builds, publishes to
PyPI, then commits, creates the annotated tag, and pushes. The PyPI upload happens
before anything is committed or pushed: if publish fails, nothing is committed,
tagged, or pushed — just revert the local version stamp with
`git checkout -- <pkg>/pyproject.toml` and retry.

Knobs (set as `make` variables or environment variables):

| Knob | Effect |
| --- | --- |
| `DRY_RUN=1` | Print every step; change nothing. |
| `LEVEL=major\|minor\|patch` | Force the bump level instead of inferring it. |
| `RELEASE_VERSION=x.y.z` | Use an exact version (skips inference). |
| `PUBLISH=testpypi` | Publish to TestPyPI (or use `make release-test`). |
| `ALLOW_DIRTY=1` | Skip the clean-working-tree guard. |
| `NO_PUSH=1` | Commit + tag locally, but do not push. |
| `ZEROVER=1` | Pre-1.0 demotion (breaking → minor, feat → patch) while on 0.x. |

To review before committing, use `make bump` (or `make -C <pkg> bump`), which only
stamps the inferred version into `pyproject.toml` — you then commit, tag, and
publish by hand.

## License

MIT — see [LICENSE](LICENSE).
