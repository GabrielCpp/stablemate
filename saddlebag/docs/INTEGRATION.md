# Integration: ostler stacks and workhorse workflows

Saddlebag is a CLI, and that is the whole of its coupling to the rest of the stablemate
tooling. Nothing imports it. Ostler shells out to it to bring a stack up, and a
workhorse workflow shells out to it from a blueprint node. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
covers install and the commands used below.

## The ostler stack

A repository's `docs/services/ops/stack.yml` names one secret source. With saddlebag:

```yaml
secrets:
  saddlebag: environment=local
```

Ostler runs `saddlebag list --tag environment=local --json` and takes each secret's
`var` as a variable the stack may reference. It compares that set against the `${VAR}`
references in the rendered compose file before anything starts, so a missing secret
fails `ostler env check` with the variable's name rather than failing a container at
boot. Then every `docker compose` command for that copy runs as
`saddlebag exec --tag environment=local -- docker compose ...`, and compose reads the
values from its own process environment. No `stack.env` is written.

The tag value is the `slug:` of the ostler `environment` page the runbook links to, the
same slug `ostler env exec` resolves a held `NAME: secret` variable by. A secret created
for that environment carries the same tag:

```bash
saddlebag secret create api_db --var POSTGRES_PASSWORD --tag environment=local \
  --description "The local stack's database password"
printf '%s' "$PASSWORD" | saddlebag secret set api_db
```

## Workhorse integration

A workflow node that needs a secret in a command's environment wraps the command in
`exec`. Nothing about the node changes otherwise, and no secret enters the node's
return value, its checkpoint or its telemetry.

```python
import logging

from pydantic import BaseModel
from workhorse.pyflow import Blueprint
from workhorse_workflows.kit import run_tool

blueprint = Blueprint("checkout-qa")


class Seeded(BaseModel):
    environment: str


@blueprint.node
def seed_database(logger: logging.Logger, environment: str) -> Seeded:
    """Run the seed script with the environment's secrets in its process environment."""
    run_tool(
        ["saddlebag", "exec", "--tag", f"environment={environment}", "--", "make", "seed"],
        check=True,
        logger=logger,
    )
    return Seeded(environment=environment)
```

`run_tool` is the seam. It logs the invocation, which carries the command line and no
value, and `check=True` fails the node rather than letting a silent non-zero exit
hand the next state a half-seeded stack.

## Signing in from an agent turn

An agent driving a browser does not receive a password. It lists the candidates for
the environment it is testing, reads their descriptions, and fills the one it chose:

```bash
saddlebag list --tag environment=staging --tag role=admin
saddlebag fill admin_login --field username --selector "#login_field" --url-contains example.com
saddlebag fill admin_login --field password --selector "#password"    --url-contains example.com
saddlebag fill admin_login --field totp     --selector "#app_totp"    --url-contains example.com
```

The browser must be one started with a debugger port, and the agent's own browser
tooling must share it. A Playwright launch with `--remote-debugging-port` or a connect
over CDP to the same endpoint both work. The daemon on the host is what reaches the
port, so a run in a container needs only the socket mounted.
