# Releasing

A release is proposed in a pull request and shipped by merging it. Every push to main
opens or refreshes that PR, and `make release` does the same without a push. The short version is in [README.md](../README.md#releasing). This document
is the mechanism: what the merge does, the upload order and the isolated smoke test in front of it, which commit types bump
what, and the one-time PyPI and GitHub setup that lives outside the repo.

The upload runs in [`.github/workflows/release.yml`](../.github/workflows/release.yml)
under [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/): GitHub mints a
short-lived OIDC token that PyPI verifies against a publisher registered as *(GabrielCpp,
stablemate, `release.yml`, environment `pypi`)*. No long-lived secret exists to leak, in the
repo or in a dotfile.

## What the merge does

The push that merges the release PR runs `make test-release` on main first. A red gate
creates no tag, so the next push to main retries the same release. On a green gate
release-please creates the tags
(`<dist-name>-v<version>`, e.g. `farrier-v1.5.1`) and GitHub releases. The `publish` job
then builds every candidate, and installs the Workflows wheel against
the sibling candidate wheels before uploading anything. That isolated install is
load-bearing: the workspace lock replaces sibling constraints with editable sources, so a
local `uv sync` can pass while the published dependency range is impossible to resolve.
Only after that smoke test do uploads proceed in dependency order:

```
ostler → workhorse-agent → farrier → workhorse-workflows → stablemate-groom → stablemate-saddlebag → stablemate
```

`stablemate-core` is not in that chain and never will be: it is vendored, not published
(see [`core/README.md`](../core/README.md)). A change to it is committed together with the
copies `make vendor` writes under `workhorse/` and `farrier/`, which is what makes
release-please bump both tools — it decides what to ship from the paths a commit touched,
so a fix committed only under `core/` would reach nobody.

groom publishes as `stablemate-groom`. The name `groom` on PyPI belongs to an unrelated
project. The import package, the `groom` command and the release-please component keep the
short name, so its tags stay `groom-v<version>`.

saddlebag publishes as `stablemate-saddlebag`. The name `saddlebag` is unavailable on PyPI.
The import package, the `saddlebag` command and the release-please component keep the
short name, so its tags stay `saddlebag-v<version>`.

The first upload of a new distribution needs a pending trusted publisher registered on PyPI
for it. Use owner GabrielCpp, repository stablemate, workflow `release.yml` and environment
`pypi`. `stablemate-saddlebag` needs one before its first release.

`stablemate` is the umbrella. It has no code and pins `workhorse-workflows`, `farrier`,
`stablemate-groom`, `ostler` and `stablemate-saddlebag`, so one `uv tool install` brings
all five. Each pin's floor is that tool's newest release and its cap is the next major
(`>=5.1.0,<6`). It uploads last, because the versions it allows must already be on the index.

A release PR bumps each member's own version, but never the pins other members hold on
it. The release job closes that gap right after release-please writes the PR.
`scripts/sync_pins.py` reads the new versions from the release branch and widens every pin
a new major left behind to that major (`>=4,<5`). Each package whose pin moved gets its
own commit on main, `fix(<package>): allow <sibling> 4.x`. release-please then runs a
second time and sees that commit, so the package that holds the pin ships in the same
release with a patch bump and a changelog line. A patch bump never leaves a major range,
so the second pass moves no sibling pin.

The umbrella's pins follow a stricter rule. Every tool that releases raises its floor in
the umbrella to the exact new version, `fix(stablemate): require farrier 5.1.0`. So a minor
or patch release of any tool also ships a new `stablemate`, and `uv tool upgrade
stablemate` reaches it. The second pass can patch a sibling that had no release of its own,
so the job runs the rewrite a third time to raise the umbrella's floor on it. Nothing pins
the umbrella, so that pass settles.

The job pushes those commits to main itself. Pull main after a release run before you
commit on top of it. Until the PR merges, main holds pins ahead of their siblings: a sibling's range one major
ahead, the umbrella's floor at the version the PR releases. `uv lock` and the pin tests
accept that, because a pin may run ahead of its member but never behind it. The job then refreshes `uv.lock` on the release branch as a `chore:`
commit, so the tree you merge passes `uv sync --locked`.

A minor or patch release moves no sibling pin, because the new version is still inside
the range. It moves only the umbrella's floor. `make sync-pins` runs the same rewrite
locally, against the versions in your tree.

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
`Restructure the workflows` subject bumps nothing. If no release PR is open,
that is why.

Baselines live in [`.release-please-manifest.json`](../.release-please-manifest.json) and the
package map in [`.release-please-config.json`](../.release-please-config.json); a new
distribution is one entry in each, plus its build/publish steps in the workflow.

A release that ships `stablemate` also attaches the Antigravity plugin to the
`stablemate-v<version>` GitHub release. The `antigravity-plugin` job runs
`stablemate/plugin/build.sh` after the PyPI upload, because the plugin's launchers fetch that
version from PyPI. The script builds from the base library alone, as
`stablemate/plugin/antigravity.toml` selects it, and validates the folder when `agy` is on
the `PATH`.

## One-time setup (not in the repo)

1. On PyPI, add a trusted publisher to each project — owner `GabrielCpp`, repository
   `stablemate`, workflow `release.yml`, environment `pypi`. A distribution that does
   not exist on the index yet gets a **pending** publisher, which its first upload
   converts into the project.
2. Create the `pypi` [environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment)
   in the repository settings, with no required reviewer, so the merge is the only approval.
3. Settings → Actions → General → **Allow GitHub Actions to create and approve pull
   requests**, or release-please cannot open the PR with the default token.
