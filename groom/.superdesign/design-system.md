# groom — IDE console design system

A design brief for groom's operator console. groom watches `workhorse`
agent-workflow **operator gates** across many repos and workers; the operator's
job is to notice a blocked worker, read its gate question (LLM-authored
markdown), and type an answer. The interface is modeled on an IDE (Zed / VSCode):
dense, dark, keyboard-driven, live.

This file is the source of truth for the static mockup (`groom-ide.html`) and,
after sign-off, for `groom/groom/assets/dashboard.css`.

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
grid-template-columns: 48px  260px  1fr;
grid-template-rows:    1fr   22px;         /* body, status bar */

┌────┬─────────────┬──────────────────────────────┐
│ AB │  PICKER     │  MAIN (split)                 │  row 1
│    │             │  ┌ inbox ─────┬ detail ─────┐ │
│    │             │  │            │             │ │
├────┴─────────────┴──┴────────────┴─────────────┘ │
│  STATUS BAR (full width)                         │  row 2
└──────────────────────────────────────────────────┘
```

- **Activity bar** (`#activitybar`, 48px rail): stacked icon buttons switching
  *mode*. One active at a time (left accent bar on the active icon).
- **Picker** (`#picker`, 260px): a live **Repository → worker** tree. Filter box
  pinned at top. Each worker node = state dot + type badge + short id + current
  node. Selected node highlighted.
- **Main** (`#main`, flex): split into **inbox** (worker list, blocked pinned
  top) and **detail** (selected worker's gate question + answer + diff). Detail
  collapses when nothing is selected (inbox takes full width).
- **Status bar** (`#statusbar`, 22px): global counts (blocked / running / idle /
  finished) + websocket-live dot + repo/worker totals.
- **Command palette** (`#palette`): centered overlay, ⌘K, fuzzy over
  workers/gates.
- **Toasts**: bottom-right stack, auto-dismiss, raised on new *blocked* events.

## Modes (activity bar)

| Icon | Mode | Picker shows | Main shows |
|------|------|--------------|------------|
| 📥 | **Inbox** *(default)* | worker tree | triage inbox (blocked first) + detail |
| 🗂 | **Fleet** | worker tree | full fleet grid, all states |
| ⇄ | **Changes** | workers w/ diffs | diff2html of selected worker |
| ⚙ | **Settings** | — | connection / notifications / refresh |

## Color tokens (dark)

```
--bg-0:        #16181d   /* app background / activity bar */
--bg-1:        #1b1e24   /* picker, status bar */
--bg-2:        #21252d   /* inbox rows, cards */
--bg-3:        #2a2f39   /* hover / selected */
--border:      #2e333d   /* 1px hairlines */
--border-2:    #3a4150   /* stronger dividers */
--text-0:      #e6e8ec   /* primary */
--text-1:      #a7adb8   /* secondary */
--text-2:      #6b7280   /* muted / disabled */
--accent:      #4c8bf5   /* selection, focus, links */
--mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
--sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
```

### State → color

| State | Dot / accent | Use |
|-------|--------------|-----|
| **blocked** | `#f0483e` (red) | needs operator — the alarm color; left border on inbox row, pulsing dot |
| **running** | `#38b26b` (green) | live/working |
| **idle** | `#c8873a` (amber) | waiting, no gate |
| **finished** | `#6b7280` (grey) | terminal, dim |

### Worker type badge

Small uppercase mono chip; distinct hue per type, low saturation:
`coder` → teal `#2f9e8f`, `author` → violet `#8a6ff0`. Unknown types fall back
to a neutral grey chip. Colors are assigned by a stable hash so new types get a
consistent chip without code changes.

## Type scale

- App: 13px base, 1.4 line-height.
- Tree / inbox rows: 12.5px.
- Node/gate paths, badges, status bar: 11.5px mono.
- Detail question: 13px, markdown-rendered.

## Spacing

4px base grid. Row padding 4px 8px. Panel padding 8px. Gaps 6–8px. Radius small
(3–4px) — IDE, not app.

## Components

- **Activity icon button** — 48×44, centered glyph, active = left 2px accent bar
  + brighter glyph.
- **Tree node** — indent by depth; repo row is a bold-ish header with a collapse
  chevron + repo@branch (mono) + mini-summary (e.g. `coder ×2 · author ×1 · 1⛔`);
  worker rows below: state dot, type badge, `#id`, current node (mono, muted).
- **Inbox row** — one per worker: state dot, type badge, repo@branch, worker id,
  gate/node path (mono), a one-line question preview (blocked only). Blocked rows
  pinned to top with a red left border. Selected row highlighted.
- **Detail pane** — header (repo · type · id · state · node), the gate question
  rendered markdown, the answer textarea + Send, and a Diff disclosure
  (diff2html, dark).
- **Command palette** — input + result list; results are workers/gates with the
  same dot/badge language; Enter selects & focuses the answer box.
- **Toast** — compact card, red left edge for blocked, title + one-line body.
- **Status bar** — segmented counts with the state dots, ws-live indicator
  (green when connected), right-aligned repo/worker totals.

## Interaction / motion

- Selection and hover are instant (no transition). Toasts fade/slide ~150ms.
- Blocked dots pulse subtly (1.5s) to draw the eye; respect
  `prefers-reduced-motion`.
- Focus rings use `--accent`; keyboard focus always visible.

## Constraints inherited from groom (non-negotiable)

- No runtime CDN; all assets vendored. No Node/bundler.
- Gate questions are untrusted markdown → escaped `data-md` node → marked →
  DOMPurify only. Never raw innerHTML.
- Diffs rendered client-side by diff2html from `/diff/{id}` text.
