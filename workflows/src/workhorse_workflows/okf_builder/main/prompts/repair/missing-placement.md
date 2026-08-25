### `missing-placement` — a placed node declares no `placement:` band

This node's role is one the profile requires a placement band for, and the bullet is
missing. The band is a *measured* constraint — where the control actually sits on the
rendered screen, as width and offset percentages — and that is exactly why the finding is
grounded: **a placement is read off the running UI or the layout code, never guessed.** A
guessed band either invents a constraint the product never had (and goes red on a correct
build) or is so wide it can never go red (and observes nothing).

To repair each one:

1. Open the component's layout source — the styles, grid/flex declarations, or layout
   constants that decide its box. If the values are literal there (a fixed sidebar width, a
   percentage column), the band can be derived from the code and written down, citing the
   file you read.
2. If the layout is computed and the source does not settle it, check whether the book's
   walkthrough screenshots (under the book's screenshots directory) show this screen — a
   band can be measured off a real capture.
3. Write the band with honest tolerances: `- placement: width 60-100%, x 0-20%` says the
   control occupies the right ~half-to-full width starting near the left edge. Narrow
   enough to catch the control moving somewhere else, wide enough to survive a resize.

If neither the source nor a capture settles where the control renders, **leave the bullet
off and say so in `doc_status`** — the item comes back after a walkthrough has seen the
screen, which is the correct order. Never write a `0-100%` band to make the finding go
away: it satisfies the linter while asserting nothing.
