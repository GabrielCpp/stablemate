from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from workhorse.requirements import Requirement


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
    # Abstract capacity tier for this node. The active backend maps this through the
    # user-wide workhorse config (`power.<level>.<backend>`) to concrete model/effort.
    # Missing config deliberately leaves model/effort unset so the backend's default
    # behavior applies. See workhorse/config.py and runner/agent.py.
    power: Literal["low", "medium", "high"] | None = None
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
    # it needs to read/write files in another. Accepts either a list of Jinja2
    # template strings or a single template string that resolves to a list value
    # in the workflow context (e.g. `"{{ affected_repo_paths }}"` where the context
    # value is a list).
    add_dirs: list[str] | str = Field(default_factory=list)
    next: str | None = None


class ScriptNode(BaseModel):
    type: Literal["script"]
    id: str
    script: str
    args: list[str] = Field(default_factory=list)

    @field_validator("script")
    @classmethod
    def _reject_shell_scripts(cls, v: str) -> str:
        """Only Python script nodes are supported. Shell scripts can't be run
        in-process (which is how the test harness intercepts scriptutil calls),
        so a workflow must port them to a Python script using ``workhorse.scriptutil``.
        Enforced at load so a bad workflow fails before any run, not mid-run."""
        if v.lower().endswith((".sh", ".bash")):
            raise ValueError(
                f"script node points at a shell script ({v!r}); shell scripts are "
                "not supported — port it to a Python script (.py) using "
                "workhorse.scriptutil"
            )
        return v
    outputs: list[OutputSpec] = Field(default_factory=list)
    # Per-node working directory (Jinja2-rendered). Sets the subprocess CWD for
    # the script. When empty/None, defaults to the workflow directory.
    cwd: str | None = None
    # Extra environment variables injected into the script subprocess (values are
    # Jinja2-rendered from workflow context). Merged on top of the inherited
    # os.environ so scripts can receive workflow config without sys.argv or file
    # side-channels.  Example:
    #   env:
    #     CODER_WORKSPACE: "{{ workspace_file }}"
    env: dict[str, str] = Field(default_factory=dict)
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


class CallOutputSpec(OutputSpec):
    wrap: str | None = None


class CallNode(BaseModel):
    type: Literal["call"]
    id: str
    fn: str
    args: dict[str, str] = Field(default_factory=dict)
    outputs: list[CallOutputSpec] = Field(default_factory=list)
    refuel: str | None = None
    next: str | None = None


class TerminalNode(BaseModel):
    type: Literal["terminal", "fail"]
    id: str


Node = Annotated[
    AgentNode | ScriptNode | BranchNode | FlowNode | CallNode | TerminalNode,
    Field(discriminator="type"),
]


class Graph(BaseModel):
    name: str
    start: str
    vars: dict[str, Any] = Field(default_factory=dict)
    # Workflow-level environment variables injected into every ScriptNode subprocess
    # (values are Jinja2-rendered from workflow context). Per-node env is merged on
    # top, so nodes can override individual keys. Example:
    #   env:
    #     CODER_WORKSPACE: "{{ workspace_file }}"
    env: dict[str, str] = Field(default_factory=dict)
    # Tools this workflow uses DIRECTLY, checked before the first node runs. Not a
    # transitive closure and not the target repo's toolchain: `make`/`go` belong to
    # whatever repo a workflow is pointed at, so they can't be declared here.
    #   requires:
    #     - dist: ostler          # importable by the script interpreter
    #       version: ">=0.1.0"
    #     - cmd: git              # on PATH
    #     - cmd: groom
    #       optional: true        # warn, never block
    requires: list[Requirement] = Field(default_factory=list)
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
            if isinstance(node, (AgentNode, ScriptNode, CallNode)) and node.next:
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
