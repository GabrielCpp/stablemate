from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    # Per-node wall-clock budget (seconds) for the agent's turn. Defaults to 1200s
    # (20 min) — research/implementation nodes routinely run a benchmark that
    # exceeds the old 600s ceiling. Set explicitly per node to widen or tighten it;
    # an explicit None/0 falls back to the engine default (AGENT_RESULT_TIMEOUT_S).
    # The effective value is surfaced to the prompt as `node_timeout_s` /
    # `node_timeout_min`, so the agent can size its work to fit the budget.
    timeout: float | None = 1200
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
