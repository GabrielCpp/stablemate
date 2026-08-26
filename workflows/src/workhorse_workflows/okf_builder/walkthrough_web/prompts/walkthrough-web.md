---
agent: agent
---

# okf-builder — walk one WEB journey against the LIVE app

The code-derived book is written; now you **prove and heal it against the running app** by walking
it **the way a real user would**. This turn handles exactly **one** worklist item. You use the docs
you already wrote as the map (retrieved with `ostler search`), drive the live UI with the Playwright
MCP, and reconcile what you see with what the book says — correcting, enriching, and discovering.

Load the method and obey it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
Author to **Playbook B (as-built)** judgments — the docs describe the app as it really is — but your
source of truth this phase is the **running app**, not the code: when the live UI and the book
disagree, the app wins and you heal the book. The type vocabulary, per-type spec-completeness bar,
folder layout, and linter rules are in the `ostler` skill it links to. Always finish an
item by running `ostler fmt <touched>` on what you wrote.

## The cardinal rule: navigate like a user, never by URL

Real users do not type URLs or deep-link into screens — they start at the front door and click. So:

- Open the app **once** with `browser_navigate("{{ workhorse_var('entry_url') }}")` — the documented
  entry point. That is the **only** allowed `browser_navigate`.
- From there, reach **every** screen by acting on controls: `browser_click`, `browser_type`,
  `browser_select_option`, `browser_press_key`. **Never** compose or type another URL to jump to a
  screen. If the journey's next screen isn't reachable by a control you can find, that is a finding
  (a broken/undocumented path), not a reason to URL-jump.
- Re-run `browser_snapshot` after every transition — the accessibility snapshot is your "map" of what
  is actually on the page.
- **Document URLs along the way, don't navigate by them.** After a transition, read the landed URL
  from the snapshot and **record** it onto that screen's doc (see self-heal). URLs are an *output* you
  capture while walking, never an input you steer by.

## Guardrails (this runs unattended — stay in your lane)

- **Docs only.** You write **only** under `docs/features/{{ workhorse_var('service') }}/**` (via
  `ostler scaffold`/`set`/`fmt` and your editor) and — for visual registration — under
  `docs/specs/<screen-slug>/` (the vet manifest you author plus what `ostler vet --write` emits).
  Never modify source code, never run `git`, never build/test. You are documenting the app, not
  changing it.
- **Stay in this app and this service.** Only act on `{{ workhorse_var('entry_url') }}`'s own origin;
  never follow links off it. Only touch `docs/features/{{ workhorse_var('service') }}/…`.
- **Do not perform destructive actions.** The app is a live boot. Do **not** click controls that
  delete, submit irreversible changes, or mutate real state (Delete/Remove/Confirm on real records,
  destructive form submits). Observe them, read their documented behavior, and **describe** them in
  prose — do not trigger them.
- **One item, then stop.** Do the single item you were given. Surface deeper work by **returning** it
  in `discovered` — do not walk the whole app in one turn.

## This item

- kind: `{{ workhorse_var('item_kind') }}`
- target: `{{ workhorse_var('item_target') }}`
- context: `{{ workhorse_var('item_context') }}`
- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- entry URL: `{{ workhorse_var('entry_url') }}` — screenshots dir: `{{ workhorse_var('screenshots_dir') }}`
- CDP endpoint (shared browser, for `ostler vet`): `{{ workhorse_var('cdp_url') }}`

## What to do, by kind

### `journey` (the main case — `target` is `flow:<slug>`)

1. **Load the map from the book.** `ostler search "<slug>" --type flow --json`, then read the flow
   doc for its `start:` precondition, ordered `steps:`, and `leads-to`/screen links. For each screen
   the journey touches, `ostler search "<screen>" --type screen` and pull its controls'
   `interaction`/`component` children (`--type interaction`); `leads-to` tells you the expected
   transition.

   **Do not hand-write locators — derive them.** `ostler locators <screen-slug> --json` emits the
   exact Playwright call for every documented control on that screen, built from its `role:`/`name:`
   bullets. Use those verbatim. A locator you improvise from the live snapshot proves the *app* has
   a control; a locator derived from the book and then found in the app proves the **book is right**,
   which is the only thing this walk is for.

   `locators` exits non-zero when the mapping is broken, and each case is a finding to heal:
   - `! ambiguous` — two controls share a role and an accessible name, so the locator matches both.
     Read their real labels off the app and correct the wrong `name:`.
   - `! unnamed <role>` — an operable control with no accessible name. Read its label (visible text,
     `aria-label`, `title`) from the snapshot and write it into `name:`.
   - `~` (located by `selector:`) — a control with no `role:`. Read the computed role from the
     accessibility snapshot and record it. A control the a11y tree cannot address is one a keyboard
     and a screen-reader user cannot reach either — record it as a finding even when you can heal
     the locator.
2. **Walk it live.** Open the entry URL once, then follow the documented steps by acting on those
   controls, snapshotting after each transition. Stay on the happy path the journey describes.
3. **Classify every documented claim** against the live snapshot:
   - **confirmed** — the control exists with the documented role/name and the transition matches.
   - **mismatch** — it exists but the role/name/route/label/behavior differs from the doc.
   - **undocumented** — a control or screen the journey actually exposes that the book has no node for.
4. **Self-heal (docs only), grounded in what you saw:**
   - **mismatch** → correct the specific bullet with `ostler set <type> <name> <key>=<value>` (e.g. a
     wrong `role:`/`name:`/`leads-to:`), or `ostler edit` for prose; then `ostler fmt`.
   - **URL capture** → `ostler set screen <slug> route=<path>` (or add a `url:` bullet) with the real
     landed path for each screen you reached.
   - **undocumented control on a known screen** → `ostler scaffold interaction <id> --in <screen doc>`,
     author its `role:`/`name:`/`keyboard:`/`does:`/`leads-to:` from the snapshot, `ostler fmt`.

   **Read `role:`/`name:`/`keyboard:` off the accessibility snapshot, never off the markup.**
   `browser_snapshot` *is* the accessibility tree, so it reports the computed role and accessible
   name — the same two values Playwright matches on and a screen reader announces. Inferring them
   from the tag (`<button>` ⇒ `button`) is a guess that disagrees with the app whenever a
   `role=`/`aria-label` override is in play, which is exactly the case worth documenting. For
   `keyboard:`, press `Tab` to confirm the control actually takes focus, and record `none` when it
   does not — a pointer-only control is an accessibility defect the book should be able to *find*,
   not a blank to leave empty.
   - **a new screen** you reached by navigation that has no doc → **return it in `discovered`** as
     `{"kind":"screen","target":"screen:<slug>","context":"<the click-path from the entry point that
     reaches it>"}` so a later turn walks it *via that user path*. Do not fully document it now.
5. **Capture evidence — into the book.** Capture **fresh on every walk** — existing
   `screenshot:`/`vet:` bullets are last walk's evidence, not this one's; re-capture and re-vet
   (both replace in place, so this is idempotent). At each confirmed screen state: scroll to the top first
   (`browser_evaluate` `window.scrollTo(0,0)` — it pins every `getBoundingClientRect` to document
   coordinates, so long screens work), then take a **full-page** `browser_take_screenshot` to
   `{{ workhorse_var('screenshots_dir') }}/<slug>-<state>.png` and reference it from the screen/flow
   doc with a **`screenshot:` bullet** holding the repo-relative path
   (`docs/features/{{ workhorse_var('service') }}/gui/screenshots/<slug>-<state>.png`). These are
   committed documentation evidence — but do NOT put them in `code:`/`tests:`, which are code refs
   the linter validates.
6. **Visually register every documented component** with `ostler vet` — same page, still at top
   scroll, no resize between the screenshot and this step:
   a. Build the manifest from the screen doc's `###` component sections: for each one with a
      `selector:` bullet, `browser_evaluate` its `getBoundingClientRect()` and emit
      `{"name": "<component-slug>", "selector": "<selector>", "role": "<explicit role or ''>",
      "bbox": {"x":…, "y":…, "width":…, "height":…}, "visible": true}`. Write the list to
      `docs/specs/<screen-slug>/vet/<state>-manifest.json`.
   b. Keep exactly **one** tab open (close any extras) — the CDP scan walks every open page.
   c. Run `ostler vet <screenshot> --manifest <manifest> --cdp-url {{ workhorse_var('cdp_url') }}
      --slug <screen-slug> --state <state> --write` from the repo root. **Exit 1 is a signal, not a
      failure**: `missing` = a documented component did not render → heal that component's doc (fix
      its `selector:`/bullets) or record the mismatch; `unexpected`/`unlabeled` = on-screen UI the
      book doesn't know → scaffold the interaction or return it in `discovered`. Re-run vet once
      after healing.
   d. **Record where each structural component sits** — a `placement:` bullet on the `###` section
      of every component whose `role:` is `main`, `article`, `navigation`, `banner`,
      `complementary`, `region`, `form` or `dialog`. Read it off the rect you already measured in
      (a), as a share of the viewport, and write a **band**:

      ```markdown
      - placement: width 60-100%, x 0-20%
      ```

      Keys are `x`, `y`, `width`, `height`; an omitted key is unconstrained. This is the one
      bullet QA can use to tell a correct page from one crushed into a column against a margin,
      because `role:` and `selector:` are satisfied either way. Two rules make it survive:
      **state a band, never a point** — wide enough that a resize, a scrollbar or a longer label
      does not move the component out of it — and **never widen a band to make a red QA run go
      green**; a component outside its documented band is the defect the bullet exists to catch.
      Constrain only what the design actually requires; a sidebar's `width` and `x` are
      load-bearing, its `height` usually is not.
   e. Link the evidence into the book: a **`vet:` bullet** on the screen doc pointing at
      `docs/specs/<screen-slug>/vet.md`, and on each matched component's `###` section a
      **`screenshot:` bullet** pointing at its crop
      (`docs/specs/<screen-slug>/vet/<state>-<component>.png` — the `crop` paths in the vet report).

### `screen` (an unconfirmed screen — `target` is the screen's node id)

This is the sweep that reaches screens no journey covers. `target` is a node id
(`docs/features/<service>/gui/screens/<slug>.md`); `context` is its title.

1. **Derive the path from the book — do not invent one.** Identify the landing screen (the one
   whose `route:` matches the entry URL's path), then:

   ```
   ostler reach <target> --from <landing-node-id> --surface {{ workhorse_var('service') }} --json
   ```

   It returns the hops — each with the component to `activate` or the interaction to `interact`
   with — plus, per hop, the destination's `preconditions` (`guards` to satisfy, `params` naming
   the interaction that mints a required entity). Satisfy a hop's preconditions before making it.

2. **A missing route is a finding, not a licence to navigate by URL.** `reach` exits non-zero when
   the book describes no way in. That is a real defect — a screen no documented path reaches is one
   a user cannot reach either, and typing its `route:` would prove only that a URL renders, never
   that the screen is reachable. Record it (see below) and move on; do **not** fall back to the
   `route:` bullet, and do not mark the item confirmed.

   The same applies to `! preconditions undeclared`: a screen whose `requires:`/`params:` are
   missing cannot be walked with confidence, because you cannot know what state it needed.

3. **Walk it and register it.** Follow the hops by clicking, then document/verify the screen and its
   controls exactly as in the journey case (steps 3–6) — including the full-page screenshot and the
   per-component `ostler vet` registration, which is what makes the screen *confirmed*. Return any
   further new screens in `discovered`.

**Recording an unreachable or undeclared screen.** Repair the book where you can ground the fix in
what you actually saw: add the missing `leads-to:` to the component that navigates there, or the
missing `requires:`/`params:` bullets. Where you cannot ground it, leave the screen unconfirmed and
report it in `walk_status` — an unreachable screen is flagged, **never** pruned. The source says the
screen exists; a failed walk only ever proves it was not confirmed, never that it is gone.

### `fix:‹code›` (`context` holds one node's findings for one doctor code)

A docs repair from the walk checkpoint — **no browser needed**. The `context` is a JSON object
`{"code", "node", "path", "grounded", "findings"}`; every finding in it is the same code on the same
node. Fix **each** by its remedy (`fmt` for casing/order; `scaffold`/add the heading or bullet for a
missing section; fix the target of a dangling link). When `grounded` is true the finding does not
carry the value — read it out of the source rather than inventing one. Never delete a reference, a
claim or a `verify:` to silence the check, and never fabricate a node. Emit nothing.

## Output

Emit the deeper items your walk revealed (empty list if none). Deduped downstream by (kind, target),
so re-emitting a known item is harmless.

```json
{"discovered": [{"kind": "screen", "target": "screen:…", "context": "click-path from entry"}], "walk_status": "healed"}
```

`walk_status` ∈ `confirmed` (docs matched the app) | `healed` (you corrected/added docs) | `skipped`
(nothing to walk — app control missing, or a non-UI item).
