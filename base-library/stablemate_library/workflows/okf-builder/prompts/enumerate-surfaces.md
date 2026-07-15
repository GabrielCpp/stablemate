---
agent: agent
---

# okf-builder — enumerate the entry-point surfaces

Seed the crawl. Read the service's code and find **every entry-point surface** — the places a user
or caller enters the system. The crawl descends from these; miss one and a whole subtree is lost,
so be exhaustive about *surfaces* (their internals are discovered later, not now).

Load the method: {{ skill_load_ref("stablemate-okf-modeling", skill_dir() + "/stablemate-okf-modeling/SKILL.md") }}

**Guardrails (unattended):** read-only reconnaissance — do **not** write any docs, modify code, run
`git`, or run builds/tests this turn. Just identify surfaces and return them. Stay inside the
explicit source root below.

## Inputs

- service: `{{ workhorse_var('service') }}`
- features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`
- excluded source paths: `{{ workhorse_var('source_excludes') }}` — do not inspect or emit these

## Steps

1. Find entry points in the service's code:
   - **CLI** — an argparse/click/typer app, Go `cmd/**/main.go`, or equivalent command registry →
     one `cli` surface.
   - **HTTP/WS server** — a route table / `create_app`, Go router/server composition, OpenAPI
     operations, or router include → one `server` surface.
   - **GUI** — top-level rendered views/templates, React Router route modules, or TSX screen
     components → one `screen` per composed view.
   - **Library / API module** — a public importable module or package meant to be used by *other*
     code (a helper/SDK the CLI/GUI never reaches, e.g. a `scriptutil`), which the entry-point crawl
     would otherwise miss → emit it as a `concept` item so it's still documented and descended.
2. Find the **operational surface** — how the system is *run and observed*, not just what it does
   (the **OKF runbook profile** — the `runbook`/`environment`/`step` node types). Read the generic run evidence:
   `Makefile`/`justfile` targets, `docker-compose*`/`compose*` services, `package.json` scripts,
   `pyproject` console-scripts / `__main__` modules, `Dockerfile`/CI, the config loader's stages +
   env vars, and any README "how to run" section. From it emit:
   - **one `runbook` seed per driver** the repo exposes — `web` (a browser page), `mobile`, `http`
     (an API, no UI), `cli` (a bounded command), `artifact` (a batch job whose output is files),
     `iac` (a deploy definition, doc-only), or `none`. A repo with nothing to boot (a pure library
     or batch tool) still gets a runbook — an `artifact` or `none` one, not a `web` one.
   - **one `environment` seed per target** you can identify (`local`, `test`, `prod`; a purely
     local tool may have only `local`, or none).
   Do not resolve the steps/ports/health here — the investigator documents each to the bar.
4. Do **not** document their internals yet — just identify each surface and where its entry code
   lives. (The drain loop investigates each surface: enumerating its elements, then descending the
   code layer by layer.)
5. Emit one item per surface for a bounded set. If a GUI registry contains more than roughly 15
   screens, emit one `surface-slice` item per coherent route family instead, with an exhaustive
   list of the screen routes/modules in `context`. The investigator still writes one `screen` node
   per route; batching only avoids one model invocation per shallow registry entry.

## Output

```json
{"discovered": [
  {"kind": "surface", "target": "cli:workhorse", "context": "workhorse/workhorse/main.py::main"},
  {"kind": "surface", "target": "server:groom", "context": "groom/groom/app.py::create_app"},
  {"kind": "surface-slice", "target": "screens:projects", "context": "routes: /projects -> app/routes/projects.tsx; /projects/new -> app/routes/projects.new.tsx"},
  {"kind": "environment", "target": "environment:local", "context": "selector: GROOM_BIND=127.0.0.1; services: dashboard @ :8787"},
  {"kind": "runbook", "target": "runbook:web", "context": "driver: web; env: local; launch: `groom serve`; evidence: pyproject console-script `groom`, README run section"}
]}
```

`target` is `<type>:<name>` (or `screens:<family>` for a large GUI batch); `context` points at the
entry symbol, carries the complete bounded route/module list, or (for `runbook`/`environment`) the
driver + launch evidence the investigator will resolve. Empty list only if the service truly has no
surfaces and nothing to run.
