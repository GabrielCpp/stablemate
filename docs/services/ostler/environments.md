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
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
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
- code: ostler/ostler/environments/runtime.py::copy_for@bf9459423d5a
- code: ostler/ostler/environments/runtime.py::write_manifest@bf9459423d5a
- code: ostler/ostler/environments/commands.py::cmd_render@5b8dac7706e8
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-render-fixture-missing
- usage: ostler env render [TARGET...] [--copy NAME] --fixtures SET[,SET] [--json] — a named
  fixture set naming a file that nothing ever creates is reported by the service and the set
  that need it, before docker ever runs
- exits: 1 — a `--fixtures` set naming a file that nothing ever creates is reported by the
  service and the set that need it, before docker ever runs
- run: invoke(argv=["env", "render", "env-render-fixture", "--copy", "okf-book-env-render-probe", "--fixtures", "okf-book-probe-missing", "--json"])
- verify: exit_status(code=1)
- verify: json_path(path="ok", equals=false)
- verify: json_path(path="error", matches="^env-render-fixture:demo fixture set `okf-book-probe-missing` names .*/docs/services/env-render-fixture/ops/absent\\.env, which does not exist$")
- fixture: [environments render and secrets](fixtures/environments-render-and-secrets.md) — seeds
  env-render-fixture's demo service with a `okf-book-probe-missing` fixture set naming a file
  no step ever creates
- code: ostler/ostler/environments/checkout.py::locate@abb56c78967b
- code: ostler/ostler/environments/render.py::render@c93ab3c3f7b3
- code: ostler/ostler/environments/commands.py::cmd_render@5b8dac7706e8
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
- code: ostler/ostler/environments/commands.py::cmd_check@5b8dac7706e8
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
- code: ostler/ostler/environments/commands.py::cmd_address@5b8dac7706e8
- code: ostler/ostler/environments/runtime.py::copy_for@bf9459423d5a
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-exec
- usage: ostler env exec ENVIRONMENT [--] COMMAND... — replaces itself with COMMAND, run under the
  `variables:` of the `environment` page ENVIRONMENT names: each `NAME: value` literal is laid over
  the process environment, and each `NAME: secret` mark wraps COMMAND in
  `saddlebag exec --env NAME=<record>` for the one saddlebag record tagged `environment=<slug>`
  whose `var` is NAME, so the value reaches COMMAND and never ostler. Every held mark is resolved
  before anything runs: a mark with no record, or with two, is named together with the
  `saddlebag secret create <name> --var NAME --tag environment=<slug>` line that registers one,
  and COMMAND does not start. A page that marks no variable `secret` runs COMMAND directly,
  asking saddlebag nothing. No command after ENVIRONMENT prints
  `usage: ostler env exec ENVIRONMENT [--] COMMAND...` on stderr and exits 2; an ENVIRONMENT that
  names no `environment` page, a malformed variable or an unbound mark exits 1 with the name in
  the message; otherwise the exit code is COMMAND's own, since the process is COMMAND by then
- args: environment — an `environment` page, by slug or id; command — what to run, after an
  optional `--`
- exits: 0 — a command run under a page of literals sees each literal as an environment variable
- run: invoke(argv=["env", "exec", "okf-book-env-vars-probe", "--", "printenv", "OKF_BOOK_PROBE_LEVEL"])
- verify: exit_status(code=0)
- verify: stdout(text="debug")
- fixture: [environments variables page](fixtures/environments-variables-page.md)
- code: ostler/ostler/environments/commands.py::cmd_exec@5b8dac7706e8
- code: ostler/ostler/environments/inject.py::resolve@f3a3093eb2a9
- code: ostler/ostler/environments/inject.py::exec_argv@f3a3093eb2a9
- code: ostler/ostler/environments/inject.py::composed_environment@f3a3093eb2a9
- code: ostler/ostler/environments/page.py::find_environment@22a09f593926
- code: ostler/ostler/environments/page.py::read_variables@22a09f593926
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-dotenv
- usage: ostler env dotenv ENVIRONMENT [--to PATH] — writes the `variables:` of the `environment`
  page ENVIRONMENT names as a dotenv file: a first line
  `# rendered by ostler env dotenv from <id>; edit the page, not this file`, then one `NAME=value`
  per entry in page order, `NAME=` for a held mark, so no secret value is ever written; prints
  `wrote <path> (<n> variables, <h> held)`. A file inside the repo whose repo-relative path no
  `.gitignore` line names yet gets one, and `added <path> to .gitignore` is printed; a file
  outside the repo leaves `.gitignore` alone, with a note on stderr. An ENVIRONMENT that names no
  `environment` page, or a malformed variable, exits 1 with the page or the variable in the
  message, and no file is written
- flags:
  - --to (the file to write, relative to the repo root unless absolute; default: `.env`)
- args: environment — an `environment` page, by slug or id
- exits: 0 — a page of literals renders to a file with one line per variable and no blank name
- run: invoke(argv=["env", "dotenv", "okf-book-env-vars-probe", "--to", "docs/services/env-vars-fixture/ops/probe.env"])
- verify: exit_status(code=0)
- verify: stdout(matches="^wrote .*probe\\.env \\(2 variables, 0 held\\)$")
- verify: contents(subject="docs/services/env-vars-fixture/ops/probe.env", text="OKF_BOOK_PROBE_LEVEL=debug")
- verify: contents(subject="docs/services/env-vars-fixture/ops/probe.env", text="OKF_BOOK_PROBE_PORT=8080")
- fixture: [environments variables page](fixtures/environments-variables-page.md)
- code: ostler/ostler/environments/commands.py::cmd_dotenv@5b8dac7706e8
- code: ostler/ostler/environments/inject.py::render_dotenv@f3a3093eb2a9
- code: ostler/ostler/environments/inject.py::ensure_ignored@f3a3093eb2a9
- code: ostler/ostler/environments/page.py::read_variables@22a09f593926
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)

### ostler-env-import-dotenv-unknown-environment
- usage: ostler env import-dotenv FILE --environment ENVIRONMENT — moves the dotenv FILE onto the
  `environment` page ENVIRONMENT names: `saddlebag env classify` says which lines are secret, the
  page's `variables:` gain each file key in file order (a secret one as `NAME: secret`, an entry of
  the same name replaced in place), the diff is printed and written, and the secret keys no record
  with that `var` and `environment=<slug>` tag holds yet go to
  `saddlebag env import FILE --keys ... --tag environment=<slug> --prefix <slug>-`; prints
  `<n> lines: <h> held, <l> literal`, `<k> already held` when any were, saddlebag's
  `stored KEY as NAME` lines, and a `next:` line naming the page to commit. Before any write it
  refuses a key the page cannot hold as a variable name, a key saddlebag reads that ostler does
  not, and a literal whose value is the word `secret`. A saddlebag failure after the page was
  written is reported as such, naming the keys the page now marks held and the
  `saddlebag secret create` line that finishes their registration
- flags:
  - --environment (the `environment` page to move the file onto, by slug or id; required)
- args: file — the dotenv file to move
- exits: 1 — a `--environment` that names no `environment` page is rejected by name before FILE
  is opened, so the file need not exist for the refusal
- run: invoke(argv=["env", "import-dotenv", "docs/services/env-vars-fixture/ops/absent.env", "--environment", "okf-book-no-such-environment"])
- verify: exit_status(code=1)
- verify: stderr(text="no environment page is named `okf-book-no-such-environment`")
- code: ostler/ostler/environments/migrate.py::cmd_import_dotenv@b0a1040701b6
- code: ostler/ostler/environments/migrate.py::rewrite_variables@b0a1040701b6
- code: ostler/ostler/environments/inject.py::classify_file@f3a3093eb2a9
- code: ostler/ostler/environments/page.py::find_environment@22a09f593926
- code: ostler/ostler/environments/cli.py::run@b521bae7b440
- detail: [Local stack bring-up](concepts/local-stack-bring-up.md)
