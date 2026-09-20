### `unreachable-from-launch` — this obligation's own screen is not where a cold launch opens

This surface has a settled `launch-screen:`, so the compiler knows which screen a cold
`- launchApp` opens on. This obligation's own page is a *different* screen, and nothing
in the compiled flow gets from the one to the other — a standalone obligation compiles one flow file that
opens with `- launchApp` and then addresses the obligation's own controls directly, so
compiling it here would assert against a screen the launch never reaches. For a journey, only
the *first* step's page is held to this — later steps are fine, because a journey navigates,
and the finding would not be raised against them.

**This finding means the obligation is real and its check/act is real; only the address is
missing.** The compiled flow has no step that reaches this screen from where the app opens, and "an
address the book did not state is not an address the book can be held to" — so the compiler
gaps it rather than emitting a flow that opens on the wrong screen and asserts anyway.

To repair it, do not touch `launch-screen:` — it is naming the real cold-launch screen
correctly. Instead, give this obligation (or the flow it belongs to) a stated way to reach its
own screen, most often by turning it into a `flow`'s journey step that starts at the launch
screen and walks to this one:

```markdown
- start: [widget-list](../gui/screens/widget-list.md)
- steps:
  - [open-new-widget](../gui/screens/widget-list.md#open-new-widget)
  - [submit-new-widget](../gui/screens/new-widget.md#submit-new-widget)
- end: [widget-list](../gui/screens/widget-list.md)
```

**Do not repair this by inventing a second `launch-screen:` or by making it conditional.**
`launch-screen:` states one screen — the one a cold launch opens on — and nothing else: a
warm relaunch, an auth gate, onboarding, or a deep link that lands somewhere else are not a
second launch screen, they are a flow's own `arrange:`/`fixture:` naming what got the device
into that state before the claim.

If the obligation's screen genuinely never is reachable from a cold launch in this app, the
obligation is not compilable as a mobile scenario at all — read the actual navigation the app
performs (the hand-written Maestro flow, if one exists for this surface, is the fastest way to
check) rather than picking whichever screen makes the finding go away.
