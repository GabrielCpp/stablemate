---
type: concept
slug: local-stack-bring-up
title: Local stack bring-up
---
# Local stack bring-up

`ostler env schema` and `ostler env check` read a book's `ops/stack.yml` without touching
docker. The rest of `ostler env` — `up`, `down`, `ls`, `render`, `address` and `compose` — turns
that declaration into a running docker compose project on the caller's machine: one directory per
named copy, rendered from the services a target needs, brought up, and torn down again.

- code: ostler/ostler/environments/__init__.py@cbf4cafcdc33
- code: ostler/ostler/environments/cli.py::add_parser@f1b74cc1cc17
- code: ostler/ostler/environments/cli.py::run@f1b74cc1cc17
- code: ostler/ostler/environments/leases.py::books_near@479047ef621a
- code: ostler/ostler/environments/leases.py::up@479047ef621a
- code: ostler/ostler/environments/leases.py::down@479047ef621a
- code: ostler/ostler/environments/leases.py::run_env@479047ef621a
- code: ostler/ostler/environments/render.py::render@468c61e21fca
- code: ostler/ostler/environments/render.py::write@468c61e21fca
- code: ostler/ostler/environments/render.py::_mount_outputs@468c61e21fca
- code: ostler/ostler/environments/runtime.py::copy_for@9c6cee57be4b
- code: ostler/ostler/environments/runtime.py::Compose@9c6cee57be4b
- code: ostler/ostler/environments/runtime.py::holder_alive@9c6cee57be4b
- code: ostler/ostler/environments/runtime.py::remove@9c6cee57be4b
- code: ostler/ostler/environments/runtime.py::remove_secrets@9c6cee57be4b
- code: ostler/ostler/environments/secrets.py::source_for@0b9d51f963bf
- code: ostler/ostler/environments/secrets.py::missing_names@0b9d51f963bf
- code: ostler/ostler/environments/secrets.py::allowed_names@0b9d51f963bf
- code: ostler/ostler/environments/secrets.py::write_private@0b9d51f963bf
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
- holder: a copy brought up with a lease records the holding process's pid and start time; a
  `down` or a later `up` treats a copy as free once that process is gone, so a crashed holder
  cannot keep a lease forever, but a live process with the same reused pid is not mistaken for
  the original holder.
- teardown: `ostler env down` always removes the copy's rendered secrets; it also drops the
  copy's data volumes unless `--keep-data` is given, and only ever deletes a directory that sits
  under the shared copies-home, never an arbitrary path.

## See also

- [ostler env schema](../cli.md#ostler-env-schema) and [ostler env check](../cli.md#ostler-env-check)
  read `ops/stack.yml` without bringing anything up.
