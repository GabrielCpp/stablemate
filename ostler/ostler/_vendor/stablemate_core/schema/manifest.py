"""Declaration: every setting of the per-repository manifest, ``agents.yml``."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, StrictBool, ValidationInfo, field_validator, model_validator

from .base import FreeSection, Section, setting
from .selection import Exclusion

HARNESSES = ("codex", "claude", "copilot")

HOOK_MANAGERS = ("pre-commit", "lefthook", "husky", "githooks", "none")

LINK_KEY = "skills_from"

README_ALIASES = {"inline": True, "import": True, "none": False}


class AgentLink(Section):
    """A harness that shares another harness's skill folders instead of holding its own copy."""

    skills_from: str = setting(
        description="The harness whose skill folders this one links to. The source must be enabled and must not itself link.",
        examples=["claude"],
    )


def _harness_switch(value: Any, info: ValidationInfo) -> bool | AgentLink:
    if not isinstance(value, dict):
        return bool(value)
    mapping: dict[Any, Any] = value
    name = info.field_name
    extra = sorted(str(key) for key in mapping if key != LINK_KEY)
    if extra or LINK_KEY not in mapping:
        raise ValueError(
            f"agents.{name} must be true, false or a mapping "
            f"{{{LINK_KEY}: <harness>}} (got {value!r})"
        )
    source = mapping[LINK_KEY]
    if not isinstance(source, str):
        raise ValueError(
            f"agents.{name}.{LINK_KEY} must name a harness, one of "
            f"{', '.join(HARNESSES)} (got {source!r})"
        )
    return AgentLink(skills_from=source)


HarnessSwitch = Annotated[bool | AgentLink, BeforeValidator(_harness_switch)]


class Agents(Section):
    """Which agent harnesses the repository renders for, and which of them link their skills."""

    claude: HarnessSwitch = setting(
        False,
        description="Render for Claude Code: skills under `.claude/skills`, commands under `.claude/commands`. A table `{ skills_from: <harness> }` enables it and links its skills.",
        examples=[True, {"skills_from": "codex"}],
        type_text="boolean or table with `skills_from`",
    )
    codex: HarnessSwitch = setting(
        False,
        description="Render for Codex: skills under `.agents/skills`, prompts under `.agents/prompts`. A table `{ skills_from: <harness> }` enables it and links its skills.",
        examples=[True, {"skills_from": "claude"}],
        type_text="boolean or table with `skills_from`",
    )
    copilot: HarnessSwitch = setting(
        False,
        description="Render for GitHub Copilot: skills and prompts under `.github`, roots into `.github/copilot-instructions.md`. A table `{ skills_from: <harness> }` enables it and links its skills.",
        examples=[False, {"skills_from": "claude"}],
        type_text="boolean or table with `skills_from`",
    )

    @model_validator(mode="after")
    def _links_resolve(self) -> Agents:
        values: dict[str, bool | AgentLink] = {name: getattr(self, name) for name in HARNESSES}
        links = {name: value.skills_from for name, value in values.items() if isinstance(value, AgentLink)}
        for harness, source in links.items():
            where = f"agents.{harness}.{LINK_KEY}"
            if source not in HARNESSES:
                raise ValueError(
                    f"{where} names {source!r}, which is not a harness "
                    f"(one of {', '.join(HARNESSES)})"
                )
            if source == harness:
                raise ValueError(
                    f"{where} names {harness!r} itself; a harness cannot link its own skills"
                )
            if not values[source]:
                raise ValueError(
                    f"{where} names {source!r}, which is not enabled; "
                    f"set agents.{source} to true or link from an enabled harness"
                )
            if source in links:
                raise ValueError(
                    f"{where} names {source!r}, which itself links its skills from "
                    f"{links[source]!r}; link from the harness that holds the real folders"
                )
        return self

    def enabled(self) -> dict[str, bool]:
        """Each harness, in the order the renderer checks them, with whether it is on."""
        return {name: bool(getattr(self, name)) for name in HARNESSES}

    def links(self) -> dict[str, str]:
        """``{linked harness: source harness}`` for every harness that links its skills."""
        found: dict[str, str] = {}
        for name in HARNESSES:
            value: bool | AgentLink = getattr(self, name)
            if isinstance(value, AgentLink):
                found[name] = value.skills_from
        return found


def _include_readme(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    key = str(value)
    if key not in README_ALIASES:
        raise ValueError(
            f"localInstructions.includeReadme must be true or false "
            f"(got {value!r}; the {'/'.join(README_ALIASES)} spellings are the "
            "old mechanism-picking form and still work)"
        )
    return README_ALIASES[key]


class LocalInstruction(Section):
    """One generated instruction file: the library sources it joins and the directories it is written into."""

    skill: str | None = setting(
        None,
        description="One skill whose body is written into the instruction file. `skills` wins when both are given.",
        examples=["api-conventions"],
        default_text="unset",
    )
    skills: list[str] = setting(
        factory=list,
        description="Skills whose bodies are written into the instruction file, in order. Each entry is a skill name as installed.",
        examples=[["api-conventions", "db"]],
    )
    policy: str | None = setting(
        None,
        description="One policy written into the instruction file. `policies` wins when both are given.",
        examples=["uv-workspace"],
        default_text="unset",
    )
    policies: list[str] = setting(
        factory=list,
        description="Policies written into the instruction file, in order. A policy is named by its bare basename, with no repo prefix.",
        examples=[["uv-workspace", "public-repo"]],
    )
    prompt: str | None = setting(
        None,
        description="One prompt written into the instruction file. `prompts` wins when both are given.",
        examples=["review"],
        default_text="unset",
    )
    prompts: list[str] = setting(
        factory=list,
        description="Prompts written into the instruction file, in order. Each entry is a prompt name as installed.",
        examples=[["review"]],
    )
    paths: list[str] = setting(
        factory=list,
        description="Directories, relative to the repository root, that receive the instruction file. `.` is the root.",
        examples=[["."], ["services/api", "services/web"]],
    )
    includeReadme: Annotated[bool, BeforeValidator(_include_readme)] = setting(
        True,
        description="Whether the README.md beside each instruction file is folded in.",
        examples=[False],
        legacy="The strings `inline` and `import` read as true and `none` as false. They are the old form that picked a mechanism.",
        type_text="boolean",
    )
    claudeMd: StrictBool = setting(
        False,
        description="Also write a `CLAUDE.md` containing `@AGENTS.md` beside each instruction file, so Claude Code reads the same text.",
        examples=[True],
    )
    text: str = setting(
        "",
        description="Repository-specific text written after the library sources. An entry may carry only this.",
        examples=["## Map\n\n- `api/`: the HTTP service.\n"],
        default_text="empty",
    )

    @model_validator(mode="after")
    def _selects_a_source(self) -> LocalInstruction:
        if not (
            self.skill_names()
            or self.prompt_names()
            or self.policy_names()
            or self.text.strip()
        ):
            raise ValueError(
                "A localInstructions entry must select at least one source "
                "(`policy`/`policies`, `skill`/`skills` and/or `prompt`/`prompts`) "
                "or carry `text`"
            )
        return self

    def skill_names(self) -> list[str]:
        """The installed skill names this entry selects."""
        return self.skills or ([self.skill] if self.skill else [])

    def policy_names(self) -> list[str]:
        """The policy names this entry selects."""
        return self.policies or ([self.policy] if self.policy else [])

    def prompt_names(self) -> list[str]:
        """The installed prompt names this entry selects."""
        return self.prompts or ([self.prompt] if self.prompt else [])


class RepoTable(FreeSection):
    """The repository's identity. Any other key is passed to library templates as `repo.<key>`."""

    name: str | None = setting(
        None,
        description="The prefix prepended to every installed skill and prompt. The directory name, kebab-cased, when unset.",
        examples=["acme-api"],
        default_text="the repository directory's name, kebab-cased",
    )
    base_branch: str | None = setting(
        None,
        description="The branch a finished story merges into.",
        examples=["develop"],
        default_text="unset",
    )

    def mapping(self) -> dict[str, Any]:
        """Every key the file sets, declared or free."""
        return self.model_dump(exclude_unset=True)


class TemplateTable(FreeSection):
    """Values the library's templates render with. A key the library does not use is ignored."""

    backend_layer_name: str | None = setting(
        None,
        description="What a plan calls the backend layer of a service of the backend type.",
        examples=["api"],
        default_text="unset",
    )
    mobile_layer_name: str | None = setting(
        None,
        description="What a plan calls the layer of a service of the mobile type.",
        examples=["app"],
        default_text="unset",
    )

    def mapping(self) -> dict[str, Any]:
        """Every key the file sets, declared or free."""
        return self.model_dump(exclude_unset=True)


def _hook_manager(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text not in HOOK_MANAGERS:
        raise ValueError(f"hooks.manager: {text!r} is not one of {', '.join(HOOK_MANAGERS)}")
    return text


class HooksTable(Section):
    """How git hooks are wired."""

    manager: Annotated[str | None, BeforeValidator(_hook_manager)] = setting(
        None,
        description="The hook manager farrier splices its entry into. `none` wires no hooks. Unset, farrier picks the one the repository looks like.",
        examples=["githooks", "none"],
        default_text="detected from the repository",
        type_text="one of pre-commit, lefthook, husky, githooks, none",
    )


class ServiceEntry(Section):
    """One service, or one service type, and the commands that check it."""

    path: str | None = setting(
        None,
        description="The service directory, relative to the repository root. Unset means the repository root. A declared path proves a directory is a service.",
        examples=["app/api-service"],
        default_text="unset",
    )
    lint: str | None = setting(
        None,
        description="The command that lints the service. A gate left unset is skipped, never guessed at.",
        examples=["golangci-lint run"],
        default_text="unset",
    )
    test: str | None = setting(
        None,
        description="The command that tests the service. A gate left unset is skipped, never guessed at.",
        examples=["go test ./..."],
        default_text="unset",
    )
    type: str | None = setting(
        None,
        description="The service type this entry stands for, such as `backend` or `mobile`.",
        examples=["backend"],
        default_text="unset",
    )


class WorkflowTable(Section):
    """Keys the installed workflows read for themselves."""

    githubTokenEnv: str | None = setting(
        None,
        description="The name of the environment variable that carries the GitHub token for the coder workflow's pull request and CI steps. `GH_TOKEN` then `GITHUB_TOKEN` are tried after it.",
        examples=["ACME_GH_TOKEN"],
        default_text="unset",
        legacy="`github_token_env` is read as `githubTokenEnv`.",
    )
    prompts: dict[str, str] = setting(
        factory=dict,
        description="Per-role prompt bodies that replace the library's, keyed by role. Each value is a file path, relative to the repository root.",
        examples=[{"plan": ".agents/prompts/plan.md"}],
        legacy="A top-level `prompts` mapping is read as this table, and wins over it when both are set.",
    )


class OrganizationTable(Section):
    """The repository's knowledge graph, read by ostler."""

    name: str | None = setting(
        None,
        description="The organization's name in the graph.",
        examples=["acme"],
        default_text="the repository directory's name",
    )
    profile: str | None = setting(
        None,
        description="How strict the book's checks are. `full` checks everything, `exploration` relaxes the checks meant for a finished book.",
        examples=["full", "exploration"],
        default_text="unset",
    )


class QaFixture(Section):
    """One QA fixture: a command that puts the application into a known state."""

    tool: str | None = setting(
        None,
        description="The opted-in QA tool that runs the fixture.",
        examples=["seed-db"],
        default_text="unset",
    )
    args: list[str] = setting(
        factory=list,
        description="Arguments passed to the tool.",
        examples=[["--profile", "demo"]],
    )
    provides: str | None = setting(
        None,
        description="The state the fixture guarantees, in the terms a scenario's preconditions use.",
        examples=["a signed-in admin with two projects"],
        default_text="unset",
    )
    timeout: float = setting(
        120.0,
        description="Seconds the fixture may run before it is stopped.",
        examples=[300],
    )


class QaTable(Section):
    """What ostler's QA runs may use."""

    tools: list[str] = setting(
        factory=list,
        description="QA tools this repository opts into. A name resolves to a built-in or to a `qa_tools` table of the machine config.",
        examples=[["tesseract", "grpcurl"]],
    )
    fixtures: dict[str, QaFixture] = setting(
        factory=dict,
        description="Fixtures keyed by name. A scenario's precondition names one.",
        examples=[{"seeded-db": {"tool": "seed-db", "provides": "a database with demo rows"}}],
    )
    recordingExemptTargets: list[str] = setting(
        factory=list,
        description="QA targets that may run without a screen recording.",
        examples=[["web"]],
    )


def _scaffold_ids(entries: Any) -> Any:
    for entry in entries or []:
        if not isinstance(entry, str):
            raise ValueError(
                f"scaffolds entries must be scaffold ids (strings); "
                f"got {entry!r}. File-tree scaffolds were replaced by scaffold "
                "definitions — run `farrier scaffold <id> --param key=value` and "
                "list the available ids under `scaffolds:`."
            )
    return entries


class Manifest(Section):
    """``agents.yml``, the file at a repository's root that says what farrier renders and what the workflows read."""

    agents: Agents = setting(
        factory=Agents,
        description="Which agent harnesses to render for. At least one must be enabled for `farrier install` to render. The list form `[claude]` enables just those.",
        examples=[{"claude": True, "codex": {"skills_from": "claude"}}],
        default_text="every harness off",
        legacy="A list of harness names enables exactly those harnesses.",
    )
    packs: list[str] = setting(
        factory=list,
        description="Packs to install. A pack is a named bundle of skills, prompts, roots and scaffolds in the library, and may include other packs.",
        examples=[["general", "python"]],
    )
    skills: list[str] = setting(
        factory=list,
        description="Skills to install on top of the packs. Each entry is a skill id, a name or a glob.",
        examples=[["ostler-*", "db"]],
    )
    prompts: list[str] = setting(
        factory=list,
        description="Prompts to install on top of the packs. Each entry is a prompt id, a name or a glob. The per-role prompt bodies of the coder workflow belong under `workflow.prompts`.",
        examples=[["agent-library/update-skill-from-conversation"]],
    )
    roots: list[str] = setting(
        factory=list,
        description="Roots to render into the always-on instruction file of each harness.",
        examples=[["agents-overview"]],
    )
    scaffolds: list[str] = setting(
        factory=list,
        description="Scaffold ids `farrier scaffold` may apply to this repository.",
        examples=[["go-service"]],
    )
    exclude: Exclusion | None = setting(
        None,
        description="Content to drop after the packs and lists above have been resolved.",
        examples=[{"skills": ["legacy-*"]}],
        default_text="absent",
    )
    template: TemplateTable = setting(
        factory=TemplateTable,
        description="Values the library's templates render with. The keys are the library's own, so this reference cannot list them. Each skill or policy documents the ones it reads.",
        examples=[{"python_floor": "3.12", "lint_command": "make lint"}],
        default_text="empty",
        legacy="`vars` is the older name. Its keys merge into `template`, and `template` wins on a clash.",
    )
    repo: RepoTable = setting(
        factory=RepoTable,
        description="The repository's identity. Any key beyond the two below is passed to library templates as `repo.<key>`.",
        examples=[{"name": "acme-api", "base_branch": "develop", "support_email": "team@example.com"}],
        default_text="empty",
    )
    hooks: HooksTable = setting(
        factory=HooksTable,
        description="How git hooks are wired.",
        examples=[{"manager": "githooks"}],
        default_text="empty",
    )
    localInstructions: list[LocalInstruction] = setting(
        factory=list,
        description="Generated instruction files (`AGENTS.md`, and `CLAUDE.md` on request). Each entry joins library sources and repository text and writes the result into its paths.",
        examples=[[{"policies": ["uv-workspace"], "paths": ["."], "includeReadme": False}]],
    )
    services: dict[str, ServiceEntry] = setting(
        factory=dict,
        description="The services this repository holds, keyed by service name or by service type. The name beats the type. The coder workflow's dev lane takes its gate commands from here.",
        examples=[{"api-service": {"path": "app/api-service", "test": "go test ./..."}}],
        legacy="`workflow.services` is read as this table. The top-level table wins when both are set.",
    )
    lint: dict[str, str] = setting(
        factory=dict,
        description="Per-service lint command overrides, keyed by service name or directory. Prefer `services.<name>.lint`.",
        examples=[{"api-service": "ruff check ."}],
        legacy="`workflow.lint` is read as this table. The top-level table wins when both are set.",
    )
    program: str | None = setting(
        None,
        description="The research program the research workflow runs when none is named on the command line: a directory holding `program.yml`.",
        examples=["specs/my-program"],
        default_text="unset",
    )
    workflow: WorkflowTable = setting(
        factory=WorkflowTable,
        description="Keys the installed workflows read. Farrier itself reads nothing here.",
        examples=[{"githubTokenEnv": "ACME_GH_TOKEN"}],
        default_text="empty",
    )
    organization: OrganizationTable | None = setting(
        None,
        description="Marks the repository as an ostler book and configures it.",
        examples=[{"name": "acme", "profile": "full"}],
        default_text="absent",
    )
    qa: QaTable = setting(
        factory=QaTable,
        description="What ostler's QA runs may use.",
        examples=[{"tools": ["tesseract"], "recordingExemptTargets": ["web"]}],
        default_text="empty",
    )

    @field_validator("scaffolds", mode="before")
    @classmethod
    def _scaffolds_are_ids(cls, value: Any) -> Any:
        return _scaffold_ids(value)
