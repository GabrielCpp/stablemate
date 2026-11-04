"""Declaration: every setting of the machine config, ``config.toml``."""

from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import BeforeValidator, field_validator, model_validator

from .base import Section, setting
from .selection import Selection

BUILTIN_DEFAULT_CLI = "claude"

AttendMode = Literal["off", "session", "headless"]


def text_or_none(raw: Any) -> str | None:
    """A non-empty string, or ``None`` for anything else: a malformed path reads as unset."""
    return raw if isinstance(raw, str) and raw else None


def cli_name(raw: Any) -> str:
    """A CLI name trimmed and lowercased; anything unusable reads as the built-in default."""
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return BUILTIN_DEFAULT_CLI


def positive_finite(raw: Any) -> float | None:
    """A strictly positive, finite number as a float, or ``None`` for anything else."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        return None
    return value


OptionalPath = Annotated[str | None, BeforeValidator(text_or_none)]


class PowerTier(Section):
    """The model, effort and timeout a tier, a default or a delegate role resolves to."""

    model: str | None = setting(
        None,
        description="The model name passed to the agent CLI. Empty or absent leaves the CLI's own default.",
        examples=["opus", "openrouter/deepseek-v4-flash-0731"],
        default_text="unset",
    )
    effort: str | None = setting(
        None,
        description="The reasoning effort passed to the agent CLI, in the CLI's own vocabulary.",
        examples=["high", "medium"],
        default_text="unset",
    )
    timeout_scale: Annotated[float | None, BeforeValidator(positive_finite)] = setting(
        None,
        description="A multiplier applied to every node timeout under this tier. A value that is not a positive finite number reads as unset.",
        examples=[2.5, 1.5],
        default_text="unset",
    )


class Profile(Section):
    """A named model set, bound to one agent CLI and selected per run."""

    cli: str = setting(
        description="The agent CLI this profile runs under. A profile whose cli differs from the CLI of a run resolves nothing.",
        examples=["claude", "opencode"],
        legacy="`default_cli` inside the profile, carried to `cli` when the file is lifted from version 1.",
    )
    powers: dict[str, PowerTier] = setting(
        factory=dict,
        description="The model mapping for each power tier, keyed by tier name (low, medium, high, max, ultra).",
        examples=[{"high": {"model": "opus", "effort": "high"}}],
        legacy="`power.<tier>.<cli>` at the top level, and `power` inside a profile, both version 1 shapes carried to `powers.<tier>`.",
    )
    default: PowerTier | None = setting(
        None,
        description="The mapping used when a node names no power tier.",
        examples=[{"model": "sonnet"}],
        default_text="absent",
        legacy="`default.<cli>` at the top level, and a per-cli `default` inside a profile, both version 1 shapes carried to `default`.",
    )
    delegates: dict[str, PowerTier] = setting(
        factory=dict,
        description="The model and effort for each subagent role, keyed by role name. A role that names no model is ignored.",
        examples=[{"lookup": {"model": "haiku"}, "worker": {"model": "sonnet"}}],
    )

    def cli_name(self) -> str | None:
        """The profile's CLI, trimmed and lowercased, or ``None`` when blank."""
        name = self.cli.strip().lower()
        return name or None


class CliBackend(Section):
    """Settings handed to one agent CLI, whichever profile runs it."""

    env: dict[str, str] = setting(
        factory=dict,
        description="Environment variables set for the CLI process, keyed by variable name. Every profile that runs this CLI inherits them. Values can be secrets, so the tools never print them.",
        examples=[{"OPENCODE_DISABLE_AUTOCOMPACT": "1"}],
    )


class WorkspaceEntry(Section):
    """One repository of a workspace."""

    path: str = setting(
        description="The repository's folder. A leading `~` expands to the home directory.",
        examples=["~/code/api-service"],
    )
    name: str | None = setting(
        None,
        description="The member's name. When absent it is the folder's basename, lowercased and kebab-cased.",
        examples=["api-service"],
        default_text="the folder's basename, normalised",
    )
    url: str | None = setting(
        None,
        description="The repository's origin URL. A clone elsewhere that has this origin counts as the member.",
        examples=["https://example.com/example-org/api-service.git"],
        default_text="unset",
    )
    branch: str | None = setting(
        None,
        description="The branch to check out when the workspace is prepared.",
        examples=["main"],
        default_text="unset",
    )

    @model_validator(mode="before")
    @classmethod
    def _path_string(cls, data: Any) -> Any:
        return {"path": data} if isinstance(data, str) else data


class AttendTable(Section):
    """The dashboard's standing choice of how an operator gate is attended."""

    mode: AttendMode = setting(
        "off",
        description="How operator gates are attended. `off` leaves them to a person, `session` attends them from a live session, `headless` attends them with a background agent.",
        examples=["session"],
        env="GROOM_ATTEND",
        precedence="this key, then the environment variable, then `off`",
    )
    last_mode: AttendMode = setting(
        "headless",
        description="The mode to return to when attending is switched back on. `off` is never remembered here and reads as `headless`.",
        examples=["headless"],
        default_text="the active mode when it is not `off`, else `headless`",
    )
    cli: str = setting(
        BUILTIN_DEFAULT_CLI,
        description="The agent CLI that attends gates in `headless` mode.",
        examples=["claude"],
        env="GROOM_ATTEND_CLI",
        precedence="this key, then the environment variable, then `claude`",
    )
    deny: list[str] = setting(
        factory=list,
        description="Gate kinds the attendant must leave to a person, lowercased. The environment variable holds the same list, comma separated.",
        examples=[["merge", "release"]],
        env="GROOM_ATTEND_DENY",
        precedence="this key, then the environment variable, then an empty list",
    )

    @field_validator("mode", "last_mode", mode="before")
    @classmethod
    def _any_case(cls, value: Any) -> Any:
        return value.lower() if isinstance(value, str) else value

    @field_validator("deny", mode="before")
    @classmethod
    def _text_entries(cls, value: Any) -> Any:
        return [str(entry) for entry in value] if isinstance(value, list) else value


class DispatchParam(Section):
    """One field of a queue's enqueue-time form."""

    name: str = setting(
        "",
        description="The parameter's name, passed to the workflow command. A parameter without one is ignored.",
        examples=["story"],
    )
    label: str = setting(
        "",
        description="The label the dashboard form shows.",
        examples=["Story id"],
        default_text="the name",
    )
    type: str = setting(
        "string",
        description="The form control, lowercased.",
        examples=["string", "select"],
    )
    required: bool = setting(
        False,
        description="Whether the form refuses an empty value.",
        examples=[True],
    )
    default: str = setting(
        "",
        description="The value the form starts with.",
        examples=["main"],
    )
    options: list[str] = setting(
        factory=list,
        description="The choices of a `select` control.",
        examples=[["main", "develop"]],
    )
    template: str = setting(
        "",
        description="A template that turns the entered value into the argument the command receives.",
        examples=["--story {value}"],
    )


class DispatchQueue(Section):
    """One queue of workflow runs the dashboard launches."""

    command: str = setting(
        "",
        description="The workflow command a queued item launches. A queue without one is ignored.",
        examples=["workhorse-loop-runner"],
    )
    concurrency: int = setting(
        1,
        description="How many items of this queue may run at once. A value below 1 counts as 1.",
        examples=[2],
    )
    params: list[DispatchParam] = setting(
        factory=list,
        description="The fields the dashboard's enqueue form offers.",
        examples=[[{"name": "story", "label": "Story id", "required": True}]],
    )


class GroomTable(Section):
    """Settings read by the groom dashboard."""

    attend: AttendTable | None = setting(
        None,
        description="How operator gates are attended.",
        examples=[{"mode": "session", "cli": "claude"}],
        default_text="absent (every field takes its default)",
    )
    dispatch: dict[str, DispatchQueue] = setting(
        factory=dict,
        description="The dispatch queues, keyed by queue name.",
        examples=[{"loop-runner": {"command": "workhorse-loop-runner", "concurrency": 2}}],
    )


class UserLibraryTable(Section):
    """What a user installs into the home directory for every project at once."""

    claude: Selection | None = setting(
        None,
        description="The skills and prompts installed for Claude Code under `~/.claude`.",
        examples=[{"packs": ["general"], "prompts": ["review"]}],
        default_text="absent",
    )
    codex: Selection | None = setting(
        None,
        description="The skills installed for Codex under `~/.codex`. Prompts are Claude-only at user scope.",
        examples=[{"packs": ["general"]}],
        default_text="absent",
    )
    copilot: Selection | None = setting(
        None,
        description="The skills installed for Copilot. Prompts are Claude-only at user scope.",
        examples=[{"skills": ["farrier-setup"]}],
        default_text="absent",
    )
    opencode: Selection | None = setting(
        None,
        description="The rules, MCP servers, guards and agents installed for OpenCode under `~/.config/opencode`. Skills and prompts are left out, because OpenCode reads the skills of `~/.claude` and `~/.agents`.",
        examples=[{"packs": ["general"]}],
        default_text="absent",
    )
    template: dict[str, Any] = setting(
        factory=dict,
        description="Template values shared by every harness's rendered content. The keys belong to the library whose templates read them, so no tool lists them.",
        examples=[{"backend_layer_name": "api-service"}],
        type_text="table of free keys",
    )


class QaTool(Section):
    """A command a QA run may invoke, opted into by a repository's manifest."""

    command: str = setting(
        "",
        description="The executable to run. A repository that opts into a tool whose table has no command gets an error.",
        examples=["tesseract", "/opt/bin/ocr-diff"],
    )
    description: str = setting(
        "",
        description="What the tool does, shown to the agent that may call it.",
        examples=["OCR a screenshot"],
    )


class SaddlebagTable(Section):
    """Settings read by saddlebag, the credential store."""

    backend: Literal["keyring", "daemon"] | None = setting(
        None,
        description="Where credentials are kept. `keyring` uses the operating system's keyring, `daemon` asks the saddlebag daemon.",
        examples=["keyring"],
        env="SADDLEBAG_BACKEND",
        precedence="the environment variable, then this key, then the tool's own detection",
        default_text="unset",
    )


class HomeConfig(Section):
    """The machine config: one `config.toml` per user, shared by every stablemate tool."""

    config_version: int = setting(
        1,
        description="The schema version this file was last written under. An absent key reads as version 1. A tool refuses to write a file newer than it understands and lifts an older one on its first write.",
        examples=[2],
    )
    library_dir: str | None = setting(
        None,
        description="The overlay library root, a folder holding `library/` and `packs/`. It layers over the base library.",
        examples=["~/code/example-org/agents"],
        env="FARRIER_LIBRARY_DIR",
        precedence="farrier's `--library` flag, then the environment variable, then this key",
        default_text="unset",
    )
    base_dir: str | None = setting(
        None,
        description="An explicit path to the base library content. An invalid path is skipped, not an error.",
        examples=["~/code/stablemate/base-library"],
        env="STABLEMATE_BASE_DIR",
        precedence="the environment variable, then this key, then `<stablemate_dir>/base-library`, then the shared cache",
        default_text="unset",
    )
    stablemate_dir: str | None = setting(
        None,
        description="A local stablemate checkout. Its `base-library` folder serves as the base library, and local-source runs of the generated launcher use it.",
        examples=["~/code/stablemate"],
        default_text="unset",
    )
    worktree_dir: OptionalPath = setting(
        None,
        description="The parent folder new git worktrees are cut into. It need not exist yet. A value that is not a non-empty string reads as unset.",
        examples=["~/code/worktrees"],
        default_text="unset",
    )
    artifacts_dir: OptionalPath = setting(
        None,
        description="Where per-user story artifacts live, outside git and shared by every worktree. A value that is not a non-empty string reads as unset.",
        examples=["~/Documents/artifacts"],
        env="STABLEMATE_ARTIFACTS_DIR",
        precedence="the environment variable, then this key, then the default",
        default_text="`<user data dir>/stablemate/artifacts`",
    )
    paddock_dir: OptionalPath = setting(
        None,
        description="The benchmark root paddock reads and writes: `gold/`, `workspace/` and `results/` live under it. A value that is not a non-empty string reads as unset.",
        examples=["~/Documents/benchmarks"],
        default_text="`<user data dir>/stablemate/paddock`",
    )
    ostler_index_dir: str | None = setting(
        None,
        description="Where ostler keeps its parse index. A blank value reads as unset.",
        examples=["~/.cache/ostler-index"],
        env="OSTLER_INDEX_DIR",
        precedence="an explicit argument, then the environment variable, then this key, then `ostler-index` under the shared cache",
        default_text="`ostler-index` under the shared cache",
    )
    default_cli: Annotated[str, BeforeValidator(cli_name)] = setting(
        BUILTIN_DEFAULT_CLI,
        description="The agent CLI a run drives when nothing on the invocation names one. It is trimmed and lowercased, and a malformed value reads as the default.",
        examples=["claude", "opencode"],
        env="AGENT_CLI",
        precedence="a `--cli` flag, then the environment variable, then this key, then `claude`",
    )
    workspaces: dict[str, list[WorkspaceEntry]] = setting(
        factory=dict,
        description="Named groups of repositories, keyed by workspace name. Each entry is a path string or a table with a `path`. A repository in any workspace shares the artifacts folder.",
        examples=[
            {
                "acme": [
                    "~/code/api-service",
                    {"path": "~/code/web-app", "name": "web", "branch": "develop"},
                ]
            }
        ],
        type_text="table of lists of path strings or tables",
    )
    profiles: dict[str, Profile] = setting(
        factory=dict,
        description="Named model sets, keyed by profile name. A run selects one with `--profile`, or the profile named after its CLI when none is given.",
        examples=[{"claude": {"cli": "claude", "default": {"model": "sonnet"}}}],
        legacy="Version 1 kept model tables at the top level as `power`, `default` and `harness`. Lifting the file folds them into profiles and `cli`.",
    )
    cli: dict[str, CliBackend] = setting(
        factory=dict,
        description="Settings per agent CLI, keyed by CLI name.",
        examples=[{"opencode": {"env": {"OPENCODE_DISABLE_AUTOCOMPACT": "1"}}}],
        legacy="`harness.<cli>` in version 1.",
    )
    groom: GroomTable | None = setting(
        None,
        description="Settings read by the groom dashboard.",
        examples=[{"attend": {"mode": "off"}}],
        default_text="absent",
    )
    user_library: UserLibraryTable | None = setting(
        None,
        description="What `farrier install --user` installs into the home directory for every project. Nothing is installed at user scope when it is absent.",
        examples=[{"claude": {"packs": ["general"]}}],
        default_text="absent",
    )
    qa_tools: dict[str, QaTool] = setting(
        factory=dict,
        description="Commands a QA run may invoke, keyed by tool name. A repository opts in by listing the name under `qa: tools:` in its manifest.",
        examples=[{"tesseract": {"command": "tesseract", "description": "OCR a screenshot"}}],
    )
    saddlebag: SaddlebagTable | None = setting(
        None,
        description="Settings read by saddlebag, the credential store.",
        examples=[{"backend": "keyring"}],
        default_text="absent",
    )
