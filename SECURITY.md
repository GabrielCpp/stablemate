# Security policy

## Reporting a vulnerability

Please report security issues **privately**, through GitHub's
[private vulnerability reporting](https://github.com/GabrielCpp/stablemate/security/advisories/new)
on this repository. Do not open a public issue.

Include what you can: the affected package and version, what an attacker gains, and the
smallest reproduction you have. You will get an acknowledgement within a week. This is a
small project maintained in spare time, so please treat that as a best effort rather than
an SLA.

## Supported versions

Fixes land on `main` and ship in the next release of the affected package. There are no
maintained back-ports; the latest release of each distribution is the supported one.

| Package | Index |
| --- | --- |
| `workhorse-agent` | [PyPI](https://pypi.org/project/workhorse-agent/) |
| `workhorse-workflows` | [PyPI](https://pypi.org/project/workhorse-workflows/) |
| `farrier` | [PyPI](https://pypi.org/project/farrier/) |
| `ostler` | [PyPI](https://pypi.org/project/ostler/) |

## What this project does, in security terms

Worth knowing before you assess it, because two of these surprise people:

**It runs an agent CLI, and that agent runs commands.** workhorse drives `claude`, `codex`,
`copilot`, `cline` or `opencode` as a subprocess against a repository you point it at,
unattended, for as long as the workflow takes. The agent's own permissions are the
boundary — workhorse does not sandbox it, and a workflow that reaches an operator gate is
waiting for a human, not for a policy engine. Run it against code and credentials you are
willing to have an agent touch.

**Prompts are rendered from a library on disk.** farrier renders markdown and YAML from a
base library (and an optional overlay you configure) into a repository's agent adapters.
That content becomes instructions to an agent. Treat a library you did not write the way
you would treat any other code you are about to execute.

**The base-library cache fetches over the network.** `farrier install` populates
`~/.cache/stablemate/library` by sparse-cloning `base-library/` from this repository. What
lands is markdown and YAML — no `.py` anywhere — so code still reaches you only as a wheel
from a package index, under whatever supply-chain posture you already apply to `pip` or
`uv`. `STABLEMATE_FETCH_BASE=0` forbids the fetch entirely for air-gapped hosts.

**Credentials.** `saddlebag` holds the credentials and environment manifests a workflow
needs at run time, deliberately outside the repository. `kit/credentials.py` is the one
module in the workflows package allowed to read the environment, precisely so a secret
never becomes a checkpointed `--param` written into a run artifact.

## Releases

Packages are published from `.github/workflows/release.yml` under
[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/). There is no
long-lived PyPI token in this repository, in CI, or on a maintainer's machine; GitHub
mints a short-lived OIDC token that PyPI verifies against a publisher pinned to this
repository, that workflow filename, and the `pypi` environment. Nothing is published from
a laptop.
