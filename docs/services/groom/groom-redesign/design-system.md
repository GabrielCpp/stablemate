---
type: feature
slug: design-system
title: groom — IDE console design system
status: implemented
area: groom-redesign
---
# groom — IDE console design system

A design brief for groom's operator console. groom watches `workhorse`
agent-workflow **operator gates** across many repos and workers; the operator's
job is to notice a blocked worker, read its gate question (LLM-authored
markdown), and type an answer. The interface is modeled on an IDE (Zed / VSCode):
dense, dark, keyboard-driven, live.

This file is the source of truth for `groom/groom/assets/dashboard.css`, and it
is kept current with it: where the built console has moved on from the mockup,
this brief follows the console rather than the mockup. `groom-ide.html` in this
folder is the original signed-off mockup and is **not** maintained — read it as
the design record it is, not as a description of the shipped UI.

Two things have changed since sign-off. The **Inbox** mode is gone: blocked runs
sort to the top of the Runs list, so a separate triage pane was a second place to
look with nothing of its own to say. And several **palette values have moved to
clear WCAG 2 AA contrast** — the notes in the token block below say which and why.

## Principles

- **Dense over roomy.** Thin 1px borders, tight row heights (~26–30px), small
  type. Show the whole fleet without scrolling where possible.
- **Dark, low-chroma chrome; color only for signal.** Surfaces are neutral
  greys; saturated color is reserved for worker state (esp. *blocked*).
- **Monospace for identity.** Repo, worker, node, and gate paths are code —
  render them in a mono face.
- **Keyboard-first.** Everything reachable via ⌘K palette + `j/k` navigation.
- **Live without flicker.** State streams in over the websocket; selection,
  scroll, and expanded panels survive re-renders.

## Layout — CSS grid shell

```
grid-template-columns: 48px  1fr;
grid-template-rows:    1fr   24px;         /* body, status bar */

┌────┬─────────────────────────────────────────────┐
│ AB │  MAIN — one pane at a time (data-mode)       │  row 1
│    │  ┌ runs ──────────┬ detail ───────────────┐  │
│    │  │ blocked first  │                       │  │
├────┴──┴────────────────┴───────────────────────┘  │
│  STATUS BAR (full width)                          │  row 2
└───────────────────────────────────────────────────┘
```

- **Activity bar** (`#activitybar`, 48px rail): a `<nav>` of icon buttons
  switching *mode*. One active at a time (left accent bar on the active icon,
  `aria-pressed` on the button). A `<nav>` rather than a `role="toolbar"` div:
  switching panes *is* this page's navigation, and a toolbar is not a landmark,
  so its contents would otherwise sit outside every region.
- **Main** (`#main`): one pane visible at a time, chosen by `data-mode` on
  `.app`. The Runs pane splits into the **runs list** (blocked pinned top) and
  **detail** (the selected run's activity, gate question, answer box, metrics
  and logs). Detail shows a prompt when nothing is selected.
- **Repo picker** (`#repo-menu-wrap`): not a column. A shared Zed-style
  container+repo menu, positioned under whichever pane's picker opened it — a
  `combobox` input over a `role="listbox"`, driven by `aria-activedescendant`.
  The 260px tree column the mockup had is gone; the Files and Diff panes carry
  their own trees, and the fleet is the Runs list.
- **Status bar** (`#statusbar`, 24px): global counts (blocked / running / idle /
  finished) + repo/worker totals + the **connection chip**, which reports live /
  stale / reconnecting / offline from how recently a frame arrived rather than
  from the socket's `readyState`.
- **Command palette** (`#palette`): centered overlay, ⌘K, fuzzy over
  workers/gates.
- **Toasts**: bottom-right stack, auto-dismiss, raised on new *blocked* events.

## Modes (activity bar)

| Mode | `data-mode` | Main shows |
|------|-------------|------------|
| **Runs** *(default)* | `runs` | the whole fleet, blocked pinned top, beside the selected run's detail |
| **Files** | `files` | the selected repo's worktree as a tree, beside the selected file |
| **Diff** | `diff` | the working-tree diff as a tree of changed files, beside a diff2html view |
| **Telemetry** | `telemetry` | spans and metrics, with run / node / status / duration filters |
| **Settings** | `settings` | connection / notifications / refresh |

There is no **Inbox** mode. Blocked runs sort to the top of the Runs list, which
makes a separate triage pane a second place to look with nothing of its own to
say. There is no **Fleet** mode either, for the same reason — Runs *is* the fleet.

## Color tokens (dark)

```
--bg-0:        #16181d   /* app background / activity bar */
--bg-1:        #1b1e24   /* pane heads, status bar */
--bg-2:        #21252d   /* rows, cards */
--bg-3:        #2a2f39   /* hover / selected */
--border:      #2e333d   /* 1px hairlines */
--border-2:    #3a4150   /* stronger dividers */
--text-0:      #e6e8ec   /* primary */
--text-1:      #a7adb8   /* secondary */
--text-2:      #94a3b8   /* muted — was #6b7280 */
--accent:      #4c8bf5   /* selection, focus, links */
--on-accent:   #0c0f14   /* ink on an --accent fill */
--d2h-dark-dim-color: #94a3b8   /* diff2html's own dim token, overridden */
--mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
--sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
```

**Contrast is a constraint on this palette, not a review step.** Four values
moved to clear the WCAG 2 AA 4.5:1 floor for normal text, each checked against
the *lightest* surface it can land on (`--bg-3`, a selected row) rather than the
darkest:

| Token | Was | Now | Why |
|-------|-----|-----|-----|
| `--text-2` | `#6b7280` | `#94a3b8` | the dim tier — timestamps, ids, column heads, empty states. 3.7:1 on `--bg-0` and worse on a selected row. Lightened until it clears 4.5:1 everywhere, while still reading dimmer than `--text-1`. |
| `--on-accent` | *(white, implicit)* | `#0c0f14` | white on `--accent` is 3.3:1; near-black is 5.8:1 — and unlike white it improves when `:hover` brightens the fill. |
| `--finished` | `#6b7280` | `#9ca3af` | it is a dot *and* the "done" chip's ink; the text side was 2.8:1 on a selected row. Neutral grey rather than `--text-2`'s slate, so the two dim chips stay tellable apart. |
| `--d2h-dark-dim-color` | *(diff2html's `#6e7681`)* | `#94a3b8` | diff2html colours its hunk headers from this variable, at 3.7:1 on its own info background. Overriding the variable catches every diff2html surface at once, wherever the markup is mounted. |

The floor is enforced dynamically: `groom/tests/test_a11y_dynamic.py` runs
axe-core over a live groom, pane by pane, so a colour change that regresses
contrast fails a test rather than a review.

### State → color

| State | Dot / accent | Use |
|-------|--------------|-----|
| **blocked** | `#f0483e` (red) | needs operator — the alarm color; left border on the run row, pulsing dot |
| **running** | `#38b26b` (green) | live/working |
| **idle** | `#c8873a` (amber) | waiting, no gate |
| **finished** | `#9ca3af` (grey) | terminal, dim — see the contrast note above |

### Worker type badge

Small uppercase mono chip; distinct hue per type, low saturation:
`coder` → teal `#2f9e8f`, `author` → violet `#8a6ff0`. Unknown types fall back
to a neutral grey chip. Colors are assigned by a stable hash so new types get a
consistent chip without code changes.

## Type scale

- App: 13px base, 1.4 line-height.
- Tree / run rows: 12.5px.
- Node/gate paths, badges, status bar: 11.5px mono.
- Detail question: 13px, markdown-rendered.

## Spacing

4px base grid. Row padding 4px 8px. Panel padding 8px. Gaps 6–8px. Radius small
(3–4px) — IDE, not app.

## Components

- **Activity icon button** — 48×44, centered glyph, active = left 2px accent bar
  + brighter glyph.
- **Tree node** — the Files and Diff panes: a directory row is a collapse
  chevron + name, file rows below it indent by depth. Directories start open;
  each keeps its own open/closed state locally, keyed by name, so a re-render
  does not collapse the tree under the operator.
- **Run row** — one per worker: state dot, type badge, repo@branch, worker id,
  gate/node path (mono), a one-line question preview (blocked only). Blocked rows
  pinned to top with a red left border. Selected row highlighted.
- **Detail pane** — header (repo · type · id · state · node) as a labelled
  `role="status"`, the gate question rendered markdown, the answer textarea +
  Send, and the run's metrics and logs.
- **Connection chip** — in the status bar: a dot (`aria-hidden`) paired with the
  phase word, never colour alone. Live / stale / reconnecting / offline.
- **Command palette** — input + result list; results are workers/gates with the
  same dot/badge language; Enter selects & focuses the answer box.
- **Toast** — compact card, red left edge for blocked, title + one-line body.
- **Status bar** — segmented counts with the state dots, right-aligned
  repo/worker totals, and the connection chip.

## Motion and interaction

- Selection and hover are instant (no transition). Toasts fade/slide ~150ms.
- Blocked dots pulse subtly (1.5s) to draw the eye; respect
  `prefers-reduced-motion`.
- Focus rings use `--accent`; keyboard focus always visible.

## Constraints inherited from groom (non-negotiable)

- No runtime CDN; all assets vendored. No Node/bundler.
- Everything on the wire is JSON; the server emits no markup at all. Gate
  questions arrive as untrusted markdown *strings* → marked → DOMPurify. That is
  the only path by which first-party code sets markup.
- Rendering is Preact + htm islands from the vendored `htm/preact` standalone
  ESM build, mounted into ids the static shell ships. No build step follows from
  the no-bundler constraint above.
- The live regions (`#runs-list`, `#statusbar`, `#toasts`) belong to the static
  shell, not to an island. A live region that is itself re-created by a render is
  never announced.
- Diffs rendered client-side by diff2html from `/diff/{id}` text.
