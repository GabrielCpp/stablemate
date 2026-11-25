---
name: farrier-agent-library
description: "Agent library plumbing: library layout, packs, agents.yml selection and reinstalling generated skills. Load when adding or moving a skill, prompt or pack, editing agents.yml, or when a generated copy drifts."
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

The agent library is the single source of truth. The per-repo `.agents/`,
`.claude/`, `.github/instructions/`, `.github/skills/`, `.github/prompts/`,
and local `AGENTS.md`/`CLAUDE.md` files are **generated outputs**. Never
hand-edit them. Change the library, then re-install. `.codex/` is a home
output, written by `farrier install --user`.

## Library layout

```
<library_dir>/               # the prompt-library CONTENT — path from `farrier config show library_dir`
  library/
    skills/<group>/<name>.md   # skill files (YAML frontmatter + markdown)
    prompts/<group>/*.md       # prompt files
    policies/<group>/<name>/   # POLICY.md plus scripts/, aggregated into AGENTS.md
    hooks/<name>/              # home guards farrier installs into each harness home
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

Follow the reuse-before-create policy in `library/skills/AGENTS.md` and
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

Cross-link sibling skills with the `{% raw %}{{ skill_link("<name>") }}{% endraw %}`
template helper rather than duplicating content. `<name>` is the target skill's
folder name, which is unique across the library. The link reads the installed
name and points at the installed path, in this repo or in the home folder.

## Tagging a skill so a workflow can find it

A workflow prompt cannot name your skills. It ships in the public `stablemate`
repo and has never met your stack, so a prompt that asks for `go-testing` by name
is a prompt that renders a dead filename in every repo that writes its tests some
other way. Prompts therefore ask by **capability**:

```
{% raw %}{{ find_by_tags("web", "tests") }}{% endraw %}    → "however this repo writes web tests"
```

The query is an AND — a skill matches only if it carries *every* tag asked for —
and it renders a link to each matching skill, or nothing at all when the
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

## Git hooks and commit checks: who pays for the check

A skill or a policy can attach a script to a commit in two ways. The choice decides
who waits for it.

| | `hooks:` (git hook) | `commit_checks:` (agent commit check) |
| --- | --- | --- |
| Runs on | every commit, human or agent | an agent's `git commit` only |
| Fires from | git, through the repo's hook manager | the `commit-checks` home guard, before the shell runs |
| Entry keys | `stage` (`pre-commit` or `commit-msg`) and `run` | `run` and `budget` |
| Listed by | `farrier hooks list` | `farrier checks --repo <repo>` |
| Wired by | `farrier install` or `farrier hooks install` in the repo | `hooks = ["commit-checks"]` in each harness profile of the home config |
| Bypassed by | `--no-verify` | a harness without the guard |

Pick `hooks:` when the rule must hold whoever commits. The commit-message format is
the example: release-please reads every subject, so a human's bad subject breaks a
release as surely as an agent's. Pick `commit_checks:` for everything an agent's
commit needs and a human's does not, such as lint, type checks or the private-names
scan. A git hook pays its cost on every human commit. Before the split, a human waited
about seventeen seconds on checks only an agent's commit needed.

The two keys are separate on purpose. A marker under `hooks:` was rejected, because
that key names a git-hook stage.

### Declaring a git hook

```yaml
hooks:
  - stage: commit-msg
    run: scripts/check_commit_message.py
```

- `stage` is `pre-commit` or `commit-msg`. Install skips any other stage without a
  word. `farrier library check` reports it, and the same check catches a missing
  `run:` file or a malformed `commit_checks:` entry.
- `run` is a path inside the source's own folder. A `.py` script runs through
  `python3`. Any other script must be executable.
- A `commit-msg` script gets the message file path as its first argument.

`farrier install` writes one runner per stage, `.agents/hooks/pre-commit` and
`.agents/hooks/commit-msg`, from the `hooks:` of every selected skill and every
policy a `localInstructions` mapping names. It then splices one fenced entry into
the repo's hook manager. `hooks.manager` in `agents.yml` names it: `pre-commit`,
`lefthook`, `husky`, `githooks` or `none`. Without that key, farrier picks the
manager from the repo's marker files and falls back to `githooks`, which sets
`core.hooksPath`. The pre-commit entry calls `make farrier-run-hook`. Farrier owns
only the fenced region, so the repo's own hooks around it survive a reinstall.
`none` strips the fence and leaves the runners unwired.

### Declaring a commit check

A skill or a policy declares its checks in front matter:

```yaml
commit_checks:
  - run: scripts/check_staged_files.py
    budget: 2
```

- `run` is a path under the source's own `scripts/` folder. A `.py` script runs
  through `python3`. Any other script must be executable.
- `budget` is the check's usual cost in seconds. The guard adds it to the agent's
  command timeout.

A check honours one contract:

1. It runs from the repository root and reads the index, never the working tree.
2. It takes the commit's pathspecs as arguments when the commit names paths, and
   checks only those.
3. It exits 0 to pass. Any other exit stops the commit, and stderr tells the agent
   what to fix.
4. It may read `AGENT_COMMIT_COMMAND`, the agent's whole command, and
   `AGENT_COMMIT_CWD`, the directory the agent ran it from. The private-names check
   reads the commit message from them.

`farrier checks --repo <repo>` prints one `command<TAB>budget` line per check. The
first line is `farrier sync`, which reinstalls drifted agent files and stages them
when `agents.yml` exists. The `commit-checks` home guard reads that listing and
rewrites the agent's `git commit` command so the checks run first. In Codex and in
Claude's auto mode, a rewrite needs an approval the harness review never gave. There
the guard approves a plain commit itself: `cd`, `git add`, `git commit`, `git log` and
`git status` joined by `&&`, with no environment prefix, no git option but `-C`, no
`--output`, no command substitution beyond a quoted heredoc message, and no redirect
but to `/dev/null`. Any other commit
comes back refused, with the rewritten command for the agent to run. Enable it by
naming `commit-checks` in the `hooks` list of each harness profile in the farrier
config.

Three things in farrier carry the word "hooks". The `hooks:` front-matter key is a
git-hook stage. `library/hooks/<name>/` is a home guard, a harness hook such as
`commit-checks` itself. `hooks.manager` in `agents.yml` names the git hook manager.

A home guard's `command` may carry a `{harness}` placeholder. Farrier replaces it
with the harness it installs into, so one guard can answer each harness in its own
dialect.

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

Every command above is bounded by a wall-clock `timeout`.
