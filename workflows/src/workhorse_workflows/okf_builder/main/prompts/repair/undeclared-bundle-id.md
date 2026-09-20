### `undeclared-bundle-id` — this mobile surface states no package a Maestro flow can open

`ostler qa compile-plan` reads a mobile target's `appId:` off the book, per surface,
rather than from a placeholder applied to every surface alike — the `runbook` node whose
`surfaces:` bullet points into this surface, via that runbook's own `bundle-id:`. This
obligation's surface states none, so the compiler cannot address a real installed package
and drops the obligation as a gap instead of guessing.

**This finding means the obligation has a check or act and the compiler has no package to
launch it in.** If the bullet the finding names carries no `verify:`/`does:` of its own,
you are reading the wrong finding: that is `no-verify-declared`, and the repair is a
check, not a bundle id.

To repair it, find the surface's own [`runbook`](runbook.md) that stands the mobile app
up, and state its real bundle/package identity alongside its `surfaces:` bullet:

```markdown
- surfaces: [mobile-app](../mobile/mobile-app.md)
- bundle-id: com.example.mobile-app
```

**Read the actual app configuration, don't invent an id.** The value has to be the
package/bundle identifier the app is really built and installed under — an
`app.json`/`build.gradle`/`Info.plist` is where that string lives. A guessed id compiles
clean and then every Maestro flow against it fails to launch, which is a worse failure
than the gap this finding already is.

If several runbooks cover this surface and disagree on the bundle id, mark the one that
actually exercises it `walkthrough: true` rather than leaving the disagreement standing —
the same remedy `conflicting-surface-driver`/`undeclared-walkthrough-runbook` already ask
for.
