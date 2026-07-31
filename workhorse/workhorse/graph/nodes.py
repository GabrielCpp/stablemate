from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from workhorse.requirements import Requirement
# AgentNode/OutputSpec are the *runner's* contract, not the YAML format's — both
# front-ends build one — so they live beside the runner. Re-exported here because
# the YAML node union is still spelled in terms of them.
from workhorse.runner.spec import AgentNode, OutputSpec


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
    # See AgentNode.activity — a Jinja2 "what this node is doing" stamped as
    # `wf.activity` on telemetry.
    activity: str | None = None
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
    # See AgentNode.activity — a Jinja2 "what this node is doing" stamped as
    # `wf.activity` on telemetry.
    activity: str | None = None
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
    # See AgentNode.activity — a Jinja2 "what this node is doing" stamped as
    # `wf.activity` on telemetry.
    activity: str | None = None
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
    # Telemetry dimensions this workflow wants stamped on its spans. Values are
    # Jinja2-rendered from workflow context before every node, so they track what
    # the run is working on; keys land as span attributes prefixed `wf.`. This is
    # how a workflow's own unit of work reaches telemetry without workhorse ever
    # learning what one is — the engine renders strings and stamps them, and only
    # the workflow knows that a "work_id" is a story or an epic. Without it, spans
    # can be grouped by run and node but not by task, so two runs of the same work
    # cannot be compared except by joining to artifacts on disk.
    #   labels:
    #     work_id: "{{ story.id or epic.id }}"
    #     phase: "{{ current_phase }}"
    # An expression that renders empty is dropped rather than stamped blank, so a
    # label simply does not appear on spans from before its value exists.
    labels: dict[str, str] = Field(default_factory=dict)
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
