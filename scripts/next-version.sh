#!/usr/bin/env bash
# Compute the next semantic version for one stablemate workspace package from its
# Conventional-Commit history since the package's last release tag.
#
# Usage:
#   scripts/next-version.sh <dist-name> <pkg-dir> <current-version>
#
# Release tags follow "<dist-name>-v<version>" (e.g. farrier-v1.3.0). Commits are
# scoped to <pkg-dir>, so the two packages version independently in the monorepo.
#
# Bump rules (https://www.conventionalcommits.org):
#   breaking  -> major   ("feat!:", "fix(x)!:", or "BREAKING CHANGE" in the body)
#   feat      -> minor
#   otherwise -> patch   (fix/perf/refactor/docs/chore/test/style/ci/build/none)
#
# Standard semver by default (feat -> minor, breaking -> major) — this matches
# how the packages have been versioned to date. Set ZEROVER=1 to opt into the
# pre-1.0 convention that demotes one level while on 0.y.z (breaking -> minor,
# feat -> patch), so a 0.x package never jumps to 1.0.0 by accident.
#
# Overrides: LEVEL=major|minor|patch forces the bump level.
#
# Prints the next "MAJOR.MINOR.PATCH" to stdout (the current version unchanged
# when there is nothing to release). All diagnostics go to stderr.
set -euo pipefail

name="${1:?usage: next-version.sh <dist-name> <pkg-dir> <current-version>}"
dir="${2:?missing <pkg-dir>}"
current="${3:?missing <current-version>}"

tag="${name}-v${current}"
if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null 2>&1; then
  range="${tag}..HEAD"
else
  range="HEAD"
  echo "next-version: no tag ${tag}; scanning full history of ${dir}" >&2
fi

rank() { case "$1" in major) echo 3;; minor) echo 2;; patch) echo 1;; *) echo 0;; esac; }

level="none"
count=0
while IFS= read -r -d '' msg; do
  count=$((count + 1))
  header="${msg%%$'\n'*}"
  this="patch"
  if printf '%s' "$header" | grep -qiE '^[a-z]+(\([^)]*\))?!:'; then
    this="major"
  elif printf '%s\n' "$msg" | grep -qE '(^|[[:space:]])BREAKING[ -]CHANGE'; then
    this="major"
  elif printf '%s' "$header" | grep -qiE '^feat(\([^)]*\))?:'; then
    this="minor"
  fi
  if [ "$(rank "$this")" -gt "$(rank "$level")" ]; then level="$this"; fi
done < <(git log -z --format=%B "$range" -- "$dir")

if [ -n "${LEVEL:-}" ]; then
  level="$LEVEL"
  echo "next-version: level forced to ${level} via LEVEL" >&2
fi

if [ "$level" = "none" ]; then
  echo "next-version: no commits scoped to ${dir} since ${tag}; nothing to bump" >&2
  printf '%s\n' "$current"
  exit 0
fi

echo "next-version: ${count} commit(s) since ${tag}; bump=${level}" >&2

IFS=. read -r MA MI PA <<EOF
$current
EOF
MA=${MA:-0}; MI=${MI:-0}; PA=${PA:-0}

if [ "$MA" -eq 0 ] && [ -n "${ZEROVER:-}" ]; then
  case "$level" in
    major) level="minor"; echo "next-version: 0.x demotion major->minor" >&2;;
    minor) level="patch"; echo "next-version: 0.x demotion minor->patch" >&2;;
  esac
fi

case "$level" in
  major) MA=$((MA + 1)); MI=0; PA=0;;
  minor) MI=$((MI + 1)); PA=0;;
  patch) PA=$((PA + 1));;
  *) echo "next-version: invalid level '${level}'" >&2; exit 2;;
esac

printf '%s\n' "${MA}.${MI}.${PA}"
