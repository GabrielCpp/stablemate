"""What the agent runner is handed: one turn's prompt, its arguments, and the
outputs it is expected to produce.

This is the runner's own input contract, not a workflow-format type — both
front-ends build one. The YAML loader validates a node's mapping into it; the
Python driver constructs one per ``self.agent`` call from the state's arguments.
Keeping it beside :mod:`workhorse.runner.ladder` is what lets the driver call the
runner without importing a graph.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class OutputSpec(BaseModel):
    # A key the node asks for. There is no companion `default` here on purpose:
    # a node that never answered has no answer to fall back to, and the ladder stops
    # the run rather than emitting one (see runner/ladder.py).
    key: str
    # Whether its absence is a failure. A key can be genuinely inapplicable rather than
    # missing — a field that means something only in one branch of the answer, like "why
    # there is no test" from a turn that wrote tests. Demanding it anyway costs a full
    # extra turn to be told a field does not apply, and a benchmark run paid exactly that
    # on its happy path. Optional keys are still *declared*, so the object carrying them
    # is still found and a reframe can still name them; only the presence check is
    # relaxed. Whether a key is required is the result model's own statement about
    # itself, never a guess here — see `pyflow/engine.py::_outputs_for`.
    required: bool = True


class AgentNode(BaseModel):
    type: Literal["agent"]
    id: str
    prompt: str
    args: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputSpec] = Field(default_factory=list)
    # Abstract capacity tier for this node. Deliberately an **opaque string**, not a
    # closed enum: the tier names are the operator's vocabulary, defined by whatever
    # `[power.<level>.<backend>]` tables their config declares. A workflow that wants a
    # rung this repo never thought of ("cheap-bulk", "verdict") writes it here and the
    # operator maps it; nothing in the engine needs to learn the name.
    #
    # The names the shipped workflows use, cheapest → most capable, are `low` / `medium`
    # / `high` / `smart` / `extra-smart` — a convention, not a constraint. `smart` and
    # `extra-smart` sit above `high` because "the strongest model available" stopped
    # being one rung: *frontier reasoning* and *the premium model, spend accordingly*
    # are different decisions, and a node wanting the first should not silently get
    # billed for the second.
    #
    # A tier no backend table maps falls through to `[default.<backend>]`, so an unknown
    # (or misspelled) tier degrades to that backend's default rather than failing the
    # run. See workhorse/config.py and runner/ladder.py.
    power: str | None = None
    # Per-node wall-clock budget (seconds) for the agent's turn. Defaults to 3600s
    # (1 hour) — research/implementation nodes routinely run a benchmark that
    # exceeds the old 600s ceiling. Set explicitly per node to widen or tighten it
    # (e.g. `timeout: 5000`); an explicit None/0 falls back to the engine default
    # (AGENT_RESULT_TIMEOUT_S). Set `timeout: infinity` (also "inf"/"unbounded"/
    # "never", or YAML `.inf`) for **no wall-clock limit** — the turn runs until the
    # CLI returns, for open-ended nodes that must not be cut off (e.g. resolving an
    # operator block). WARNING: an unbounded node that wedges hangs the run with no
    # timeout-retry recovery; prefer a large finite value unless you truly want this.
    # The effective value is surfaced to the prompt as `node_timeout_s` /
    # `node_timeout_min` ("unbounded" when infinite), so the agent can size its work.
    timeout: float | None = 3600
    # Per-node reframe budget: how many times a failed turn is re-asked from scratch in
    # a fresh session before the ladder gives up on this node. None (the default) means
    # the run's `resilience.max_rephrase_attempts`.
    #
    # Set it to 0 for a node whose **deliverable is a file rather than the turn's reply**
    # and whose caller can act on a partial one. A reframe discards the session and
    # re-asks at full price, which for such a node buys nothing the caller could not get
    # more cheaply by reading what is already on disk — and under a tight per-node
    # `timeout` it multiplies that budget by the number of reframes before the run stops.
    # Only the caller knows whether a partial artifact is worth something, so this is a
    # per-node decision, not a run-level one.
    retries: int | None = None

    @field_validator("timeout", mode="before")
    @classmethod
    def _coerce_timeout(cls, v: Any) -> Any:
        """Accept seconds as a number, or a word for 'no limit'. ``infinity`` / ``inf``
        / ``infinite`` / ``unbounded`` / ``never`` (case-insensitive) → ``float('inf')``
        (unbounded). A numeric string (``"5000"``) parses as seconds. None/0 are left
        as-is (they mean 'use the engine default')."""
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"infinity", "inf", "infinite", "unbounded", "never"}:
                return float("inf")
            return float(s)
        return v

    # Per-node working directory (Jinja2-rendered from workflow context). Sets the
    # subprocess CWD for the agent CLI, controlling CLAUDE.md/skills discovery and
    # git context. When empty/None, inherits the process CWD (existing behavior).
    cwd: str | None = None
    # Additional directories to grant the agent access to (rendered as --add-dir
    # flags). Used for multi-repo workflows where the agent's CWD is one repo but
    # it needs to read/write files in another. Accepts either a list of Jinja2
    # template strings or a single template string that resolves to a list value
    # in the workflow context (e.g. `"{{ affected_repo_paths }}"` where the context
    # value is a list).
    add_dirs: list[str] | str = Field(default_factory=list)
    # Human-readable "what this node is doing", Jinja2-rendered from context before
    # the node runs (e.g. "reviewing {{ story_slug }}"). Stamped live on telemetry as
    # `wf.activity` so a monitor can show the run's current activity without knowing
    # the workflow's vocabulary. Empty render → dropped. See main.py's label render.
    activity: str | None = None
    next: str | None = None


__all__ = ["AgentNode", "OutputSpec"]
