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

## License

MIT — see [LICENSE](LICENSE).
