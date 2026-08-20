"""Time the coder's `dev` lane on one story, turn by turn.

`bench.py` answers *how good is the output*. This answers the other half — *what did
getting there cost* — at the resolution the optimization work needs: one row per agent
turn, with its power tier, its tokens, its tool calls and its seconds.

The two commands are deliberately separate. `run` resets a benchmark repo to a commit
where the story is still unbuilt and drives the lane over it; `table` reads the
telemetry afterwards and prints markdown. Keeping them apart is what makes a
re-measurement comparable: the same `--at` and `--story` reproduce the same starting
tree months later, and a table can be re-derived from a run nobody kept the console
output of.

    uv run python benchmarks/devlane.py run   --repo /tmp/bench-expense-split \
        --at 93d8234 --story expense-list --run-id baseline
    uv run python benchmarks/devlane.py table --repo /tmp/bench-expense-split \
        --run-id baseline

**The briefing column is the point of the exercise.** A turn's prompt is a few thousand
tokens against a context the agent then grows by two orders of magnitude reading the
repo, so the share the briefing occupies is the measurement that decides whether
shortening prompts can be claimed as a latency win at all. It is reported per turn and
in the summary, and it is reported as a *share of tokens* rather than of seconds
because no backend records time-to-first-token — an honest proxy, named as one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ostler import markdown

#: Rough characters-per-token for English prose and markdown. Only ever used for the
#: briefing column, where the question is "single-digit percent or not" and a tokenizer
#: that matched the backend's exactly would not change the answer.
CHARS_PER_TOKEN = 4

#: Prompt stems whose turn is a repair rather than a step forward. The lane's happy path
#: is every other turn; a lap is any turn on one of these plus any *repeat* of a node
#: that already ran, since the second `implement-plan` in a run is rework by definition.
REPAIR_NODES = frozenset(
    {"dev-fix", "fix-verify", "refine-plan", "rework-story", "resolve-operator"}
)


@dataclass(frozen=True)
class Turn:
    """One `agent_turn` span, joined to the tool calls its transcript records."""

    seq: int
    node: str
    model: str
    power: str
    seconds: float
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: float
    tool_calls: int
    briefing_tokens: int

    @property
    def is_repair(self) -> bool:
        return self.node in REPAIR_NODES

    @property
    def briefing_share(self) -> float:
        """The briefing as a fraction of everything the model read for this turn.

        The denominator is every input token — fresh, cache-written and cache-read alike
        — because all three are context the turn had to be handed, and the cache is an
        accounting detail of who paid for it rather than of how much there was.
        """
        total = self.input_tokens + self.cached_tokens
        return self.briefing_tokens / total if total else 0.0


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def reset(repo: Path, at: str, run_dir: Path) -> None:
    """Put the benchmark repo back to `at`, with no trace of a previous measurement.

    `git clean` runs without `-x`: the ignored half of the tree is farrier's install
    (`.agents/skills`, the context manifest), which the lane needs and which reinstalling
    on every measurement would only add variance to. The run directory is removed by
    name for the same reason — a stale checkpoint would be resumed rather than replaced.
    """
    _git(repo, "reset", "--hard", at)
    _git(repo, "clean", "-fd")
    subprocess.run(["rm", "-rf", str(run_dir)], check=True)


def launch(repo: Path, story: str, run_id: str, flow: str, log: Path) -> int:
    """Drive the lane over the prepared tree, streaming its console output to `log`."""
    params = json.dumps({"story": story, "operator_mode": "auto"})
    with log.open("w", encoding="utf-8") as sink:
        return subprocess.run(
            ["workhorse-coder", "run", flow, "--params", params, "--run-id", run_id],
            cwd=repo,
            stdout=sink,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode


def _tool_calls(transcript: Path) -> int:
    """How many tool calls one turn's transcript records.

    Counted off `tool_use` blocks rather than off the span, which carries no such
    number: a turn's cost is mostly what it read, and the read count is the only
    available handle on why one node takes eight minutes and another forty seconds.
    """
    calls = 0
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (record.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        calls += sum(
            1
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        )
    return calls


def _transcripts(run_dir: Path) -> list[tuple[str, str, Path]]:
    """Every transcript in the run, in turn order, as `(stem, session, path)`.

    Keyed by the *turn* rather than by the session, which is the whole subtlety here: a
    lane opens one session and sends several turns into it, and each turn's transcript is
    the conversation **so far**, not that turn's slice of it. Keying by session id would
    hand all three of a story's turns the last one's file — and, with it, the last one's
    cumulative tool count.
    """
    found: list[tuple[str, str, Path]] = []
    for path in sorted((run_dir / "transcripts").glob("*.jsonl")):
        stem, _, session = path.stem.partition("__")
        found.append((stem, session, path))
    return found


def _briefing_tokens(run_dir: Path, stem: str) -> int:
    """The size of the prompt this turn was handed, in tokens.

    Read from the turn's own directory rather than the node's, because the node
    directory holds only the *last* render — a node that ran three times overwrote its
    first two briefings there, and a repair lap's prompt is exactly what this column
    exists to compare against the turn it repairs.
    """
    prompt = run_dir / "turns" / stem / "prompt.md"
    if not prompt.exists():
        return 0
    return len(prompt.read_text(encoding="utf-8")) // CHARS_PER_TOKEN


def collect(repo: Path, run_id: str) -> list[Turn]:
    """Every agent turn of the run, in order, joined across telemetry and run dir."""
    from groom import store  # noqa: PLC0415 - a heavy import only the reader needs

    run_dir = repo / ".agents" / "runs" / f"coder-{run_id}"
    transcripts = _transcripts(run_dir)
    rows = store._connection().execute(  # noqa: SLF001 - no public per-span reader
        "SELECT node, start_ts, end_ts, attrs_json FROM spans"
        " WHERE run_id = ? AND name = 'agent_turn' ORDER BY start_ts",
        (run_id,),
    ).fetchall()
    # Both sequences are the run's turns in order, so they are joined positionally: the
    # spans carry no transcript name and the transcripts carry no timing.
    seen: dict[str, int] = {}
    turns: list[Turn] = []
    for seq, row in enumerate(rows, start=1):
        attrs = json.loads(row["attrs_json"] or "{}")
        stem, session, transcript = (
            transcripts[seq - 1] if seq <= len(transcripts) else ("", "", None)
        )
        # The transcript is cumulative, so this turn's tool calls are what it added to
        # its session — a resumed conversation would otherwise be charged again for
        # every call the turns before it made.
        cumulative = _tool_calls(transcript) if transcript else 0
        tool_calls = cumulative - seen.get(session, 0)
        seen[session] = cumulative
        turns.append(
            Turn(
                seq=seq,
                node=row["node"] or attrs.get("workhorse.node", "?"),
                model=attrs.get("model", ""),
                power=attrs.get("effort", ""),
                seconds=row["end_ts"] - row["start_ts"],
                input_tokens=int(attrs.get("usage.input_tokens", 0))
                + int(attrs.get("usage.cache_creation_input_tokens", 0)),
                output_tokens=int(attrs.get("usage.output_tokens", 0)),
                cached_tokens=int(attrs.get("usage.cache_read_input_tokens", 0)),
                cost_usd=float(attrs.get("total_cost_usd", 0.0)),
                tool_calls=tool_calls,
                briefing_tokens=_briefing_tokens(run_dir, stem),
            )
        )
    return turns


#: How the fix envelope labels the two facts a lap is identified by. Read off the rendered
#: prompt rather than off a span because the gate's verdict is nowhere in telemetry, and
#: the prompt is the one artifact that is *by construction* what the turn was told.
GATE_LABEL = "gate"
LAP_LABEL = "repair attempt"

#: Inline formatting around a bullet's value — `**Gate:** \`lint\`` leaves the closing
#: emphasis on the value side of the colon, and it is decoration, not part of the answer.
DECORATION = "*_` "


def envelope(text: str) -> tuple[str, int]:
    """The gate and the lap a rendered `dev-fix` prompt was written for.

    Parsed rather than matched, because the envelope is followed by the gate's own output
    inside a fence — and a lint failure quoting a line of markdown is not this prompt's
    header, however much it looks like one on a line-oriented read.
    """
    gate, lap = "?", 0
    seen_gate = seen_lap = False
    for bullet in markdown.split(text).walk_bullets():
        if bullet.label == GATE_LABEL and not seen_gate:
            spans = markdown.all_code_spans(bullet.text)
            gate = spans[0] if spans else bullet.value.strip(DECORATION)
            seen_gate = True
        elif bullet.label == LAP_LABEL and not seen_lap:
            value = bullet.value.strip(DECORATION)
            lap = int(value) if value.isdigit() else 0
            seen_lap = True
    return gate, lap


@dataclass(frozen=True)
class Lap:
    """One repair turn, and whether the gate it was sent at went green afterwards."""

    seq: int
    source: str
    lap: int
    closed: bool


def laps(repo: Path, run_id: str) -> list[Lap]:
    """Every `dev-fix` turn of the run, by gate, with the verdict the *gate* gave next.

    A lap closed its gate when no later lap was sent at the same source. That is the only
    honest reading available: `FixResult.status` is the agent's own claim, and the flow
    deliberately does not branch on it — re-running the gate is what decides. So the
    measurement asks the same question the flow does, and answers it from the sequence.

    The gate re-runs *in order* after every lap, so a second `lint` lap after a `test` lap
    means lint came back; sources are therefore counted independently rather than by
    adjacency.
    """
    run_dir = repo / ".agents" / "runs" / f"coder-{run_id}"
    found: list[Lap] = []
    for seq, path in enumerate(sorted((run_dir / "turns").glob("*-dev-fix")), start=1):
        prompt = path / "prompt.md"
        if not prompt.exists():
            continue
        gate, lap = envelope(prompt.read_text(encoding="utf-8", errors="replace"))
        found.append(Lap(seq=seq, source=gate, lap=lap, closed=True))
    last = {lap.source: lap.seq for lap in found}
    return [
        Lap(lap.seq, lap.source, lap.lap, closed=last[lap.source] == lap.seq)
        for lap in found
    ]


def render_laps(all_laps: dict[str, list[Lap]]) -> str:
    """The fix-lap success rate, per `FailureReport.source`, across the runs given.

    Per source and never averaged, because the row this fills exists to catch one source
    getting worse while the mean stays flat — a cheaper lap that fails more often is a cost
    moved to the operator gate, not an optimisation.
    """
    by_source: dict[str, list[Lap]] = {}
    for run_laps in all_laps.values():
        for lap in run_laps:
            by_source.setdefault(lap.source, []).append(lap)
    lines = [
        "| source | laps | closed the gate | rate |",
        "| ------ | ---: | --------------: | ---: |",
    ]
    for source in sorted(by_source):
        got = by_source[source]
        closed = sum(1 for lap in got if lap.closed)
        lines.append(
            f"| `{source}` | {len(got)} | {closed} | {closed / len(got) * 100:.0f}% |"
        )
    if not by_source:
        lines.append("| *(no repair laps in these runs)* | 0 | 0 | n/a |")
    detail = [
        f"- `{run_id}`: "
        + (
            ", ".join(f"{lap.source}#{lap.lap} {'closed' if lap.closed else 'came back'}"
                      for lap in run_laps)
            or "no repair laps"
        )
        for run_id, run_laps in all_laps.items()
    ]
    return "\n".join(lines + [""] + detail)


def render(turns: list[Turn], run_id: str, story: str, head: str) -> str:
    """The measurement as markdown: one table of turns, then the per-story summary."""
    lines = [
        f"Run `{run_id}` — story `{story}`, from `{head}`.",
        "",
        "| # | node | power | s | in | cached | out | tools | briefing | share |",
        "| - | ---- | ----- | -: | -: | -----: | --: | ----: | -------: | ----: |",
    ]
    for turn in turns:
        mark = " ↻" if turn.is_repair else ""
        lines.append(
            f"| {turn.seq} | `{turn.node}`{mark} | {turn.power} | {turn.seconds:.0f} |"
            f" {turn.input_tokens:,} | {turn.cached_tokens:,} | {turn.output_tokens:,} |"
            f" {turn.tool_calls} | {turn.briefing_tokens:,} |"
            f" {turn.briefing_share * 100:.2f}% |"
        )
    total_s = sum(turn.seconds for turn in turns)
    repairs = [turn for turn in turns if turn.is_repair]
    high = [turn for turn in turns if turn.power == "high"]
    briefing = sum(turn.briefing_tokens for turn in turns)
    read = sum(turn.input_tokens + turn.cached_tokens for turn in turns)
    by_node = Counter(turn.node for turn in turns)
    lines += [
        "",
        f"- **Turns:** {len(turns)} ({len(turns) - len(repairs)} happy path,"
        f" {len(repairs)} repair)",
        f"- **High-power turns:** {len(high)}",
        f"- **Wall clock:** {total_s / 60:.1f} min across turns",
        f"- **Cost:** ${sum(turn.cost_usd for turn in turns):.2f}",
        f"- **Briefing share of everything read:** {briefing / read * 100:.2f}%"
        f" ({briefing:,} of {read:,} tokens)" if read else "- **Briefing share:** n/a",
        "- **Turns per node:** "
        + ", ".join(f"`{node}`×{count}" for node, count in by_node.most_common()),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    runner = sub.add_parser("run", help="Reset the repo and drive the lane over it")
    runner.add_argument("--repo", type=Path, required=True)
    runner.add_argument("--at", required=True, help="Commit to reset the repo to")
    runner.add_argument("--story", required=True)
    runner.add_argument("--run-id", required=True)
    runner.add_argument("--flow", default="dev")

    reader = sub.add_parser("table", help="Print the turn table for a finished run")
    reader.add_argument("--repo", type=Path, required=True)
    reader.add_argument("--run-id", required=True)
    reader.add_argument("--story", default="")

    lapper = sub.add_parser("laps", help="Fix-lap success rate, per failure source")
    lapper.add_argument("--repo", type=Path, required=True)
    lapper.add_argument("--run-id", required=True, action="append", dest="run_ids")

    args = parser.parse_args(argv)
    if args.command == "laps":
        repo = args.repo.resolve()
        print(render_laps({run_id: laps(repo, run_id) for run_id in args.run_ids}))
        return 0

    repo = args.repo.resolve()
    run_dir = repo / ".agents" / "runs" / f"coder-{args.run_id}"

    if args.command == "run":
        reset(repo, args.at, run_dir)
        log = repo / f".agents/devlane-{args.run_id}.log"
        print(f"repo at {_git(repo, 'rev-parse', '--short', 'HEAD')}; log {log}")
        return launch(repo, args.story, args.run_id, args.flow, log)

    turns = collect(repo, args.run_id)
    if not turns:
        print(f"no agent turns recorded for run {args.run_id}", file=sys.stderr)
        return 1
    head = _git(repo, "rev-parse", "--short", "HEAD")
    print(render(turns, args.run_id, args.story, head))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
