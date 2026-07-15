---
agent: agent
---

# okf-builder — walk one WEB journey against the LIVE app

The code-derived book is written; now you **prove and heal it against the running app** by walking
it **the way a real user would**. This turn handles exactly **one** worklist item. You use the docs
you already wrote as the map (retrieved with `ostler search`), drive the live UI with the Playwright
MCP, and reconcile what you see with what the book says — correcting, enriching, and discovering.

Load the method and obey it: {{ skill_load_ref("stablemate-okf-modeling", skill_dir() + "/stablemate-okf-modeling/SKILL.md") }}
Author to **Playbook B (as-built)** judgments — the docs describe the app as it really is — but your
source of truth this phase is the **running app**, not the code: when the live UI and the book
disagree, the app wins and you heal the book. The type vocabulary, per-type spec-completeness bar,
folder layout, and linter rules are in the `stablemate-ostler` skill it links to. Always finish an
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
   `interaction`/`component` children (`--type interaction`) — their `role:` / `name:` / `keyboard:`
   bullets are your `getByRole(role, {name})` locators; `leads-to` tells you the expected transition.
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
     author its `role:`/`name:`/`does:`/`leads-to:` from the snapshot, `ostler fmt`.
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
   committed documentation evidence — but do NOT put them in `code:`/`verify:`, which are code refs
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
   d. Link the evidence into the book: a **`vet:` bullet** on the screen doc pointing at
      `docs/specs/<screen-slug>/vet.md`, and on each matched component's `###` section a
      **`screenshot:` bullet** pointing at its crop
      (`docs/specs/<screen-slug>/vet/<state>-<component>.png` — the `crop` paths in the vet report).

### `screen` (a discovered screen — `target` is `screen:<slug>`)

`context` holds the user click-path that reaches it from the entry point. Open the entry URL once,
follow that path by clicking (never by URL), then document/verify the screen and its controls exactly
as in the journey case (steps 3–6). Return any further new screens in `discovered`.

### `fixup` (`context` holds `ostler doctor` output)

A mechanical docs repair from the walk checkpoint — **no browser needed**. Fix **each** finding by its
remedy (`fmt` for casing/order; `scaffold`/add the heading or bullet for a missing section; fix the
target of a dangling link). Never delete a reference or fabricate a node to silence the check. Emit
nothing.

## Output

Emit the deeper items your walk revealed (empty list if none). Deduped downstream by (kind, target),
so re-emitting a known item is harmless.

```json
{"discovered": [{"kind": "screen", "target": "screen:…", "context": "click-path from entry"}], "walk_status": "healed"}
```

`walk_status` ∈ `confirmed` (docs matched the app) | `healed` (you corrected/added docs) | `skipped`
(nothing to walk — app control missing, or a non-UI item).
