#!/usr/bin/env bash
# Stamp a version into a package's pyproject.toml (the first, project-level
# `version = "..."` line — classifiers and other lines are left untouched).
#
# Usage:
#   scripts/set-version.sh <pkg-dir> <version>
set -euo pipefail

dir="${1:?usage: set-version.sh <pkg-dir> <version>}"
new="${2:?missing <version>}"
f="${dir%/}/pyproject.toml"

[ -f "$f" ] || { echo "set-version: no such file: ${f}" >&2; exit 1; }

cur="$(grep -m1 '^version' "$f" | cut -d'"' -f2)"
if [ "$cur" = "$new" ]; then
  echo "set-version: already at ${new}; ${f} unchanged"
  exit 0
fi

sed -i -E "0,/^version = \"[^\"]*\"/s//version = \"${new}\"/" "$f"
echo "set-version: ${cur} -> ${new} in ${f}"
