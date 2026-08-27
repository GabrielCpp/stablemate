---
name: stablemate-ui-superdesign
description: "Superdesign Local Design Workflow — CLI setup, agent-skill install, design exploration prompts, and implementation handoff rules. Applies to UI source, design docs, and agents.yml."
metadata:
  generated_by: farrier
  source: library/skills/ui/superdesign/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-ui-superdesign/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [runbook]
---

# Superdesign Local Design Workflow

Use this skill when a task asks for local Superdesign setup, UI exploration,
visual mockups, design-system capture, or implementation handoff from
Superdesign into Codex, GitHub Copilot CLI, or Claude Code.

## Local Setup

Install and authenticate the Superdesign CLI from the repository root:

```bash
npm install -g @superdesign/cli@latest
superdesign login
```

Install the Superdesign agent skill into the local agent environment you use for design work:

```bash
npx skills add superdesigndev/superdesign-skill
```

Prefer project-level installation for repo-specific design work so generated
context, design-system notes, and any `superdesign/` working files stay scoped
to this repository. Use a global install only when you intentionally want the
skill available across many repositories.

## Claude Code Native Command

Claude Code can invoke the installed Superdesign skill as a native slash command:

```text
/superdesign help me design <your prompt>
```

Include the target surface and local constraints in the prompt. Mention the
app's UI framework, its screen/view-model patterns, and the repo's existing
design-system files (see `../stablemate-ui-design-system/SKILL.md`) when
relevant.

## Codex

Codex receives Superdesign guidance through generated skills under
`.codex/skills/` after `farrier` renders the selected packs. Ask Codex to use
the generated superdesign skill for design exploration or for applying a
Superdesign handoff.

Use this shape for local Codex prompts:

```text
Use the superdesign skill. Explore a Superdesign concept for <screen or flow>, using the current app design system and app context. Keep generated design artifacts in a local superdesign/ folder and produce an implementation-ready handoff.
```

When implementing a finalized handoff, combine this skill with the framework
UI, theme, architecture, state, navigation, API, and testing skills that match
the files being changed.

## GitHub Copilot CLI

After `farrier` runs, Copilot CLI can use the generated project skill under
`.github/skills/<repo>-ui-superdesign/SKILL.md` and the matching repository
instructions.

Use this shape for local Copilot CLI prompts:

```text
Use the superdesign project skill. Design <screen or flow> for this app, respecting the existing design system, app routes, and generated API boundaries. Keep any Superdesign context local to the repository and return an implementation handoff.
```

If your Copilot CLI session does not auto-discover project skills, paste or
reference the generated SKILL.md in the prompt, then run the same Superdesign
CLI setup commands from this file.

## Handoff Rules

- Treat Superdesign output as design context first, not production code.
- Before implementing, map the design to the repo's existing design system and
  generated API contracts.
- Keep local Superdesign artifacts out of production surfaces unless a story
  explicitly asks to commit them.
- Do not introduce new UI tokens, route structure, or state-management patterns
  just because they appear in a generated design. Adapt the design to the
  repo's conventions.
- For multi-page flows, ask Superdesign for an implementation prompt that
  includes every page, interaction, state, and empty/error/loading case needed
  by the flow.
