# What belongs in the base library

Read [README.md](README.md) first — it says what this directory *is*. This file says
what may be **added** to it, because that is the decision that keeps getting made
wrongly, and it is invisible once it lands: a file that does not belong here still
renders, still installs, and still passes every check in the repo.

The base library is the **lowest-precedence layer of shared, overridable content for
the person and the agent working in a repo**. Everything here is fetched to
`~/.cache/stablemate` on machines that have none of this workspace, shadowed
name-for-name by a private overlay, and frozen for the life of a run. Those three
properties are the test.

## The rule

Content belongs here when **all** of these hold:

1. **More than one tool or repo is its audience.** A skill a coder turn loads in any
   repo, a slash command a person runs from anywhere, a pack that bundles them.
2. **A repo may legitimately want to override it.** The layering exists for content
   somebody else's house style should be able to replace. Content nobody may replace
   is not layered content — it is part of whatever ships it.
3. **It is inert data.** Markdown and YAML. No code, no dependency, nothing imported.
4. **It stands alone.** It renders and reads correctly on a machine that has only the
   cache — no path back into this workspace, and no private project's name in it (see
   the root `AGENTS.md`; `make check-public` is the gate).

## What does not belong

- **A prompt one package dispatches.** If exactly one program reads the text, the text
  is that program's data and ships in its wheel. Putting it here splits one release
  into two and makes the package's behaviour depend on an *optional* install: the
  library can be absent, stale, or shadowed by an overlay, and then the program runs
  with content it did not ship and cannot test against.
- **A workflow's own turn prompts.** `workhorse-workflows` is standalone by design —
  every envelope it renders is inside its wheel. The README's
  *Overriding a coder-workflow turn* section covers the one narrow exception, which is
  an override **slot** in an overlay, not a home for defaults.
- **Anything with a dependency, an import, or an `__init__.py`.** There is no build
  here and nothing to install.
- **A repo-specific rule.** This repo's own standards go in the root `AGENTS.md` or,
  when they must reach other repos, in a skill *plus* a `make check` that enforces
  them.

## The example this file was written for

`attend-gate.md` — the doctrine groom hands an attendant it spawns at a run that
parked or died — was added here and then moved out to `groom/groom/prompts/`. It
failed tests 1 and 2: groom is its only reader, and nothing else may override the rules
an unattended agent operates a live run under. Worse, it failed test 4 in a way that
was easy to miss — groom shipped from PyPI onto a machine with no library configured
would have dispatched an agent with the facts of a stopped run and none of the rules,
which is precisely the attendant that answers a gate to make a run move.

The prompt did not need to move because it was badly written. It moved because
*shipping with the thing that reads it* is what made it reliably present.

## Adding something

- A skill goes in `library/skills/<group>/<name>/SKILL.md`; a prompt in
  `library/prompts/<namespace>/<name>.md`; both are selected by a pack in
  `packs/<pack>.yml`, and a prompt that no pack lists is installed by nothing.
- Keep `packs/stablemate.yml`'s description in step with what it selects — it is the
  one place a reader sees the bundle as a whole.
- The layout contract itself (`library/skills/<group>/<name>/SKILL.md`,
  `packs/<pack>.yml`) is `farrier/docs/LAYOUT.md`. Changing it breaks the tools, not a
  version string here.
- Scope commits touching this directory `base-library`.
