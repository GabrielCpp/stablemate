### `undeclared-launch-screen` — this mobile surface states no screen a cold launch opens on

A Maestro flow always opens with a bare `- launchApp`, which lands on whatever screen the app
happens to launch on — not on whatever screen the obligation being compiled is about. The
book states which screen that is with the `runbook`'s own `launch-screen:`, resolved by
`reach.surface_launch_screen` the same way `bundle-id:`/`driver:` already are: the first
non-empty value among the runbooks whose `surfaces:` names this surface, in driver order
(`web`, `mobile`, `http`, `cli`, `artifact`, `iac`, `none`, then a runbook with no driver,
ties broken by node id). One runbook stating it is enough. This surface states it nowhere —
absent on every runbook covering it — so the compiler cannot know what screen a cold launch
actually opens on and drops every mobile obligation on this surface as a gap instead of
guessing.

**This finding means the obligation has a check or act and the compiler has nothing to say a
cold launch opens where the obligation needs.** If the bullet the finding names carries no
`verify:`/`does:` of its own, you are reading the wrong finding: that is `no-verify-declared`,
and the repair is a check, not a launch screen.

To repair it, find the surface's own [`runbook`](runbook.md) that stands the mobile app up,
and state the screen a cold launch actually opens on, alongside its `bundle-id:`:

```markdown
- surfaces: [widget-list](../gui/screens/widget-list.md), [new-widget](../gui/screens/new-widget.md)
- bundle-id: com.example.mobile-app
- launch-screen: [widget-list](../gui/screens/widget-list.md)
```

**Read what the app actually opens on, don't invent one.** Launch the app cold and see which
screen renders — a hand-written Maestro flow, if one already exists for this surface, usually
already asserts the first screen after its own `- launchApp` and is the fastest way to check.
A guessed screen compiles clean and then either hides a real defect (an obligation on the
wrong screen wrongly passes) or wrongly gaps a screen the app really does open on, both worse
than the gap this finding already is.

State it on the one runbook that actually stands the app up, not on every runbook that
happens to name the surface. A runbook that lints or provisions a mobile surface never cold
launches it, and a `launch-screen:` copied onto it is a claim the book cannot back — the
resolution only needs the first one, and the runbook whose `## Steps` launch the app is the
one that has seen which screen comes up.

**Warm relaunch, an auth gate, onboarding, or a deep link are not this bullet's job.**
`launch-screen:` states only the cold-launch case; every other starting condition is a flow's
own `arrange:`/`fixture:`, stated on the obligation or journey that needs it, not a second
`launch-screen:` on the runbook.
