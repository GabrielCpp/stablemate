# `ostler artifact` — schema-checked workflow artifacts (design)

Status: **implemented** (2026-07-03) — `ostler/artifact/` (kinds registry, scaffold, vet, CLI wiring, `tests/test_artifact_kinds.py`); consumer workflow gates union its problems in as a pre-check and the planner/QA prompts self-check with it. Registration via `.agents/templates.yml` (schema override/extension) remains future work; kinds are built-in for now. Motivated by two production incidents in the Predykt
`epic-coder` run of 2026-07-02/03, both the same failure class: *an agent wrote a JSON artifact
in an invented shape, and the deterministic consumer that reads it lived several pipeline stages
downstream.*

- `plan-context.json` written with `touched_layers: ["go"]` instead of `services: [...]` — the
  implementation dispatcher found zero services, silently skipped the entire implement stage, and
  an unimplemented story sailed through review into QA.
- `qa-evidence.json` written with `result`/`acceptance_criteria` instead of `overall`/`criteria`
  — the deterministic evidence gate failed the pass, burning the story's final QA rework on a
  key-renaming exercise.

Both artifacts had their schema defined only *implicitly* — inside the validator script that
eventually rejected them and inside prompt prose. The producer had nothing machine-readable to
conform to at write time. This is exactly the artifact-consistency problem ostler exists to solve
for the `docs/` knowledge hierarchy; this feature extends the same discipline to workflow
artifacts.

## Principles

1. **The contract is data, not prose.** Each artifact kind has a JSON Schema checked into the
   repository (`docs/artifact-schemas/<kind>.schema.json` by default). Prompts reference the
   schema file; validators load it; agents can read it. One source of truth kills drift between
   prompt prose, producer output, and consumer expectations.
2. **Validate at the producer.** The node that writes an artifact validates it in the same round
   (`ostler artifact vet`), so a schema error is fixed by the agent that made it — never
   discovered N stages later by a different loop with a different budget.
3. **Scaffold, don't dictate from memory.** `ostler artifact scaffold` writes the skeleton with
   the correct keys and empty/placeholder values; the agent fills values. Fill-in-the-blanks
   drifts far less than generate-from-memory.
4. **Empty is not absent.** A present-but-unusable artifact (exists, parses, but yields an empty
   work-list for its consumer) is a *validation error*, never a silent no-op. Consumers should
   never need defensive "is it secretly empty?" checks (the Predykt dispatcher now hard-fails on
   this; with producer-side validation that guard should never fire).

## CLI surface

```
ostler artifact scaffold <kind> --spec <spec-dir> [--force]
    Write <spec-dir>/<kind's filename> from the registered schema's skeleton
    (required keys present, enum placeholders, one empty exemplar per array).
    Refuses to overwrite unless --force.

ostler artifact vet <kind> --spec <spec-dir> [--json]
    Validate the artifact against its registered schema + kind-specific semantic
    rules (below). Exit 0 clean / 1 problems, mirroring `ostler vet`.
    Problems are actionable, one line each, naming the offending key/path.

ostler artifact list
    Show registered kinds, their schema paths, and target filenames.
```

Registration lives in `.agents/templates.yml` (the file ostler already owns for
template-declared kinds): each entry maps `kind → {filename, schema, rules}`.

## Initial kinds

| kind | filename | semantic rules beyond the JSON Schema |
|---|---|---|
| `plan-context` | `plan-context.json` | `services` non-empty; every `services[].repo` resolves in the workspace; every `services[].plan_file` exists in the spec dir; `implementation_order` entries all match a declared `repo::path`. |
| `qa-evidence` | `qa-evidence.json` | `criteria` non-empty; every criterion `verdict` ∈ {Pass, Fail}; every Pass criterion's `evidence[]` paths exist on disk; `kind: parity` requires a `checklist`; `kind: data-entry` requires a `persistence` proof; when `runId` present, `qa/run-manifest.json` must exist with the same id and every Pass criterion must cite ≥1 artifact from it. |
| `backlog-items` | `backlog-items.json` | array of `{id, description}`; ids kebab-case and unique. |

The `qa-evidence` semantic rules are a port of the Predykt workflow's
`verify_qa_evidence.py`; once `ostler artifact vet qa-evidence` exists, that script should
delegate to it (single implementation, gate and producer share it — the gate stops being the
only holder of the contract).

## Workflow integration (epic-coder)

- The planner prompt gains: "run `ostler artifact scaffold plan-context --spec <spec_dir>`
  before writing, and `ostler artifact vet plan-context --spec <spec_dir>` before returning —
  a vet failure is YOUR bug to fix in this round."
- The QA prompt gains the same pair for `qa-evidence`.
- `validate-plan-context.py` and `verify_qa_evidence.py` become thin wrappers over
  `ostler artifact vet` (keeping their workflow-output envelope), so the workflow gates and the
  producer self-checks can never disagree.

## Non-goals

- Not a general-purpose JSON Schema runner: kinds are registered, curated, and carry semantic
  rules that plain schema validation cannot express (path existence, workspace resolution,
  cross-file consistency).
- Not a replacement for the deterministic gates — gates stay; they just share the
  implementation with the producer-side check instead of being its only definition.
