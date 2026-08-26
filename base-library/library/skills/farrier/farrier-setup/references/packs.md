# The pack catalog

What each pack name in `agents.yml → packs:` selects. The pack files themselves
(`packs/*.yml` in each library layer) carry a `description:` field, and that is
the source of truth — this table is the index, and a pack whose description has
moved on is right and this file is wrong.

## The two the base library ships

Every repo selects both. They are the floor, not a menu — the craft contracts
and the toolchain that reads them:

| Pack | Contents |
|------|----------|
| `general` | the cross-cutting craft every repo owes, whatever it is written in — architecture (ports-and-adapters, code structure), testing, ui/accessibility, vertical slicing, bug diagnosis, code review — plus the `grill`, `brainstorm` and `implement-plan-*` prompts |
| `stablemate` | the toolchain — farrier (install/setup, library maintenance), ostler (the doc-graph CLI, the OKF format, repo docs), groom (operator gate + telemetry), workhorse (workflow authoring) |

## The stack pack on top

One more for what the repo is actually built with. These live in the overlay
library, and each carries the concrete mechanics whose language-neutral
contract `general` already supplied:

| Pack | Contents |
|------|----------|
| `go` | Go backend skills + fix prompts |
| `flutter` | Flutter app skills + prompts |
| `react-router` | React Router web app skills |
| `react-native` | React Native app skills |
| `python-workflow` | Python CLI, testing, release skills |
| `pulumi` | Pulumi infrastructure skills (pair with `infra`) |
| `infra` | GCP CI/IAM conventions, dev-stack hardening, CLI anti-hang rules |
| `product-planning` | story-docs + write-epics-and-stories skills, product-planning prompts |
| `shared-lifecycle` | planning, review, validation prompts |
| `shared-docs` | docs/misc prompts + standard `docs/` scaffold |
| `qa` | shared QA planning prompts (per-stack QA skills ship with stack packs) |
| `research` | autonomous researcher skills, gate-loop prompts, generic research workflow |

## Two things that make the list safe to over-select

A pack named in more than one layer resolves to the highest-precedence one — an
overlay `stablemate.yml` shadows the base one name-for-name rather than merging
with it.

A selection is a **set**. A stack pack that `includes:` a contract pack
`general` already carries adds nothing, so there is no cost to naming both and
no ordering to get right.
