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
    #   dict → per-CLI selection keyed by backend name ("claude"/"codex"/"copilot"),
    #          e.g. {claude: opus, codex: "@gpt-5.5"}. An optional "default" key
    #          covers any backend not listed; a backend that is neither listed nor
    #          has a "default" falls through to AGENT_MODEL / the backend's own
    #          default (see runner/agent.py:_model_for_backend and runner/backends.py).
    # When unset, the backend's own default applies — workflows need not hard-code a
    # Claude alias.
    model: str | dict[str, str] | None = None
    # Reasoning/thinking effort for this node's turn. "high" is worth it for the
    # hardest decision/authoring nodes (e.g. resolving an operator block). Every
    # backend uses its native knob: Claude and Copilot → `--effort <level>`; Codex →
    # `-c model_reasoning_effort=<level>` (clamped to its max of "high"). Levels follow
    # the Claude/Copilot CLIs (low|medium|high|xhigh|max); unset → backend default.
    # See runner/backends.py.
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
    AgentNode | ScriptNode | BranchNode | TerminalNode,
    Field(discriminator="type"),
]


class Graph(BaseModel):
    name: str
    start: str
    vars: dict[str, Any] = Field(default_factory=dict)
    nodes: dict[str, Node]

    @model_validator(mode="after")
    def _validate_edges(self) -> Graph:
        if self.start not in self.nodes:
            raise ValueError(f"start node '{self.start}' not found")

        for node in self.nodes.values():
            refs: list[str] = []
            if isinstance(node, (AgentNode, ScriptNode)) and node.next:
                refs.append(node.next)
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
