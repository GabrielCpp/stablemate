"""Cline CLI (``cline --json``) — event vocabulary and adapter.

One of the two OpenRouter-native harnesses (opencode is the other), and the
best-instrumented backend here: it ends every turn with a single structured
``run_result`` carrying tokens, the cache split, real money, duration and the model
it actually used.

Event shapes below were captured from a live turn (CLI 3.0.50, 2026-08-05), not
inferred:

* ``{"type":"agent_event","event":{"type":"content_start"|"content_end",
  "contentType":"text"|"reasoning","text":…,"accumulated":…}}`` — the answer arrives
  as content parts; the ``run_result`` repeats the whole thing, so this adapter reads
  the terminal event and uses the parts only for the live echo.
* ``{"type":"agent_event","event":{"type":"usage","cost","inputTokens",…}}`` — emitted
  per *iteration*. Deliberately ignored: ``run_result.usage`` is already the turn's
  total, and folding both would double-count. (opencode is the opposite case — there
  the per-step events are the only report, so they must be summed.)
* ``{"type":"run_result","usage":{...},"durationMs":…,"text":…,"finishReason":…}`` —
  the terminal event, and the one that matters.
* ``{"type":"hook_event",...,"taskId":"conv_…"}`` — carries the id ``--id`` resumes.

`model.info.pricing` rides along inside ``run_result``, keyed ``input``/``output`` —
the same spelling opencode uses for its *counts*. That is a live trap for the usage
normalizer rather than a curiosity here; see ``runner/usage.py::_as_int``.
"""

from __future__ import annotations

import json
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import usage as _usage
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id

#: cline's own reasoning levels, which happen to be exactly workhorse's — so effort
#: passes through unmapped, unlike opencode's (which needs a variant name). A level
#: outside this set (``max``) is omitted rather than guessed at: cline rejects an
#: unknown value outright, which would cost the whole turn.
_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh"})


def _on_event(event, state: TurnState, node_id) -> None:
    """cline ``--json``: NDJSON, every line a ``{"type":…,"ts":…}`` envelope.

    The answer is taken from ``run_result.text`` rather than accumulated from the
    content parts: cline already assembled it, and re-deriving it here would be a
    second implementation of the same thing that could disagree with the first.
    """
    etype = event.get("type") or ""
    if etype == "hook_event":
        # The resume handle. It appears here rather than on run_result, so it is
        # captured whenever it shows up.
        if event.get("taskId"):
            state.session_id = event["taskId"]
        return
    if etype == "run_result":
        state.result_text = (event.get("text") or "").strip()
        state.usage = state.usage.merge(_usage.normalize(event))
        # `finishReason` is cline's own verdict on the turn. Anything but a clean
        # completion goes to diagnostics, where `classify_turn` decides whether it
        # is transient, an overflow, or fatal — this adapter does not classify.
        reason = event.get("finishReason") or ""
        if reason and reason != "completed":
            state.diagnostics.append(f"cline finishReason={reason}")
        return
    if etype == "agent_event":
        inner = event.get("event") or {}
        if inner.get("type") == "content_end" and inner.get("contentType") == "text":
            text = (inner.get("text") or "").strip()
            if text:
                print(f"[{node_id}] {text[:500]}", flush=True)
        return
    if "error" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


class ClineBackend(JsonlBackend):
    """Cline CLI (``cline --json``), selected with ``--cli cline``.

    Autonomous by construction: ``--auto-approve true`` answers every tool prompt, and
    headless mode is what ``--json`` already implies. Sessions resume by id via
    ``--id``. ``add_dirs`` has no cline equivalent — it works the tree at ``cwd`` — so
    a multi-repo node must be given a ``cwd`` that contains what it needs.

    Compaction is declined here even though cline has a ``--compaction`` flag: that
    flag configures cline's *own* automatic compaction for the turn, which is not the
    same capability as the ladder's "compact this session and retry the same prompt".
    Claiming support would send the recovery ladder down a path with nothing behind
    it. It is set to ``basic`` on every turn so cline manages its own context, and the
    ladder reframes rather than compacting.
    """

    name = "cline"
    #: No default: cline resolves its own model from the provider it was authenticated
    #: against, and naming one here would silently override that.
    default_model = None
    supports_compaction = False

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        sid = read_session_id(session_id_path)
        cmd = [
            "cline",
            "--json",
            "--auto-approve",
            "true",
            # cline manages its own context window; the ladder does not compact it.
            "--compaction",
            "basic",
        ]
        if model:
            cmd += ["--model", model]
        if effort in _EFFORTS:
            cmd += ["--thinking", effort]
        if cwd:
            cmd += ["--cwd", cwd]
        if sid:
            cmd += ["--id", sid]
            print(f"[{node_id}] 🔄 Resuming cline session: {sid[:8]}...", flush=True)
        # The prompt is a positional argument, and `--` ends option parsing so one
        # starting with '-' is still the message.
        cmd += ["--", prompt]
        state = self.stream(
            cmd, node_id, timeout, None, _on_event,
            resilience=resilience, cwd=cwd,
            env_extra=self.harness_env(),
        )
        return finalize_turn("cline", node_id, state, session_id_path, timeout)

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ):
        return False
