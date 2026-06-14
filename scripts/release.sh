#!/usr/bin/env bash
# Release one stablemate workspace package: infer the next version from the
# commit history, stamp it into pyproject.toml, build, publish to PyPI, then
# commit + tag + push.
#
# Usage:
#   scripts/release.sh <dist-name> <pkg-dir>
#
# Knobs (environment variables — also settable as `make` variables):
#   DRY_RUN=1                  Show every step; change nothing.
#   LEVEL=major|minor|patch    Force the bump level (else inferred from commits).
#   RELEASE_VERSION=x.y.z      Use an exact version (skips inference entirely).
#   PUBLISH=testpypi           Publish to TestPyPI instead of PyPI.
#   ALLOW_DIRTY=1              Skip the clean-working-tree guard.
#   NO_PUSH=1                  Commit + tag locally, but do not push.
#   ZEROVER=1                  Use pre-1.0 (0.x) bump demotion (breaking->minor).
#
# Steps are ordered so the irreversible PyPI upload happens before anything is
# pushed: if publish fails, nothing has left your machine.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
name="${1:?usage: release.sh <dist-name> <pkg-dir>}"
dir="${2:?missing <pkg-dir>}"
cd "$dir"

current="$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)"
if [ -n "${RELEASE_VERSION:-}" ]; then
  next="$RELEASE_VERSION"
  echo "release: version pinned to ${next} via RELEASE_VERSION" >&2
else
  next="$("$here/next-version.sh" "$name" "$dir" "$current")"
fi

if [ "$next" = "$current" ]; then
  echo "release: ${name} is up to date at ${current} — no new commits to release."
  exit 0
fi

tag="${name}-v${next}"
target="$([ "${PUBLISH:-}" = "testpypi" ] && echo TestPyPI || echo PyPI)"
echo "release: ${name} ${current} -> ${next}  (tag ${tag}, publish to ${target})"

echo "release: commits in this release:"
git log --oneline "${name}-v${current}..HEAD" -- "$dir" 2>/dev/null || true

if [ -n "${DRY_RUN:-}" ]; then
  echo "[dry-run] set ${dir}/pyproject.toml version -> ${next}"
  echo "[dry-run] make $([ "${PUBLISH:-}" = "testpypi" ] && echo publish-test || echo publish)"
  echo "[dry-run] git commit -m 'release(${name}): v${next}'"
  echo "[dry-run] git tag -a ${tag} -m '${name} ${next}'"
  [ -n "${NO_PUSH:-}" ] || echo "[dry-run] git push origin HEAD && git push origin ${tag}"
  exit 0
fi

# Guard: a clean tree, so the version bump is the only change we commit.
if [ -z "${ALLOW_DIRTY:-}" ] && [ -n "$(git status --porcelain)" ]; then
  echo "release: working tree not clean — commit/stash first, or set ALLOW_DIRTY=1." >&2
  exit 1
fi

# Guard: never clobber an existing tag.
if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null 2>&1; then
  echo "release: tag ${tag} already exists." >&2
  exit 1
fi

# 1. Stamp the new version.
"$here/set-version.sh" "$dir" "$next"

# 2. Build + publish (the sub-make re-reads the bumped pyproject.toml).
if [ "${PUBLISH:-}" = "testpypi" ]; then
  make publish-test
else
  make publish
fi

# 3. Record the release: commit, annotated tag, push.
git add pyproject.toml
git commit -m "release(${name}): v${next}"
git tag -a "${tag}" -m "${name} ${next}"

if [ -n "${NO_PUSH:-}" ]; then
  echo "release: committed + tagged ${tag} locally (NO_PUSH set; not pushed)."
else
  git push origin HEAD
  git push origin "${tag}"
fi

echo "release: ${name} ${next} released to ${target}."
