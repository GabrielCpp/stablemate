---
type: concept
slug: local-stack-bring-up
title: Local stack bring-up
---
# Local stack bring-up

`ostler env schema` and `ostler env check` read a book's `ops/stack.yml` without touching
docker. `up`, `down`, `ls`, `render`, `address` and `compose` turn that declaration into a running
docker compose project on the caller's machine: one directory per named copy, rendered from the
services a target needs, brought up, and torn down again. `exec`, `dotenv` and `import-dotenv`
read an `environment` page instead of a stack file: the page's `variables:` are the variables a
command outside compose runs with, and the page is where a repo's dotenv moves to.

- code: ostler/ostler/environments/__init__.py@cbf4cafcdc33
- code: ostler/ostler/environments/cli.py::add_parser@03ca0f5405c9
- code: ostler/ostler/environments/cli.py::run@a2cdf551584c
- code: ostler/ostler/environments/leases.py::books_near@f3dc55131ce7
- code: ostler/ostler/environments/leases.py::up@c9e11fad8ccb
- code: ostler/ostler/environments/leases.py::down@bba92dc8fb8f
- code: ostler/ostler/environments/leases.py::run_env@50c6a3f3ff03
- code: ostler/ostler/environments/render.py::render@2b996371a211
- code: ostler/ostler/environments/render.py::write@b18b23b7045b
- code: ostler/ostler/environments/render.py::_mount_outputs@9abcec004bd8
- code: ostler/ostler/environments/runtime.py::copy_for@02834c13f824
- code: ostler/ostler/environments/runtime.py::Compose@fc97524c55b6
- code: ostler/ostler/environments/runtime.py::holder_alive@b5f32816eaf6
- code: ostler/ostler/environments/runtime.py::hold@a118625f33a8
- code: ostler/ostler/environments/runtime.py::remove@4e1b0c3a3b98
- code: ostler/ostler/environments/runtime.py::remove_secrets@4fb61acec73f
- code: ostler/ostler/environments/secrets.py::source_for@d9bf1e14c9f0
- code: ostler/ostler/environments/secrets.py::missing_names@aa2bc1fcdc10
- code: ostler/ostler/environments/secrets.py::allowed_names@55906ca4c382
- code: ostler/ostler/environments/secrets.py::write_private@24a534b2ab0e
- code: ostler/ostler/environments/page.py::read_variables@45bf345aacfd
- code: ostler/ostler/environments/page.py::find_environment@229ec14aa7ec
- code: ostler/ostler/environments/inject.py::resolve@60e36bd81dc8
- code: ostler/ostler/environments/inject.py::render_dotenv@f70ec1d4cde1
- code: ostler/ostler/environments/migrate.py::cmd_import_dotenv@fa0e40c97f3f
- detail: [ostler](../cli.md)

## Contract

- copy: a named instance of a repo's stack, identified by `--copy NAME` (default: `$STABLEMATE_LEASE_HOLDER`'s
  lease env var, else `shared`); its directory lives under the platform user-state dir (or
  `$OSTLER_ENV_HOME`), one subdirectory per `<repo-name>-<copy-name>` project.
- render: `ostler env render` and the render step of `up` write one `compose.yml` per copy from
  each needed service's Jinja-templated `define` file, plus the static and templated files the
  service lists under `files:`; a rendered block may not set `depends_on`, `ports` or
  `container_name` directly, since ostler derives those from the stack's `needs:`, `address:` and
  `port:` declarations.
- outputs mount: a service that declares `outputs:` gets a bind mount into
  `<copy>/outputs/<service>` and a `$STABLEMATE_OUTPUTS` variable pointing at its env file inside
  that mount; a service that already sets that variable, or a `volumes:`/`environment:` of a type
  ostler cannot extend, fails the render instead of silently overwriting what the block set.
- secrets: a stack root names at most one secret source — a dotenv file, a decrypt command, or a
  saddlebag tag query — and `ostler env up`/`render` reject a rendered block that references a
  variable neither that source nor an upstream service's `outputs:` supplies, before docker ever
  runs.
- variables: an `environment` page's `variables:` children are `NAME: value` literals and
  `NAME: secret` marks; a mark names a value saddlebag holds in the record tagged
  `environment=<page slug>` whose `var` is NAME, and no secret value is ever written on the page.
  `ostler env exec <page> -- CMD` is the one injector: it lays the literals over the process
  environment and wraps CMD in `saddlebag exec --env` for the marks, and fails by name before
  running anything when a mark has no record or two. `ostler env dotenv` renders the page as a
  gitignored file with the marks blank, for a tool that wants one, and `ostler env import-dotenv`
  moves a dotenv the other way: literals onto the page, secret lines into saddlebag through
  `saddlebag env import`, with the page written before saddlebag is asked and never a prompt.
- holder: a copy brought up with a lease records the holding process's pid and start time; a
  `down` or a later `up` treats a copy as free once that process is gone, so a crashed holder
  cannot keep a lease forever, but a live process with the same reused pid is not mistaken for
  the original holder.
- rule: a run that resumes after its process died names itself the holder of the copies it still
  plays against, so the next `up` of any other copy on the machine does not reclaim them
  mid-play. Naming a copy that does not exist changes nothing.
- rule: only the copy a lease names records the lease's holder. A command run under a lease
  that brings up another named copy, such as `--copy prod`, leaves that copy without a holder, so
  the next lease does not reclaim it and drop its data when the run that started it restarts.
- teardown: `ostler env down` always removes the copy's rendered secrets; it also drops the
  copy's data volumes unless `--keep-data` is given, and only ever deletes a directory that sits
  under the shared copies-home, never an arbitrary path.

## See also

- [ostler env schema](../cli.md#ostler-env-schema) and [ostler env check](../cli.md#ostler-env-check)
  read `ops/stack.yml` without bringing anything up.
