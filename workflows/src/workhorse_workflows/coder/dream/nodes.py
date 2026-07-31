"""The dream flow's deterministic halves: read a past run's process record, drain the inbox.

Ports `gather-run-evidence.py` and `record-improvements.py`.

`dream` reflects on a **previous** run, not its own, and the thing it reflects on is the
process record rather than the artifacts. A story's `review.md` and `qa.md` say what was
finally decided; they say nothing about what looped four times, what stalled for eleven
minutes, or what was retried until it passed. That lives in `events.jsonl`, and turning it
into a digest is this module's first half.

The second half is what keeps reflection from being a per-run dead document: proposals go
into a durable ledger deduped by (layer, title), and a proposal seen again in a later run
bumps a count rather than landing twice. Recurring friction accumulating evidence is the
whole signal — a one-off annoyance and a structural defect look identical in a single run.

**The loop closes at human review, not at auto-mutation.** Nothing here edits a prompt, a
workflow or a script. A flow that rewrote its own instructions on the strength of one
model's reflection would have no reviewer at the point where it matters most.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.paths import DREAM_INBOX, DREAM_LEDGER
from workhorse_workflows.coder.shared.schemas.dream import ImprovementsRecorded, RunEvidence

#: The layers a proposal may be filed under. Anything else is filed as `infra` rather than
#: dropped — a proposal with a bad label is still a proposal, and dropping it silently is
#: how a ledger stops being trustworthy.
VALID_LAYERS = frozenset({"base-prompt", "repo-flavor", "workflow-dag", "ostler", "infra"})

#: How much of the node path to keep in the digest, and how many slow nodes to rank. Both
#: are context-budget choices: the digest is read by a model, and a 4,000-visit path tail
#: would crowd out the loops it is there to explain.
PATH_TAIL = 30
SLOW_NODES = 10


@blueprint.node
def gather_run_evidence(
    logger: logging.Logger, run_dir: str = "", docs_path: str = "", repo_dir: str = ""
) -> RunEvidence:
    """Digest a finished run's `events.jsonl` into the signals reflection actually needs.

    Three artifacts carry the process record, and only the first is authoritative:

    * `events.jsonl` — one line per node enter/done. Repeated `enter`s for a node **are**
      a loop; a long enter→done gap is a stall. Nested `_flow` sub-runs keep their own,
      so they are read too and scoped by their path under the run.
    * `<node>/output.json` — each node's structured result. Final state only: a re-run
      overwrites it, which is exactly why the loop count comes from the event log.
    * `<node>/.session_id` — a pointer into the agent backend's own store, where the full
      turn-by-turn transcript lives. Too large to inline and too useful to lose, so the
      digest carries the pointers and the prompt is told how to follow them.

    With no `run_dir`, or one that holds no `events.jsonl`, the newest non-dream run under
    `<docs>/.agents/runs` is used. Dream runs are excluded by name: reflecting on the last
    reflection is the degenerate case, and it is reachable simply by running dream twice.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    resolved = _resolve_run_dir(run_dir, docs_root)
    if resolved is None or not (resolved / "events.jsonl").is_file():
        logger.warning("no run with events.jsonl found under %s", docs_root)
        return RunEvidence(
            run_dir=str(resolved or ""),
            digest={"error": "no run with events.jsonl found", "run_dir": str(resolved or "")},
        )

    events = _load_events(resolved)

    enters: dict[str, int] = {}
    order: list[str] = []
    open_enter: dict[str, datetime | None] = {}
    durations: list[tuple[str, float]] = []
    all_ts: list[datetime] = []
    for event in events:
        scope = event.get("_scope", "")
        key = f"{scope}/{event.get('node')}" if scope else event.get("node")
        ts = _parse_ts(event.get("ts", ""))
        if ts:
            all_ts.append(ts)
        if event.get("phase") == "enter":
            enters[key] = enters.get(key, 0) + 1
            order.append(key)
            open_enter[key] = ts
        elif event.get("phase") == "done":
            started = open_enter.get(key)
            if started and ts:
                durations.append((key, (ts - started).total_seconds()))

    loops = sorted(
        [{"node": node, "entered": count} for node, count in enters.items() if count > 1],
        key=lambda row: -row["entered"],
    )
    slow_nodes = [
        {"node": node, "seconds": round(seconds)}
        for node, seconds in sorted(durations, key=lambda pair: -pair[1])[:SLOW_NODES]
    ]
    wall = round((max(all_ts) - min(all_ts)).total_seconds()) if len(all_ts) >= 2 else 0

    digest = {
        "run_dir": str(resolved),
        "run_id": resolved.name,
        "total_node_visits": len(order),
        "wall_time_seconds": wall,
        # The core signals reflection needs but final artifacts hide:
        "loops": loops,                 # entered >1 → which pair spun, and how many times
        "slow_nodes": slow_nodes,       # longest enter→done → stalls and cost hot-spots
        "path_tail": order[-PATH_TAIL:],  # how it actually flowed, most recent last
        "sessions": _sessions(resolved),  # scope → session id, for a transcript deep-dive
        "hint": ("Read events.jsonl and the per-node prompt.md/output.json under run_dir "
                 "for detail; .session_id points at the full opencode transcript in its store."),
    }
    logger.info("digested run %s: %d node visits, %d loop(s), wall=%ds",
                resolved.name, len(order), len(loops), wall)
    return RunEvidence(run_dir=str(resolved), digest=digest)


def _auto_run_dir(docs_root: Path) -> Path | None:
    """The newest run that is not itself a dream run — reflecting on a reflection is noise."""
    runs = docs_root / ".agents" / "runs"
    if not runs.is_dir():
        return None
    candidates = [p.parent for p in runs.glob("*/events.jsonl") if "dream" not in p.parent.name]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p / "events.jsonl").stat().st_mtime)


def _resolve_run_dir(arg: str, docs_root: Path) -> Path | None:
    """An explicit run dir if it is really one, else the newest.

    A relative argument resolves against the repo root rather than the process's cwd, and
    an argument pointing at something with no `events.jsonl` falls back rather than
    failing: it is a mistyped path, and the useful run is one directory over.
    """
    if arg:
        given = Path(arg)
        candidate = given if given.is_absolute() else (docs_root / given)
        if (candidate / "events.jsonl").is_file():
            return candidate.resolve()
    return _auto_run_dir(docs_root)


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _load_events(run_dir: Path) -> list[dict]:
    """Every event from the top-level log and each nested `_flow` sub-run, scope-tagged.

    A malformed line is skipped rather than fatal. This reads a *completed* run's log,
    which may have been truncated by a kill, and losing the whole digest to one bad tail
    line would be the wrong trade.
    """
    events: list[dict] = []
    for ev_file in sorted(run_dir.rglob("events.jsonl")):
        scope = "" if ev_file.parent == run_dir else str(ev_file.parent.relative_to(run_dir))
        for raw in ev_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            event["_scope"] = scope
            events.append(event)
    return events


def _sessions(run_dir: Path) -> dict[str, str]:
    sessions: dict[str, str] = {}
    for sid_file in run_dir.rglob(".session_id"):
        try:
            sessions[str(sid_file.parent.relative_to(run_dir))] = (
                sid_file.read_text(encoding="utf-8").strip()
            )
        except OSError:
            continue
    return sessions


@blueprint.node
def record_improvements(
    logger: logging.Logger, docs_path: str = "", run_dir: str = "", repo_dir: str = ""
) -> ImprovementsRecorded:
    """Drain the reflection inbox into the durable ledger, deduping and counting.

    The reflection turn writes its proposals to `docs/.dream-improvements.inbox.json`;
    this merges them into `docs/workflow-improvements.json` and re-renders the human-facing
    `docs/workflow-improvements.md` beside it. Dedup is by `(layer, title)`, case- and
    whitespace-normalised, and a repeat bumps `observed` and appends the run id.

    Both files are written, because they have different readers: the JSON is what the next
    run merges into, and the Markdown is what a person reviews. Re-rendering the Markdown
    from the JSON every time means the two cannot drift.

    The inbox is deleted afterwards so the next dream run starts clean; a leftover inbox
    would re-bump every proposal in it on the following run and manufacture evidence of
    recurrence that never happened.
    """
    root = find_docs_root(docs_path, repo_dir)
    run_id = Path(run_dir).name if run_dir else "unknown-run"
    ledger_md = f"{DREAM_LEDGER}.md"
    inbox_path = root / DREAM_INBOX

    if not inbox_path.is_file():
        logger.info("no inbox at %s — nothing to record", inbox_path)
        return ImprovementsRecorded(ledger=ledger_md, note="no inbox — nothing to record")
    try:
        proposals = json.loads(inbox_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("unreadable inbox %s: %s", inbox_path, exc)
        return ImprovementsRecorded(ledger=ledger_md, note=f"unreadable inbox ({exc})")

    # The prompt asks for a list; a model that wraps it in {"proposals": [...]} is answering
    # the same question, and rejecting that shape would lose a whole reflection turn.
    if isinstance(proposals, dict):
        proposals = proposals.get("proposals", [])
    if not isinstance(proposals, list):
        proposals = []

    ledger_path = root / f"{DREAM_LEDGER}.json"
    ledger: list[dict] = []
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8")) or []
        except (ValueError, OSError):
            ledger = []
    index = {_key(row.get("layer", ""), row.get("title", "")): row for row in ledger}

    added = bumped = 0
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        layer = str(proposal.get("layer", "")).strip().lower()
        title = str(proposal.get("title", "")).strip()
        if not title:
            continue
        if layer not in VALID_LAYERS:
            layer = "infra"  # keep it in the ledger under a safe default rather than drop
        existing = index.get(_key(layer, title))
        if existing:
            existing["observed"] = int(existing.get("observed", 1)) + 1
            runs = existing.setdefault("runs", [])
            if run_id not in runs:
                runs.append(run_id)
            # Keep the freshest detail/where if the new one is non-empty.
            if proposal.get("detail"):
                existing["detail"] = str(proposal["detail"]).strip()
            if proposal.get("where"):
                existing["where"] = str(proposal["where"]).strip()
            bumped += 1
        else:
            record = {
                "layer": layer,
                "title": title,
                "detail": str(proposal.get("detail", "")).strip(),
                "where": str(proposal.get("where", "")).strip(),
                "impact": str(proposal.get("impact", "")).strip(),
                "observed": 1,
                "runs": [run_id],
                "status": "open",
            }
            ledger.append(record)
            index[_key(layer, title)] = record
            added += 1

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    (root / ledger_md).write_text(_render_md(ledger), encoding="utf-8")
    try:
        inbox_path.unlink()
    except OSError:
        pass

    logger.info("recorded %d added, %d bumped (ledger total %d)", added, bumped, len(ledger))
    return ImprovementsRecorded(added=added, bumped=bumped, ledger=ledger_md, total=len(ledger))


def _key(layer: str, title: str) -> str:
    """The dedup key. Whitespace-collapsed and lowercased, because the same friction
    described twice by two runs differs in exactly those ways and in no other."""
    return layer.strip().lower() + "|" + " ".join(title.strip().lower().split())


def _render_md(ledger: list[dict]) -> str:
    """The reviewer's view: open items first, then most-observed first.

    That ordering is the point of the ledger — recurring friction rises to the top on its
    own, without anyone having to remember that they saw it last week too.
    """
    rows = sorted(ledger,
                  key=lambda row: (row.get("status") == "done", -int(row.get("observed", 1))))
    out = ["# Workflow self-improvement ledger",
           "",
           "Proposals from the `dream` flow (offline reflection over run transcripts).",
           "Deduped across runs; `observed` counts how many runs surfaced the same friction.",
           "A human reviews and applies — the dream flow never self-mutates the workflow.",
           ""]
    for row in rows:
        box = "x" if row.get("status") == "done" else " "
        out.append(f"- [{box}] **[{row.get('layer', '?')}]** {row.get('title', '').strip()} "
                   f"(observed ×{row.get('observed', 1)})")
        if row.get("detail"):
            out.append(f"  - {row['detail'].strip()}")
        if row.get("where"):
            out.append(f"  - Where: `{row['where'].strip()}`")
        if row.get("runs"):
            out.append(f"  - Runs: {', '.join(row['runs'][-5:])}")
    out.append("")
    return "\n".join(out)


__all__ = ["gather_run_evidence", "record_improvements"]
