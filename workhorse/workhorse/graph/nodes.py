from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OutputSpec(BaseModel):
    key: str
    # Value emitted for this key when the node exhausts all retries/reframes and
    # the runner falls back to "default to next node" (see runner/agent.py). The
    # safe fallback is workflow-specific, so it's declared here by the workflow
    # author rather than guessed by the generic runner. Unset → None.
    default: Any = None


class AgentNode(BaseModel):
    type: Literal["agent"]
    id: str
    prompt: str
    args: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputSpec] = Field(default_factory=list)
    # Model for this node, interpreted by the active CLI backend.
    #   str  → an absolute default applied to every backend (e.g. "opus" / "haiku"
    #          for Claude). Existing behaviour.
    #   dict → keyed selection by CLI name ("claude"/"codex"/"copilot"/"aider"/
    #          "opencode", plus an optional "default"): e.g.
    #          {claude: opus, codex: "@gpt-5.5", aider: openrouter/xiaomi/mimo-v2.5}.
    #          The active backend (AGENT_CLI / --cli) picks its key; an unlisted
    #          backend with no "default" falls through to AGENT_MODEL / the backend's
    #          own default. To run a node on an OpenRouter model, drive the run with
    #          an OpenRouter-native backend (aider/opencode) and give it an
    #          "openrouter/<slug>" value here. See runner/agent.py (_resolve_model /
    #          _model_for_backend).
    # When unset, the backend's own default applies — workflows need not hard-code a
    # Claude alias.
    model: str | dict[str, str] | None = None
    # Reasoning/thinking effort for this node's turn. "high" is worth it for the
    # hardest decision/authoring nodes (e.g. resolving an operator block). Every
    # backend uses its native knob: Claude and Copilot → `--effort <level>`; Codex →
    # `-c model_reasoning_effort=<level>` (clamped to its max of "high"); aider →
    # `--reasoning-effort` (clamped to "high"); opencode → `--variant`. Levels follow
    # the Claude/Copilot CLIs (low|medium|high|xhigh|max); unset → backend default
    # (use unset for non-reasoning models like MiMo). See runner/backends.py.
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
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
    # it needs to read/write files in another.
    add_dirs: list[str] = Field(default_factory=list)
    next: str | None = None


class ScriptNode(BaseModel):
    type: Literal["script"]
    id: str
    script: str
    args: list[str] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    # Per-node working directory (Jinja2-rendered). Sets the subprocess CWD for
    # the script. When empty/None, defaults to the workflow directory.
    cwd: str | None = None
    # Gas-tank refuel marker (infinite-loop guard). When set to a context dotpath,
    # reaching this node REFILLS the run's gas tank whenever the value at that path
    # has changed since the last visit — i.e. real forward progress was made. The
    # engine burns one unit of gas per node step and halts when the tank empties, so
    # a healthy run tops up at each progress point and never runs dry, while a loop
    # that reprocesses the SAME unit forever burns one tank and stops. The coder
    # workflow refuels on a new story (`story_slug`) and a new epic (`epic`). See
    # main.py `_GasTank`.
    refuel: str | None = None
    next: str | None = None


class FlowNode(BaseModel):
    """Call a named sub-graph (a ``flows:`` entry) like a function: render ``args``
    into a fresh child context, run the flow to its terminal, pull the declared
    ``outputs`` back into the parent context, then advance to ``next``. Mirrors
    AgentNode/ScriptNode's args/outputs/next shape so it composes the same way."""
    type: Literal["flow"]
    id: str
    # Which flow (key in the containing graph's `flows:` map) to invoke.
    name: str
    # Jinja2 templates rendered against the PARENT context; the rendered values are
    # the ONLY things that cross into the child context (alongside the flow's own
    # vars), so the boundary is explicit and parent state can't silently leak in.
    args: dict[str, str] = Field(default_factory=dict)
    # Keys to lift OUT of the child's terminal context back into the parent.
    outputs: list[OutputSpec] = Field(default_factory=list)
    next: str | None = None


class BranchCondition(BaseModel):
    op: Literal["==", "!=", "<", ">", "<=", ">="]
    value: str
    next: str


class BranchNode(BaseModel):
    type: Literal["branch"]
    id: str
    # Named 'path' because 'on' is a YAML 1.1 boolean keyword
    path: str
    cases: dict[str, str] = Field(default_factory=dict)
    conditions: list[BranchCondition] = Field(default_factory=list)
    default: str | None = None


class TerminalNode(BaseModel):
    type: Literal["terminal", "fail"]
    id: str


Node = Annotated[
    AgentNode | ScriptNode | BranchNode | FlowNode | TerminalNode,
    Field(discriminator="type"),
]


class Graph(BaseModel):
    name: str
    start: str
    vars: dict[str, Any] = Field(default_factory=dict)
    nodes: dict[str, Node]
    # Named sub-graphs callable via a FlowNode, or runnable standalone
    # (`workhorse run <workflow> <flow>`). Each value is itself a Graph, so flows
    # self-validate and may (within the depth backstop) nest.
    flows: dict[str, Graph] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_edges(self) -> Graph:
        if self.start not in self.nodes:
            raise ValueError(f"start node '{self.start}' not found")

        for node in self.nodes.values():
            refs: list[str] = []
            if isinstance(node, (AgentNode, ScriptNode)) and node.next:
                refs.append(node.next)
            elif isinstance(node, FlowNode):
                if node.next:
                    refs.append(node.next)
                # The flow itself must resolve in THIS graph's `flows:` map (lexical
                # scope); the sub-graph it names self-validates as its own Graph.
                if node.name not in self.flows:
                    raise ValueError(
                        f"flow node '{node.id}' references unknown flow '{node.name}'"
                    )
            elif isinstance(node, BranchNode):
                refs.extend(node.cases.values())
                refs.extend(c.next for c in node.conditions)
                if node.default:
                    refs.append(node.default)

            for ref in refs:
                if ref not in self.nodes:
                    raise ValueError(
                        f"node '{node.id}' references unknown node '{ref}'"
                    )

        return self
