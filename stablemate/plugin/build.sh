#!/bin/sh
set -eu

version="$1"
rm -rf "$2"
mkdir -p "$2"
out=$(cd "$2" && pwd)
here=$(cd "$(dirname "$0")" && pwd)
folder="$out/stablemate"
archive="$out/stablemate-antigravity-$version.zip"

env -u FARRIER_LIBRARY_DIR STABLEMATE_CONFIG="$here/antigravity.toml" uv run --all-packages farrier plugin build --harness antigravity \
    --config "$here/antigravity.toml" --out "$folder" --version "$version"
if command -v agy >/dev/null 2>&1; then
    agy plugin validate --strict "$folder"
else
    echo "agy is not installed here, so the plugin was not validated" >&2
fi
(cd "$folder" && zip -qrX "$archive" .)
(cd "$out" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256")
cat "$archive.sha256"
