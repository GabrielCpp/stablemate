# The book's stack: `stack.yml`

A book that boots something says what it is made of in one file, `stack.yml`, beside its pages
at `docs/features/<book>/stack.yml`. A repo with one book keeps it at `docs/features/stack.yml`,
and the book takes the repo directory's name in lowercase. `ostler env` reads every book's file
together and runs the product on this machine from them, one compose project per copy. The file
replaces a hand-kept compose file, the make targets that start it and the proxy config beside
it. Those become templates the file names.

## What the file says

```yaml
secrets: web-local
default-fixtures: [schema]
services:
  web:
    about: the browser app, built from this checkout
    define: ops/services/web.yml.j2
    needs: [api:api, api:provision]
  gateway:
    define: ops/services/gateway.yml.j2
    render: [ops/services/Caddyfile.j2]
    needs: [web]
    address: gateway
    port: 80
    host-port: 8443
```

| key | where | what it says |
| --- | --- | --- |
| `services` | book | one entry per service this book defines, named in lowercase letters, digits and `-` |
| `secrets` | book | the saddlebag environment this book's services read `${VAR}` values from |
| `default-fixtures` | book | the fixture sets loaded when a bring-up names none |
| `about` | service | one line on what the service is |
| `define` | service | the template that renders to this service's compose block |
| `needs` | service | the services that must be up first. `name` is this book's, `book:name` another book's |
| `once` | service | `true` for a job that runs to completion, such as a migration. What needs it waits for it to exit 0 |
| `render` | service | helper templates rendered beside the copy, such as a proxy config the service mounts |
| `fixtures` | service | fixture sets by name, each a list of files the service loads |
| `address` | service | the name a run reads this service's URL by, the same name a runbook writes as `{gateway}` |
| `port` | service | the container port the address publishes. An address needs one |
| `host-port` | service | the host port the shared copy keeps. Every other copy takes a free one |
| `scheme` | service | the address's URL scheme, `http` unless stated |

Paths are read from the folder the file sits in.

## One service, one book

A service another book uses is defined once, in the book that owns it, and named in the other
book's `needs:`. The web book does not copy the api's database. It needs `api:db`, and a
bring-up of both books starts the database once. Two books defining the same template, or two
services publishing the same address, are refused.

## Templates

A `define` template renders to one compose service block. It sees these values:

| value | what it holds |
| --- | --- |
| `copy` | the copy's name: `shared`, or the run's lease |
| `project` | the compose project, `<repo>-<copy>` |
| `shared` | `true` for the shared copy |
| `repo` | the checkout root, for a build context or a bind mount |
| `book_dir` | the folder `stack.yml` sits in |
| `dir` | where this service's `render` files land in the copy |
| `fixtures` | the files of the chosen fixture sets this service declares, each with `path` and `name` |
| `service('book:name')` | another service's host name inside the copy |

```yaml
image: caddy:2
volumes:
  - {{ dir }}/Caddyfile:/etc/caddy/Caddyfile:ro
  - data:/data
environment:
  UPSTREAM: http://{{ service('web') }}:5173
  API_KEY: ${GATEWAY_API_KEY}
```

ostler writes `depends_on`, `ports` and `container_name` from the file, so a template that sets
one is refused. A named volume such as `data` above becomes the copy's own. A `${VAR}` value
comes from the book's `secrets:` environment, rendered for each copy and deleted when it goes
down. A secret value is never written into a template or a fixture.

A template names a host from `service(...)` and never as a literal, because each copy has its
own. A dependency with a `healthcheck` is waited for until healthy, so a service that clients
reach before it is ready declares one.

## Copies

Each run that holds a lease brings up its own copy, with its own volumes and ports. The shared
copy is the one a person runs by hand, and keeps each `host-port`.

```bash
timeout 60 ostler env check
timeout 900 ostler env up web --copy story-12
timeout 30 ostler env address gateway --copy story-12
timeout 120 ostler env down --copy story-12
```

A QA run needs none of these by hand. `ostler qa stack up --lease story-12` brings the book up
from its `stack.yml` as that copy, and the coder workflow does the same under the run's lease.
A call without a lease keeps the stack the book's runbook declares, and takes the shared copy
only where no runbook declares one.

## Doctor codes it can trip

`stack-invalid`, one finding per problem, on the file it was found in. See
[doctor-codes.md](doctor-codes.md).
