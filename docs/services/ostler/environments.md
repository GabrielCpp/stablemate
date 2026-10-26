---
type: cli
slug: environments
title: ostler env
---
# ostler env

`ostler env` turns the books' `ops/stack.yml` declarations into a running docker compose project.
`render` and the render step of `up` write the compose file and reject a template that references
a secret no source supplies, without ever starting docker.

- binary: ostler
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

## Commands

### ostler-env-render
- usage: ostler env render [TARGET...] [--copy NAME] [--fixtures SET[,SET]] [--json] — writes the
  copy's `compose.yml` and a `copy.json` manifest from the targeted books' services, without
  starting docker, and prints `rendered <copy> into <directory>` (or the whole outcome as one
  JSON object with --json)
- flags:
  - --copy (which named copy to render into; default: `$STABLEMATE_LEASE_HOLDER`, else `shared`),
    --fixtures (the fixture sets to load; default: each targeted book's default-fixtures),
    --json (print `{ok, copy, project, directory, services, fixtures, files}` as one indented
    JSON object)
- args: target — a book name, or one `book:service`; defaults to every book under the repo when
  omitted
- exits: 0 — a targeted book whose services' templates render to a compose block with none of the
  keys ostler itself writes always renders and writes
- run: invoke(argv=["env", "render", "env-render-fixture", "--copy", "okf-book-env-render-probe", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="copy", equals="okf-book-env-render-probe")
- verify: json_path(path="services[0]", equals="env-render-fixture:demo")
- verify: json_path(path="files[0]", matches="(?s)^.*compose\\.yml$")
- fixture: [environments render and secrets](fixtures/environments-render-and-secrets.md) — seeds
  env-render-fixture, one service whose template references no secret
- code: ostler/ostler/environments/render.py::render@c93ab3c3f7b3
- code: ostler/ostler/environments/render.py::write@c93ab3c3f7b3
- code: ostler/ostler/environments/runtime.py::copy_for@c45517030b87
- code: ostler/ostler/environments/runtime.py::write_manifest@c45517030b87
- code: ostler/ostler/environments/commands.py::cmd_render@36bbc1003620
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-check-required-name
- usage: ostler env check [--json] — beyond `ostler env check`'s book-shape checks (see
  [ostler env check](cli.md#ostler-env-check)), rejects a rendered template that references a
  `${NAME}` the stack root's secret source, or an upstream job's `outputs:`, does not supply
- exits: 1 — a service's template referencing a `${NAME}` neither source defines is reported by
  name and by the service that needs it, before docker ever runs
- run: invoke(argv=["env", "check", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="errors[0]", matches="^a `\\$\\{NAME\\}` the templates require is in no secret source: `OKF_BOOK_PROBE_SECRET` is required by env-secrets-fixture:worker$")
- fixture: [environments render and secrets](fixtures/environments-render-and-secrets.md) — seeds
  env-secrets-fixture, whose `worker` service's template references `${OKF_BOOK_PROBE_SECRET}`,
  and no stack root declares a `secrets:` source to supply it
- code: ostler/ostler/environments/secrets.py::source_for@761a72c7a6dd
- code: ostler/ostler/environments/secrets.py::missing_names@761a72c7a6dd
- code: ostler/ostler/environments/secrets.py::required_names@761a72c7a6dd
- code: ostler/ostler/environments/secrets.py::allowed_names@761a72c7a6dd
- code: ostler/ostler/environments/commands.py::cmd_check@05411233ab32
- code: ostler/ostler/environments/spec.py::load@ece1017c2482
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-address-not-up
- usage: ostler env address NAME [--copy NAME] [--json] — prints the URL the copy publishes
  NAME at, read from the `addresses.json` a bring-up wrote into the copy's directory, without
  starting docker; fails a name no bring-up has published yet, naming every address the copy
  does publish instead
- flags:
  - --copy (which named copy to read from; default: `$STABLEMATE_LEASE_HOLDER`, else `shared`), --json (print `{ok, name, url}` as one indented JSON object)
- args: name — the address name to resolve
- exits: 1 — a copy nothing has brought up yet publishes no address book; the name is rejected,
  and the message says the copy is not up rather than naming an address it never had
- run: invoke(argv=["env", "address", "demo", "--copy", "okf-book-env-address-never-up", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="error", matches="^okf-book-env-address-never-up publishes no `demo` \\(it publishes none, since it is not up\\)$")
- fixture: none, because nothing is seeded
- code: ostler/ostler/qa/addresses.py::read_book@910467430420
- code: ostler/ostler/environments/commands.py::cmd_address@05411233ab32
- code: ostler/ostler/environments/runtime.py::copy_for@c45517030b87
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)
