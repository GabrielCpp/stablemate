# The book's stack: `stack.yml`

A book that boots something says what it is made of in one file, `stack.yml`, in the `ops/`
folder beside its pages, at `docs/services/<book>/ops/stack.yml`. The file at
`docs/services/ops/stack.yml` is the stack root. It is also a book, and takes the repo
directory's name in lowercase. A file at an old place, `docs/services/<book>/stack.yml` or
`docs/services/stack.yml`, is an error that names where to move it.

`ostler env` reads every book's file together and runs the product on this machine from them,
one compose project per copy. The file replaces a hand-kept compose file, the make targets that
start it and the proxy config beside it. Those become templates the file names.

## What the file says

```yaml
default-fixtures: [schema]
services:
  web:
    about: the browser app, built from this checkout
    define: services/web.yml.j2
    needs: [api:api, api:provision]
  gateway:
    about: the proxy a browser opens
    define: services/gateway.yml.j2
    files:
      Caddyfile: services/Caddyfile.j2
    needs: [web]
    address: gateway
    port: 80
    host-port: 8443
```

| key | where | what it says |
| --- | --- | --- |
| `services` | book | one entry per service this book defines, named in lowercase letters, digits and `-` |
| `secrets` | root | the one source of `${VAR}` values: `file:` a dotenv file, `decrypt:` a command whose stdout is dotenv, or `saddlebag:` the `key=value` tags that select secrets in saddlebag. Valid only in the stack root |
| `needs` | book | the books whose every service this book's services need. They come up first, and a cycle across books is refused |
| `default-fixtures` | book | the fixture sets loaded when a bring-up names none |
| `about` | service | one line on what the service is, required. `ostler env ls` shows it |
| `define` | service | the template that renders to this service's compose block |
| `needs` | service | the services that must be up first. `name` is this book's, `book:name` another book's |
| `once` | service | `true` for a job that runs to completion, such as a migration. What needs it waits for it to exit 0 |
| `outputs` | service | for a `once` job, the environment names it writes to `$STABLEMATE_OUTPUTS`. The services that need the job read them as `${NAME}` |
| `files` | service | files placed in the service's folder of the copy, target to source. A `.j2` source is rendered, any other file is copied byte for byte, a folder is walked |
| `fixtures` | service | fixture sets by name, each a list of files the service loads. A fixture file must exist only when its set is loaded, so a set no bring-up names may point at a file this checkout lacks, such as a database dump kept out of git. In a git worktree, a fixture file absent there is read from the main checkout |
| `address` | service | the name a run reads this service's URL by, the same name a runbook writes as `{gateway}` |
| `port` | service | the container port the address publishes. An address needs one |
| `host-port` | service | the host port the shared copy keeps. Every other copy takes a free one |
| `scheme` | service | the address's URL scheme, `http` unless stated |

Paths are read from the folder the file sits in, which is `ops/`. `ostler env schema` prints a
JSON Schema for the file, for an editor to validate it with. It comes from the same key table as
the rows above.

## What `ops/` is for

A book's `ops/` folder holds everything it takes to run the book on a machine: `stack.yml`, the
templates and plain files it places, and the `environment` and `runbook` pages that describe it.
Nothing in `ops/` is product. The stack root, `docs/services/ops/stack.yml`, is the file of a
one-book repo as well.

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
| `ops_dir` | the `ops/` folder `stack.yml` sits in |
| `dir` | this service's folder in the copy, where its `files` land |
| `env_dir` | the copy's folder |
| `fixtures` | the files of the chosen fixture sets this service declares, each with `path` and `name` |
| `fixture_sets` | the names of the fixture sets the bring-up loads, in order, whether or not this service declares them |
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
comes from the stack root's one secret source. A secret value is never written into a template or a fixture.

A template names a host from `service(...)` and never as a literal, because each copy has its
own. A dependency with a `healthcheck` is waited for until healthy, so a service that clients
reach before it is ready declares one.

## Files

`files:` maps a target to a source. The target is a path inside the service's folder of the copy,
so an absolute target or one with `..` is an error. The source is read from `ops/` and must exist.

- A source ending in `.j2` is rendered with Jinja and written under the target name as given.
- Any other file is copied byte for byte, so an executable bit survives and a literal `{{ }}`
  stays as it is.
- A source folder is walked. Each file lands at `target/<relative path>`. A `.j2` file in it is
  rendered and loses its `.j2` suffix, and every other file is copied.

A service builds from the checkout with its Dockerfile in the copy. A `Dockerfile.dockerignore`
beside the Dockerfile applies to the build:

```yaml
build:
  context: {{ repo }}
  dockerfile: {{ dir }}/Dockerfile
```

```yaml
files:
  Dockerfile: images/web.Dockerfile.j2
  Dockerfile.dockerignore: images/web.dockerignore
```

## Secrets

One repo has one secret source, named in the stack root, `docs/services/ops/stack.yml`. A
`secrets:` key in any other book's file is an error.

```yaml
secrets:
  file: .env
```

```yaml
secrets:
  decrypt: sops --decrypt docs/services/ops/secrets.enc.env
```

```yaml
secrets:
  saddlebag: environment=local
```

- `file:` is a dotenv file, read from the repo root. Compose reads it in place, so ostler makes
  no copy of it. In a git worktree, a file absent there is read from the main checkout.
- `decrypt:` is a shell command, run with `sh -c` from the repo root. Its stdout is dotenv. ostler
  runs it once per `up` and writes the output to `secrets/stack.env` in the copy, mode `0600`.
  A failure is reported by exit code and the last five lines of stderr. The output is never
  printed or logged. `down` deletes the file.
- `saddlebag:` is one or more `key=value` tags separated by spaces. ostler asks
  `saddlebag list --tag <k=v> --json` for the matching secrets and takes each one's `var` as a
  name the source defines. Every `docker compose` command for the copy then runs under
  `saddlebag exec --tag <k=v> --`, so compose reads the values from its own process environment
  and no secrets file is written. A matching secret with no `var` fails `check` and `up` by name.

The copy's manifest records the env files and the `saddlebag exec` prefix `up` used, so
`ostler env compose` runs the same way.

Every `$NAME`, `${NAME}` and `${NAME:?msg}` a rendered template uses must be a name the source defines, or a job it needs writes.
`$NAME` without braces is checked too. `${NAME:-default}` has a default and is not checked, nor
are the other default and alternative forms, `${NAME-x}`, `${NAME:+x}` and `${NAME+x}`. `$$` is
an escape, so `$$NAME` and `$${NAME}` are literal text. `ostler env up` fails
before docker runs, and `ostler env check` fails too, each naming the missing name and its
service. Neither prints a value. The check reads names only, so a `KEY=value` line gives it `KEY`.

## Job outputs

A `once` job that declares `outputs:` hands values to the services that need it. A job is a
container the template defines, so ostler adds no tool-specific key or code. Pulumi and Terraform
are two examples of what such a job runs.

```yaml
services:
  infra:
    about: creates the upload bucket
    once: true
    outputs: [UPLOAD_BUCKET]
    define: services/infra.yml.j2
  api:
    about: the HTTP API, built from this checkout
    needs: [infra]
    define: services/api.yml.j2
```

```yaml
image: example.com/infra-tool:1
command: ["sh", "-c", "create-bucket && echo UPLOAD_BUCKET=$(bucket-name) >> $STABLEMATE_OUTPUTS"]
```

ostler mounts a folder of the copy into the job and sets `STABLEMATE_OUTPUTS` to the path of the
file the job writes `KEY=value` lines to, one line per name. A template that sets the variable
itself is an error. The job must write every name it declares, or `up` fails and names the job
and each name it left out. A service reads a name as `${NAME}`, and the name check allows the
outputs of every job in its needs, so `api` above may use `${UPLOAD_BUCKET}`.

An `up` that holds such a job runs compose twice on one project. The first run brings up only
the job and what it needs, and waits for it to exit 0. ostler reads its file and writes the
values to `secrets/outputs.env` in the copy, mode `0600`, then deletes the raw file. The second
run brings up the whole copy with that file as an env file. The services that need the job stay
down until the second run. Compose starts the job a second time in that run, so a job with
outputs must be safe to run twice, as every `once` job already must be. An `up` with no job
outputs runs compose once.

## Copies

Each run that holds a lease brings up its own copy, with its own volumes and ports. The shared
copy is the one a person runs by hand, and keeps each `host-port`.

```bash
timeout 60 ostler env check
timeout 900 ostler env up web --copy story-12
timeout 30 ostler env address gateway --copy story-12
timeout 30 ostler env ls
timeout 120 ostler env down --copy story-12
```

`ostler env ls` prints each book's services, one line each: the reference, its `about`, the
address and host port it publishes, and the copies that run it. A copy docker does not report as
running shows its status in parentheses. It exits 1 when the stack files have errors, after it
lists the services that did load. `--json` keeps the `copies` rows and adds a `services` list.

A QA run needs none of these by hand. `ostler qa stack up --lease story-12` brings the book up
from its `stack.yml` as that copy, and the coder workflow does the same under the run's lease.
A call without a lease keeps the stack the book's runbook declares, and takes the shared copy
only where no runbook declares one.

Each bring-up of a copy that is already up does the same work:

- It holds what this `up` names and what that needs. A service an earlier `up` started and
  this one leaves out is removed. From the repo root, `up` with no target names every book,
  so `timeout 900 ostler env up --copy "$STABLEMATE_LEASE"` rebuilds the whole run's copy.
- It rebuilds every built image from the checkout, through Docker's build cache, so an edit
  reaches the copy on the next `up`. A service whose image or block changed is recreated.
- It starts every `once` job again, so a job such as a migration or a seed is idempotent.
- It keeps the copy's volumes. `ostler env up --fresh` drops them first, so the fixtures load
  again.

`ostler env down` and `ostler qa stack down --lease` drop the copy's volumes with it.
`ostler env down --keep-data` keeps them for the next `up`.

A fixture or a step that runs a command inside a service reaches it through `ostler env
compose`. The copy defaults to `$STABLEMATE_LEASE`, so the same line serves every run. Compose
names each service `<book>-<service>`:

```bash
timeout 60 ostler env compose -- exec -T api-db mysql -e 'select 1'
timeout 30 ostler env compose -- ps --format '{{.Service}} {{.Name}}'
```

A container's name is `<repo>-<copy>-<book>-<service>-1`. It starts with the checkout's
directory name, so a `docker ps` filter on the lease alone finds it only unanchored.

A run killed before its teardown does not leave its copy up for good. The next leased bring-up
on the machine tears down every copy whose run is gone, and says which. A copy brought up by
hand, outside any run, has no holder and stays until `ostler env down` removes it.

## Runbook prepare steps

This file describes `stack.yml`. A runbook page declares its own stack, and its `kind: prepare`
steps run on the host, each through `bash -c`, in document order and before the service starts.
A step that does not return within 600 seconds is killed and fails the bring-up. A step raises
its own ceiling with a `timeout:` bullet, in seconds. A stack the run adopts, because it already
serves, skips the prepare steps and the launch, and still runs the seed and health steps. The
mobile example in
[the runbook reference](../../ostler-okf/references/node-types/runbook.md) boots an emulator
and installs the app in prepare steps.

## Doctor codes it can trip

`stack-invalid`, one finding per problem, on the file it was found in. See
[doctor-codes.md](doctor-codes.md).
