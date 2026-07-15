#!/usr/bin/env bash
# Commit and push the agent's spec/code edits to the result branch so they
# survive the ephemeral container. Idempotent: a no-op commit is skipped.
#
# Args:
#   $1  repo dir       (e.g. /workspace/<repo>)
#   $2  result branch  (e.g. <program-slug>/auto)
#
# Outputs JSON: {"publish_result": {"pushed": true|false, "branch": "...", "status": "ok"}}
set -euo pipefail

REPO_DIR="${1:?repo dir required}"
RESULT_BRANCH="${2:-research/auto}"
PROGRAM_DIR="${3:-}"

# Program label for the commit message, so a non-HRNet program is not mislabelled.
# Prefer the program dir's basename (the proper, correctly-cased program name, e.g.
# specs/SMCNv3 → SMCNv3); else derive from the result branch (drop trailing "/auto").
if [ -n "$PROGRAM_DIR" ]; then
  PROGRAM_LABEL="$(basename "$PROGRAM_DIR")"
else
  PROGRAM_LABEL="${RESULT_BRANCH%/*}"
fi
: "${PROGRAM_LABEL:=$RESULT_BRANCH}"

cd "$REPO_DIR"

git config user.email "research-agent@local" >/dev/null 2>&1 || true
git config user.name  "Research Agent"        >/dev/null 2>&1 || true

# Work on the result branch (create or switch).
git checkout -B "$RESULT_BRANCH" >&2

git add -A

if git diff --cached --quiet; then
  echo "[publish] no changes to commit" >&2
  echo "{\"publish_result\": {\"pushed\": false, \"branch\": \"$RESULT_BRANCH\", \"status\": \"ok\"}}"
  exit 0
fi

git commit --quiet -m "$PROGRAM_LABEL: automated gate update" >&2

if git push --quiet --force-with-lease origin "$RESULT_BRANCH" >&2; then
  echo "{\"publish_result\": {\"pushed\": true, \"branch\": \"$RESULT_BRANCH\", \"status\": \"ok\"}}"
else
  # No write credential / no remote: keep edits local; artifacts still capture them.
  echo "[publish] push failed — edits remain on local branch $RESULT_BRANCH only" >&2
  echo "{\"publish_result\": {\"pushed\": false, \"branch\": \"$RESULT_BRANCH\", \"status\": \"push_failed\"}}"
fi
