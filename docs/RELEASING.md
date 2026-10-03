# Releasing

A release is proposed in a pull request and shipped by merging it; `make release` only
dispatches the workflow that opens that PR. The short version is in
[README.md](../README.md#releasing). This document is the mechanism: what merging actually
does, the upload order and the isolated smoke test in front of it, which commit types bump
what, and the one-time PyPI and GitHub setup that lives outside the repo.

The upload runs in [`.github/workflows/release.yml`](../.github/workflows/release.yml)
under [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub mints a
short-lived OIDC token that PyPI verifies against a publisher registered as *(GabrielCpp,
stablemate, `release.yml`, environment `pypi`)*. No long-lived secret exists to leak, in the
repo or in a dotfile.

## What merging does

Merging the release PR re-triggers the same workflow, which then creates the tags
(`<dist-name>-v<version>`, e.g. `farrier-v1.5.1`) and GitHub releases, runs `make test`
against the merged tree, builds every candidate, and installs the Workflows wheel against
the sibling candidate wheels before uploading anything. That isolated install is
load-bearing: the workspace lock replaces sibling constraints with editable sources, so a
local `uv sync` can pass while the published dependency range is impossible to resolve.
Only after that smoke test do uploads proceed in dependency order:

```
ostler → workhorse-agent → farrier → workhorse-workflows → stablemate-groom → stablemate
```

`stablemate-core` is not in that chain and never will be: it is vendored, not published
(see [`core/README.md`](../core/README.md)). A change to it is committed together with the
copies `make vendor` writes under `workhorse/` and `farrier/`, which is what makes
release-please bump both tools — it decides what to ship from the paths a commit touched,
so a fix committed only under `core/` would reach nobody.

groom publishes as `stablemate-groom`. The name `groom` on PyPI belongs to an unrelated
project. The import package, the `groom` command and the release-please component keep the
short name, so its tags stay `groom-v<version>`.

`stablemate` is the umbrella. It has no code and allows one major version each of
`workhorse-workflows`, `farrier` and `stablemate-groom`, so one `uv tool install` brings all
three. It uploads last, because the versions it allows must already be on the index.

A release PR bumps each member's own version, but never the pins other members hold on
it. The release job closes that gap on the release branch, right after release-please
writes it: `scripts/sync_pins.py` widens every pin on a member whose new version falls
outside it to that member's major (`>=4,<5`), then `uv lock` runs, and both land as one
`chore:` commit on the PR. The tree you merge already passes the pin tests, so nothing
fails after the tags exist.

A minor or patch release moves no pin, because the new version is still inside the range.
Only a new major rewrites one. The package that holds a rewritten pin is not released for
it: release-please never sees that commit as a reason to bump. Its version already on
PyPI keeps the old range, which still resolves, and the new range ships with that
package's next release. `make sync-pins` runs the same rewrite locally.

`saddlebag` is versioned and gets changelogs but has no upload step, because it is not in
scope yet. Adding it means registering its trusted publisher on PyPI and adding its two
steps to the workflow.

| Commit since last tag | Bump |
| --- | --- |
| `feat!:` / `fix(x)!:` / `BREAKING CHANGE:` in body | major |
| `feat:` | minor |
| `fix:` / `perf:` / `refactor:` | patch |
| `docs:` / `test:` / `build:` / `ci:` / `chore:` / anything unparseable | **none — no release** |

`refactor:` is in the patch row only because `changelog-sections` in
[`.release-please-config.json`](../.release-please-config.json) puts it there. Release-please
hides that type by default, and a hidden type bumps nothing — so before that section
existed, a commit that rewrote a package shipped to nobody while reading as though it had
released. The section is written out in full because declaring it replaces the defaults
rather than extending them: a type left off the list is a type that silently stops
releasing.

That last row is the change of consequence. Under the old shell scripts a
non-conventional subject still produced a patch bump, so *any* commit released. Now the
commit message is what decides whether a package is released at all, and a
`Restructure the workflows` subject bumps nothing. If `make release` returns an empty PR,
that is why.

Baselines live in [`.release-please-manifest.json`](../.release-please-manifest.json) and the
package map in [`.release-please-config.json`](../.release-please-config.json); a new
distribution is one entry in each, plus its build/publish steps in the workflow.

## One-time setup (not in the repo)

1. On PyPI, add a trusted publisher to each project — owner `GabrielCpp`, repository
   `stablemate`, workflow `release.yml`, environment `pypi`. A distribution that does
   not exist on the index yet gets a **pending** publisher, which its first upload
   converts into the project.
2. Create the `pypi` [environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
   in the repository settings. Adding yourself as a required reviewer turns the merge into
   an explicit "approve the upload", which is the cheapest safety net available.
3. Settings → Actions → General → **Allow GitHub Actions to create and approve pull
   requests**, or release-please cannot open the PR with the default token.
