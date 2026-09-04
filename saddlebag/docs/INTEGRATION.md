# Integration — workhorse workflows and ostler seeds

Saddlebag is a CLI, and that is the whole of its coupling to the rest of the stablemate
tooling: nothing imports it. A workhorse workflow shells out to it from a blueprint node,
and ostler supplies the *requirements* a scan is run with. This file shows both ends.

The [README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
covers install and the shortest path through it; the commands used below are documented in
[docs/CREDENTIALS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/CREDENTIALS.md)
and
[docs/ENVIRONMENTS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/ENVIRONMENTS.md).

## Workhorse integration

A workhorse workflow is a Python state machine. Credentials flow through it as ordinary
blueprint nodes that bookend the agent work — acquire before the turn, release after it:

```python
import json
import logging

from pydantic import BaseModel
from workhorse.pyflow import Blueprint, Continue, Done, Workflow
from workhorse_workflows.kit import run_tool

blueprint = Blueprint("checkout-qa")


class LeasedCredential(BaseModel):
    """What the workflow carries between states.

    Deliberately **no `password` field** — and saddlebag could not supply one if the
    workflow asked: no verb emits a stored secret. The lease JSON is the identity and
    the lease, which is exactly what is safe to checkpoint to a node's `output.json`.
    The secret itself only ever leaves the store through `env render`, into the
    environment's own `0600` target file.
    """

    id: str
    username: str
    lease_id: str


@blueprint.node
def acquire_credential(
    logger: logging.Logger,
    env: str,
    roles: str,
    surface: str,
    run_id: str,
    select_via: str,
) -> LeasedCredential:
    """Scan the pool, let the agent CLI pick a match, and lease it for this run."""
    result = run_tool(
        [
            "saddlebag", "scan",
            "--env", env,
            "--roles", *roles.split(),
            "--surface", surface,
            "--select-via", select_via,
            "--run-id", run_id,
            "--json",
        ],
        check=True,
        logger=logger,
    )
    record = json.loads(result.stdout)
    return LeasedCredential(
        id=record["id"], username=record["username"], lease_id=record["lease_id"]
    )


@blueprint.node
def release_credentials(logger: logging.Logger, run_id: str) -> Released:
    """Give back every credential this run holds. Idempotent, so it cannot fail a run."""
    run_tool(["saddlebag", "release", "--run-id", run_id], check=True, logger=logger)
    return Released(run_id=run_id)


class CheckoutQA(Workflow):
    env: str
    surface: str
    #: Which agent CLI `scan --select-via` should ask to choose. A workflow input, not
    #: something the engine hands you.
    select_via: str = "claude"

    def start(self) -> Continue:
        cred = self.call(
            acquire_credential,
            self.env,
            "admin billing",
            self.surface,
            self.run_id,
            self.select_via,
        )
        return Continue(cred, self.run_test, username=cred.username)

    def run_test(self, username: str) -> Continue:
        result = self.agent(
            "prompts/test-login.md",
            returns=TestResult,
            args={"username": username},
        )
        return Continue(result, self.release, ok=result.ok)

    def release(self, ok: bool) -> Done:
        self.call(release_credentials, self.run_id)
        return Done(ok)
```

`Released`, `TestResult` and `EnvRendered` are the workflow's own pydantic schemas, elided
here — every node and every agent turn returns a typed model. Two things carry the design:

**`run_tool` is the seam.** Nodes route every external CLI call through
`workhorse_workflows.kit.run_tool`, so the invocation is logged and `check=True` fails the
node rather than letting a silent non-zero exit hand the workflow an empty lease.

**Release by `--run-id`, not `--lease-id`.** One release node then cleans up every
credential the run holds, including any acquired in parallel branches:

```python
    def start(self) -> Continue:
        staging = self.call(
            acquire_credential, "staging", "admin", self.surface, self.run_id,
            self.select_via,
        )
        self.call(
            acquire_credential, "prod", "admin", self.surface, self.run_id,
            self.select_via,
        )
        return Continue(staging, self.run_test, username=staging.username)
```

Both leases carry the same `--run-id`, so the single `release` state at the end gives back
both. Nothing has to track lease ids by hand.

### Bringing the stack up

An environment renders through the same shape, and needs no new release node — the
existing one already covers any `credential-ref` leases that `render` took out:

```python
@blueprint.node
def ensure_env(logger: logging.Logger, env_name: str, run_id: str) -> EnvRendered:
    """Materialize the stack's environment file from the pool."""
    run_tool(
        ["saddlebag", "env", "render", env_name, "--run-id", run_id],
        check=True,
        logger=logger,
    )
    return EnvRendered(name=env_name)
```

This is what lets an environment fixer stop touching `.env` files at all. The stack's
environment material is owned by saddlebag, not by files in the repo: an agent runs
`env render` to materialize it, and never reads, writes, or invents the contents of a
`.env`. If render reports pending required keys, that is a human-only wall — the agent
reports it and names the exact keys, rather than guessing a value and producing a silently
wrong stack. Once that sanctioned path exists, a permission layer can deny agent reads of
`.env*` outright.

## The `.workhorse/` contract

`saddlebag.workhorse` is the one Python module a workflow may import:

| Name | What it is |
|---|---|
| `WORKHORSE_DIR` | `".workhorse"` — where run-scoped artifacts go |
| `write_private` | the `0600`-before-content write for any run-scoped secret file |

There is deliberately no credential file and no read helper: saddlebag never hands a
stored secret to a caller, so there is nothing to read back. Everything else is the CLI.
