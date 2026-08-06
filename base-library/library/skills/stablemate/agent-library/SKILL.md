---
name: agent-library
description: "Agent Library Maintenance & Install. Applies to agents.yml,.agents/**,agents/library/**,agents/packs/**,agents/scaffolds/**."
applyTo: 'agents.yml,.agents/**,agents/library/**,agents/packs/**,agents/scaffolds/**'
tags: [codegen]
---

# Agent Library Maintenance & Install

Use this skill when changing the shared agent library (skills, prompts, packs,
scaffolds) **and** when propagating those changes into a consuming repository
with `make agent-install`.

The library's filesystem location is never hardcoded — resolve it with
`farrier config show library_dir` (or `farrier config show` for all keys).
Do not assume it lives at a particular path like `example-org/agents`; that
is just one possible checkout, and treating it as fixed will conflate a
specific machine's layout with the library itself.

The agent library is the single source of truth. The per-repo `.codex/`,
`.claude/`, `.github/instructions/`, `.github/skills/`, `.github/prompts/`,
`.agents/workflows/`, and local `AGENTS.md`/`CLAUDE.md` files are **generated
outputs** — never hand-edit them. Change the library, then re-install.

## Library layout

```
<library_dir>/               # the prompt-library CONTENT — path from `farrier config show library_dir`
  library/
    skills/<group>/<name>.md   # skill files (YAML frontmatter + markdown)
    prompts/<group>/*.md       # prompt files
    roots/                     # root instruction files (CLAUDE.md / AGENTS.md)
  packs/<pack>.yml      # named bundles of skills + prompts a repo opts into
  scaffolds/*.yml       # scaffold definitions applied via `farrier scaffold <id>`
```

The renderer that turns this content into a repo's adapters is **`farrier`**, a
separate published package (in the public `stablemate` repo) — it is not part of
this content tree. Install it with `pipx install farrier` and point it at this
library once with `farrier config set-library /path/to/agent-library`. Run
`farrier config show` any time to confirm the currently configured `library_dir`.

## Editing the library

Follow the reuse-before-create policy in `library/skills/CLAUDE.md` and
`library/skills/README.md` — check for a generic skill before writing a new one,
and add only project-specific deltas to project groups (never duplicate a generic
skill's rules).

1. **Edit a skill** — change the file under `skills/<group>/<name>.md`. Keep the
   `applyTo` frontmatter accurate; it controls which file globs load the skill.
2. **Add a skill** — create `skills/<group>/<name>.md`, then reference it from a
   pack under `skills:` as `<group>/<name>` (no `.md` extension).
3. **Edit a prompt** — change `prompts/<group>/<name>.md`; packs reference these
   under `prompts:` (globs like `review/*` are allowed).
4. **Wire it into a pack** — a skill or prompt is only installed if a pack the
   repo selects in `agents.yml` includes it. Packs compose via `includes:`.

Cross-link sibling skills with the `{% raw %}{{ instruction_file("<name>") }}{% endraw %}`
template helper (where `<name>` is the target skill's base name) rather than
duplicating content.

## Tagging a skill so a workflow can find it

A workflow prompt cannot name your skills. It ships in the public `stablemate`
repo and has never met your stack, so a prompt that asks for `go-testing` by name
is a prompt that renders a dead filename in every repo that writes its tests some
other way. Prompts therefore ask by **capability**:

```
{% raw %}{{ find_by_tags("web", "tests") }}{% endraw %}    → "however this repo writes web tests"
```

The query is an AND — a skill matches only if it carries *every* tag asked for —
and it renders the matching skills' installed paths, or nothing at all when the
repo has none. **Nothing at all is the default for an untagged library**: a skill
with no `tags:` can never be the answer to a query, so a per-stack skill that
isn't tagged is invisible to every workflow that would have used it.

Declare tags in the skill's frontmatter, as a list or a comma-separated string
(case and surrounding space don't matter — they are normalized):

```yaml
---
name: react-router-testing
description: "..."
applyTo: "web/**"
tags: [web, tests, qa]
---
```

The vocabulary the workflows query — use these spellings, since a tag no prompt
asks for is a tag nothing will ever read. The `coder` workflow asks for the
mechanics of writing and verifying code:

| Tag | The skill answers |
| --- | --- |
| `runbook` | how to bring this repo's local stack up and work in it day to day |
| `standards` | how code in that layer is written — the conventions a change must follow |
| `tests` | how that layer's tests are written and run |
| `qa` | how to bring the **real** stack up and drive it for verification |
| `codegen` | which artifacts are generated, and the command that regenerates them |

The `author` workflow asks a different question — not how code is written but how
work and its record are *shaped* — so it queries two more:

| Tag | The skill answers |
| --- | --- |
| `planning` | how this repo decomposes work into epics, stories and seeds — the method, and the sizing and sequencing rules |
| `docs` | how a written artifact is structured — the epic/story grammar, the docs graph, the prose entry surface |

These two are deliberately narrower than `standards`. Nearly ninety library
skills answer "how code is written", so a prompt that needs the story grammar and
asks `find_by_tags("standards")` gets the whole library back and has selected
nothing. A kind tag earns its place by *excluding* — if adding one to a skill does
not shrink some query's answer, it is decoration.

Combine one of those with the layer the skill belongs to: `backend`, `cli`,
`web`, `mobile`, or `infra`. A skill covering more than one job carries more than
one tag — `tags: [web, standards, runbook]` answers all three of those queries.

Then add the **stack** the mechanics are specific to — `go`, `python`,
`flutter`, `react-router`, `pulumi`, and so on. The layer says *which ring of the
system*, the stack says *which technology*, and they are not the same question: a
repo with two backends has two `backend` skill sets, and only the stack tag tells
them apart. A skill that says "here is how this layer is written" without naming
the technology is a skill a query cannot narrow.

The stack list is open — it is whatever a library actually holds, so name the
stack as the ecosystem calls itself and reuse the spelling already in the library
rather than coining a synonym. Skills that are genuinely technology-neutral (the
ports-and-adapters contract, the accessibility contract, the story-doc layout)
carry no stack tag at all, which is what keeps them answering every query.

```yaml
tags: [go, backend, standards]        # how Go code in the API ring is written
tags: [flutter, mobile, tests]        # how the Flutter app's tests are written
tags: [standards]                     # language-neutral: applies to every stack
```

One more tag exists for a different reader:

| Tag | The skill answers |
| --- | --- |
| `entrypoint` | where to *start* in that layer — the root skill that fans out to its own testing/QA/codegen siblings |

`entrypoint` is not part of the coder vocabulary; the querier is a repo-root
instruction (the one `localInstructions` renders into `CLAUDE.md`). That file is
in context for every single turn, so a root that lists every skill in the layer
spends the context it was meant to save. `find_by_tags("backend", "entrypoint")`
returns the one skill to open first and lets it do the fanning out. Exactly one
skill per layer should carry it.

Tags land in the generated skill's `metadata:` block and in the context manifest,
so `make agent-install` is what makes a new tag visible to a workflow.

A tag is only as good as the frontmatter around it. `tags:` must sit on its own
line inside the `---` fences; a block that loses its closing newline parses as no
front matter at all, which silently strips *every* tag on that skill rather than
erroring. After a bulk retag, check that each source still opens with a
well-formed `---` … `---` block before trusting a query that comes back empty.

## Installing into the working repo

After any library change, regenerate the adapters in **every consuming repo** that
selects the affected pack. From the consuming repo root:

```bash
# Regenerate adapters from the library (writes .claude/, .codex/, .agents/, etc.)
timeout 300 make agent-install

# Verify adapters are current without writing (use in CI / pre-commit)
timeout 120 make agent-check
```

`make agent-install` runs `farrier --repo "$(CURDIR)"`. `AGENTS_DIR` defaults to
`$(shell farrier config show library_dir)` — the location recorded once via
`farrier config set-library` — so the generated Makefile never hardcodes a
path either. If the library lives somewhere else for this invocation, override
the dir explicitly:

```bash
timeout 300 make agent-install AGENTS_DIR=/path/to/agent-library
```

You can also invoke the installer directly, using whatever `farrier config show
library_dir` reports (or an explicit override):

```bash
timeout 300 farrier --repo /path/to/repo --library "$(farrier config show library_dir)"
timeout 120 farrier --repo /path/to/repo --check --library "$(farrier config show library_dir)"
```

## Verification before calling the work done

1. `make agent-check` passes in the consuming repo (no drift).
2. The new/changed skill or prompt appears in the generated `.claude/` (and any
   other enabled adapter) output.
3. `agents.yml` `packs:` actually selects the pack that carries the change —
   otherwise the install is a no-op for that repo.
4. Commit the regenerated adapter files alongside the library change.

Every command above is bounded by a wall-clock `timeout`, per
`{{ instruction_file("infra-cli-writer") }}`.

