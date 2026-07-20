#!/usr/bin/env bash
# Rerunnable driver for the todo-app benchmark: genesis → author → coder.
#
# Every phase is separately invocable, because they have wildly different costs and failure
# modes and you almost never want to redo an earlier one to retry a later one:
#
#   ./run.sh genesis     create the repo + all four service skeletons   (minutes)
#   ./run.sh author      backlog.md → epics/stories                     (tens of minutes)
#   ./run.sh coder       implement every story                          (hours)
#   ./run.sh all         the three above, in order
#   ./run.sh reset       delete the target and start clean
#   ./run.sh status      what exists so far
#   ./run.sh report      did the machinery get there WITHOUT repair loops?
#
# Idempotent by construction: genesis keys its skeleton step on each *service's* marker
# file, so re-running skips surfaces that already exist rather than clobbering them. That
# means a failed run is resumed by re-running the same command, which is the property that
# makes a benchmark worth having.
#
# Env:
#   TARGET      where to build the app        (default /tmp/todo-app)
#   STABLEMATE  this repo                     (default: derived from this script's path)
#   SURFACES    surface list                  (default ./surfaces.yml)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:-/tmp/todo-app}"
STABLEMATE="${STABLEMATE:-$(cd "$HERE/../.." && pwd)}"
SURFACES="${SURFACES:-$HERE/surfaces.yml}"
CODER_DIR="$STABLEMATE/base-library/workflows/coder"
AUTHOR_DIR="$STABLEMATE/base-library/workflows/author"
LOG_DIR="${LOG_DIR:-$HERE/.runs}"

mkdir -p "$LOG_DIR"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# Reads surfaces.yml without a yaml dependency in the shell: python is already required by
# every workflow here, so it is not a new one.
py() { uv run --project "$STABLEMATE" python3 "$@"; }

surface_params() {
  py - "$SURFACES" "$TARGET" "$1" <<'PY'
import json, sys, yaml
spec = yaml.safe_load(open(sys.argv[1]))
target, want = sys.argv[2], sys.argv[3]
repo = spec.get("repo") or {}
for s in spec["surfaces"]:
    if s["service"] != want:
        continue
    print(json.dumps({
        "target": target,
        "service": s["service"],
        "service_root": s["service_root"],
        "packs": s.get("packs", ""),
        # The docs scaffold rides along with the first surface so docs/epics/ exists before
        # anything reads the graph; farrier's scaffold step skips files already present.
        "scaffolds": ",".join(x for x in (repo.get("docs_scaffold", ""), s.get("scaffolds", "")) if x),
        "init_cmd": s.get("init_cmd", ""),
        "marker": s.get("marker", ""),
        "markers": s.get("markers", ""),
        "workflows": "coder,author",
    }))
    break
else:
    sys.exit(f"no surface {want!r} in {sys.argv[1]}")
PY
}

surface_names() {
  py -c "
import sys, yaml
print(' '.join(s['service'] for s in yaml.safe_load(open(sys.argv[1]))['surfaces']))
" "$SURFACES"
}

cmd_genesis() {
  say "genesis → $TARGET"
  for svc in $(surface_names); do
    say "genesis: $svc"
    params="$(surface_params "$svc")"
    ( cd "$CODER_DIR" && uv run workhorse run coder genesis --params "$params" ) \
      2>&1 | tee "$LOG_DIR/genesis-$svc.log"
  done
  cmd_seed_backlog
  say "genesis complete"
}

# The benchmark's input. Copied rather than generated: the whole point is that every run
# starts from the same 18 bullets, so the outcome is attributable to the workflows and not
# to a backlog that drifted between runs.
cmd_seed_backlog() {
  [ -d "$TARGET/docs" ] || die "no $TARGET/docs — run genesis first"
  cp "$HERE/docs/backlog.md" "$TARGET/docs/backlog.md"
  say "seeded docs/backlog.md ($(grep -c '^- \[' "$HERE/docs/backlog.md") bullets)"
}

cmd_author() {
  [ -f "$TARGET/docs/backlog.md" ] || die "no backlog at $TARGET/docs/backlog.md — run genesis"
  say "author → epics + stories"
  ( cd "$AUTHOR_DIR" && AGENT_REPO_DIR="$TARGET" uv run workhorse run author \
      --params '{"backlog":"docs/backlog.md"}' ) 2>&1 | tee "$LOG_DIR/author.log"
}

cmd_coder() {
  [ -f "$TARGET/docs/epics/index.md" ] || die "no epic queue — run author first"
  say "coder → implementation"
  ( cd "$CODER_DIR" && AGENT_REPO_DIR="$TARGET" uv run workhorse run coder \
      --params "{\"docs_path\":\"$TARGET\"}" ) 2>&1 | tee "$LOG_DIR/coder.log"
}

cmd_status() {
  say "status of $TARGET"
  [ -d "$TARGET" ] || { echo "  (does not exist)"; return; }
  printf '  git:      '; git -C "$TARGET" log --oneline 2>/dev/null | wc -l | tr -d '\n'; echo " commit(s)"
  for svc in $(surface_names); do
    root=$(py -c "
import sys, yaml
print(next(s['service_root'] for s in yaml.safe_load(open(sys.argv[1]))['surfaces'] if s['service']==sys.argv[2]))
" "$SURFACES" "$svc")
    marker=$(py -c "
import sys, yaml
print(next(s.get('marker','') for s in yaml.safe_load(open(sys.argv[1]))['surfaces'] if s['service']==sys.argv[2]))
" "$SURFACES" "$svc")
    if [ -f "$TARGET/$root/$marker" ]; then printf '  %-8s ✓ %s\n' "$svc" "$root/$marker"
    else printf '  %-8s ✗ missing %s\n' "$svc" "$root/$marker"; fi
  done
  printf '  backlog:  '; [ -f "$TARGET/docs/backlog.md" ] && grep -c '^- \[' "$TARGET/docs/backlog.md" || echo 0
  printf '  epics:    '; ls "$TARGET/docs/epics" 2>/dev/null | grep -v index.md | wc -l
  printf '  stories:  '; find "$TARGET/docs/epics" -name story.md 2>/dev/null | wc -l
}

# The benchmark's real question is not "did a valid repo appear" but "did the machinery get
# there on its own". Those come apart: a run that needed an agent to diagnose and hand-repair a
# deterministic gap still ends with a valid repo, and reading only the end state scores that as
# success. Every repair loop is a defect in the workflow, so they are counted here rather than
# left for someone to notice in a log.
cmd_report() {
  say "machinery reliability"
  py - "$CODER_DIR/.agents/runs" "$AUTHOR_DIR/.agents/runs" <<'PY'
import json, pathlib, sys

# Nodes that only ever run because something upstream failed. Reaching one is not an error —
# the bounded loops exist so a run can recover — but it means the deterministic path did not
# hold, which is the number this benchmark is actually about.
REPAIR = {
    "fix_genesis", "fix_story", "fix_ci", "fix_merge", "setup_fix",
    "rework_story", "rework_epics", "apply_review", "apply_qa_fixes",
}
rows, total_repairs = [], 0
for runs_dir in (pathlib.Path(a) for a in sys.argv[1:]):
    for run in sorted(p for p in runs_dir.glob("*") if p.is_dir()):
        events = run / "events.jsonl"
        if not events.is_file():
            continue
        entered, repairs, failed = [], [], False
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("phase") != "enter":
                continue
            node = ev.get("node", "")
            entered.append(node)
            if node in REPAIR:
                repairs.append(node)
            if node.endswith("_failed"):
                failed = True
        total_repairs += len(repairs)
        rows.append((run.name, len(entered), repairs, failed))

if not rows:
    print("  no runs recorded yet")
    raise SystemExit(0)

for name, n_nodes, repairs, failed in rows:
    status = "FAILED" if failed else ("repaired" if repairs else "clean")
    mark = {"clean": "\u2713", "repaired": "\u26a0", "FAILED": "\u2717"}[status]
    detail = f"  ({', '.join(sorted(set(repairs)))} x{len(repairs)})" if repairs else ""
    print(f"  {mark} {name:<26} {n_nodes:>3} nodes  {status}{detail}")

clean = sum(1 for _, _, r, f in rows if not r and not f)
print(f"\n  {clean}/{len(rows)} run(s) completed with no repair loop.")
if total_repairs:
    print(f"  {total_repairs} repair-loop entr(y/ies) total — each one is a workflow defect,")
    print("  not a successful recovery. A clean re-run is the only proof a fix landed.")
PY
}

cmd_reset() {
  say "reset $TARGET"
  rm -rf "$TARGET"
  echo "  removed"
}

case "${1:-all}" in
  genesis) cmd_genesis ;;
  backlog) cmd_seed_backlog ;;
  author)  cmd_author ;;
  coder)   cmd_coder ;;
  status)  cmd_status ;;
  report)  cmd_report ;;
  reset)   cmd_reset ;;
  all)     cmd_genesis; cmd_author; cmd_coder ;;
  *)       die "unknown command: $1 (genesis|backlog|author|coder|all|status|report|reset)" ;;
esac
