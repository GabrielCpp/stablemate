---
type: feature
slug: README
area: groom-redesign
title: groom — IDE console redesign (design result)
status: implemented
---
# groom — IDE console redesign (design result)

Superdesign output for reworking groom's UI from its single 7-column table into
an **IDE-style operator console** (Zed / VSCode metaphor). This folder is the
signed-off design result; implementation into the live
`groom/` package is tracked separately.

See [`../groom.md`](../groom.md) for the feature's architecture and signal model.

## Contents

- **`design-system.md`** — the design brief / token system: dark VSCode-density
  palette, the CSS-grid shell spec, the mode set, state→color map, and the
  component inventory. Source of truth for the eventual `groom/groom/assets/
  dashboard.css`.
- **`groom-ide.html`** — a standalone, interactive mockup with fake
  multi-repo / multi-worker data. Open it directly in a browser (it references
  groom's already-vendored `marked` / `DOMPurify` / `diff2html` via relative
  paths, so no server or network is required).

## The design at a glance

A three-pane IDE shell over a live status bar:

- **Activity bar** (left rail) — switch mode: **Inbox** (triage, blocked-first) ·
  **Fleet** (browse the whole repo→worker tree) · **Changes** (working-tree
  diffs) · **Settings**.
- **Picker** — live `Repository → worker` tree; each repo header shows a compact
  type summary (`coder×2 author×1`) + a red blocked-count pill; each worker shows
  a state dot, type badge, `#id`, and current node.
- **Main (split)** — an **inbox** of all workers (blocked pinned to the top with
  a red edge + a one-line question preview) beside a **detail pane** for the
  selected worker: the gate path, the rendered markdown question, a large answer
  box + Send, and a dark **diff2html** working-tree diff.
- **Status bar** — blocked / running / idle / finished counts, repo & worker
  totals, a websocket-live dot, and the ⌘K hint.
- **Command palette (⌘K)** — fuzzy jump to any worker or blocked gate.
- **Toasts** — raised bottom-right on a new block.

## Load-bearing properties carried from groom (preserved by the design)

- Gate questions are untrusted LLM-authored markdown → escaped `data-md` text
  node → `marked` → `DOMPurify` only (the mockup includes an `<img onerror>` /
  `<script>` XSS probe that renders inert).
- Diffs render client-side with `diff2html` from `/diff/{id}` text (dark scheme).
- No runtime CDN; every asset is vendored. No Node / bundler.

## New data requirement surfaced by the design

The `Repository → worker (type)` hierarchy needs a **worker type** the model
doesn't capture yet. It is derivable host-side from the `/workflow` mount's
`Source` basename (`.../workflows/coder` → `coder`), with the
`com.docker.compose.service` label as a fallback — no sidecar change.
