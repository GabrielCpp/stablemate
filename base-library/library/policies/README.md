# Policies

A **policy** is library text that reaches a repository only by being aggregated into a
generated `AGENTS.md`, through a `localInstructions` mapping in that repo's `agents.yml`.
It is never installed as a skill, never gets a slash command, is never an
`instruction_file()` target, and never answers a tag query. It bundles no assets.

## Why the kind exists

A skill folded into an always-loaded `AGENTS.md` is charged twice: its whole body is
resident in every turn's context, *and* its `name` and `description` sit in the skill
index the agent carries every turn — advertising, as something to load on demand, text
already above it in the window. Thirty skills is roughly 15 KB of index. A policy pays
the body once and nothing else.

## The bar

Write a policy when **all** of these hold:

- The text must be in context **every turn**, not loaded when a task matches. If an agent
  can do useful work in this repo without it, it is a skill.
- Nothing would ever **invoke** it by name. A policy cannot be loaded on demand, linked
  to, or found by a tag query — if any of those is how you expect it to be reached, it is
  a skill.

Most policies are **rules** — the standing constraints the procedures run under. A
*procedure* can be one too, but only once the second bullet holds of it: a procedure
that is resident every turn is never reached by name, and keeping it a `/`-command as
well leaves a second copy of text that was never off-screen. `commit-and-push` is the
worked example — every change ends there, every repo that had it aggregated it, and the
command it used to be went unused. A procedure only *some* turns need is still a prompt.

Everything else stays a skill or a prompt. A policy that a second repo wants is fine —
it is library text like any other; layer shadowing and namespacing work the same way.

## Layout

```
library/policies/<group>/<name>.md
```

Flat files under a group, like prompts. Front matter carries `name` and `description`
for humans and for farrier's error messages; both are stripped before aggregation, so
neither is emitted anywhere. No `applyTo` and no `tags` — a policy is not auto-loaded by
glob and is not discoverable by query. The body renders through Jinja2 like any other
library source.

A policy that a second repo would want takes its repo-specific values from
`{{ template.<key> | default("…") }}` and the consumer's `agents.yml` `template:` block,
so the text stays installable in a repo that sets none of them. Groups sort the tree by
concern, not by consumer: `git/`, `python/`, `repo/` hold text no repo is named in,
`stablemate/` holds the ones that only make sense here.

Referenced by **bare basename** (`stablemate-repo`), with no repo prefix ever added:
there is no installed artifact for a prefix to disambiguate. The namespaced form
(`<group>/<name>`) resolves too, and a basename ambiguous across two groups is an error.

See [`farrier/docs/LAYOUT.md`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/docs/LAYOUT.md)
for the full kind reference.
