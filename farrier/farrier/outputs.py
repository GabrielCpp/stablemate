"""Full-render orchestration and the writes that install it."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from farrier.drift import Drifted, report
from farrier.frontmatter import frontmatter_mapping
from farrier.local_instructions import LocalInstruction
from farrier.hook_managers import (
    HOOK_RUNNER,
    LEFTHOOK_INCLUDE,
    configured_manager,
    fence_drift,
    install_manager,
    lefthook_include_text,
    runner_text,
)
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
)
from farrier.managed_blocks import (
    GATE_SCRIPT,
    ensure_agents_gitignore,
    ensure_makefile_include,
    ensure_qa_gitignore,
)
from farrier._vendor.stablemate_core.config import config_path, read_config
from farrier.layers import available_names
from farrier.naming import repo_prefix
from farrier.ownership import is_owned, owned_files, sweep
from farrier.renderer import Rendered, Renderer, user_harness_dir
from farrier.selection_errors import (
    suggestions,
    unknown_selection_error,
)
from farrier.skill_hooks import SkillHook, hooks_for
from farrier.sources import (
    Source,
    collect_selection,
    library_name,
    load_layered_sources,
    public_name,
    selected_sources,
    unmatched_patterns,
)
from farrier.template_values import collect_template_values
from farrier.user_library import (
    HARNESSES,
    user_library_tables,
    user_template_values,
)


MANAGED_DIRS = [
    ".agents/skills",
    ".agents/prompts",
    ".agents/hooks",
    ".claude/skills",
    ".claude/commands",
    ".github/instructions",
    ".github/prompts",
    ".github/skills",
    ".github/agents",
]

MANAGED_FILES = [
    ".github/copilot-instructions.md",
    LAUNCHER_AGENTS_MK,
    LEFTHOOK_INCLUDE,
]

ASSUMED_OWNED = [
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    ".agents/agents-context.*.json",
]


@dataclass(frozen=True)
class Managed:
    """What one install scope owns — the directories it sweeps and the files it names."""

    dirs: tuple[str, ...]
    files: tuple[str, ...] = ()
    assumed: tuple[str, ...] = ()
    repo_scaffolding: bool = True


REPO_MANAGED = Managed(tuple(MANAGED_DIRS), tuple(MANAGED_FILES), tuple(ASSUMED_OWNED))

USER_MANAGED = Managed(
    (
        ".claude/skills",
        ".claude/commands",
        ".agents/skills",
        ".codex/skills",
        ".copilot/skills",
    ),
    repo_scaffolding=False,
)


def repo_managed_with_claude_pointers(instructions: Sequence[LocalInstruction]) -> Managed:
    """REPO_MANAGED plus the CLAUDE.md in every localInstructions directory."""
    pointers = tuple(
        (Path(rel) / "CLAUDE.md").as_posix()
        for instruction in instructions
        for rel in instruction.paths
    )
    return replace(REPO_MANAGED, files=REPO_MANAGED.files + pointers)


def expected_text(content: str) -> str:
    """The exact bytes *content* installs as — the one place the rule is stated."""
    if getattr(content, "verbatim", False):
        return content
    return content.rstrip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected_text(content), encoding="utf-8")
    if getattr(content, "executable", False):
        mode = path.stat().st_mode
        path.chmod(mode | ((mode & 0o444) >> 2))


def normalize_agents(config: dict[str, Any]) -> dict[str, bool]:
    agents = config.get("agents") or {}
    if isinstance(agents, list):
        return {name: name in agents for name in ["codex", "claude", "copilot"]}
    return {
        name: bool(agents.get(name, False)) for name in ["codex", "claude", "copilot"]
    }


def is_assumed_owned(
    repo: Path, path: Path, managed: Managed = REPO_MANAGED
) -> bool:
    """True when *path* is one farrier owns by convention rather than by a mark."""
    rel = path.relative_to(repo).as_posix()
    return any(fnmatch(rel, pattern) for pattern in managed.assumed)


def conflicts(
    repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED
) -> list[str]:
    """The paths farrier is about to write that are held by files it did not generate."""
    return sorted(
        path.relative_to(repo).as_posix()
        for path, content in outputs.items()
        if path.exists()
        and not getattr(content, "assumed", False)
        and not is_assumed_owned(repo, path, managed)
        and not is_owned(path, repo)
    )


def refuse_conflicts(
    repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED
) -> None:
    """Abort the install when any output path holds a file farrier does not own."""
    held = conflicts(repo, outputs, managed)
    if not held:
        return
    listing = "\n".join(f"  {rel}" for rel in held)
    raise SystemExit(
        f"farrier will not overwrite files it did not generate. {len(held)} path(s) it "
        f"renders are held by untagged files:\n{listing}\n"
        "Rename or delete each one, then install again. Nothing was written. "
        "A file farrier generated says so — `metadata.generated_by: farrier` in a "
        "skill, prompt or command, or a `generated by farrier` comment near the top "
        "of anything that cannot carry front matter."
    )


def remove_targets(repo: Path, managed: Managed = REPO_MANAGED) -> None:
    """Delete farrier's previous output — and only farrier's."""
    for rel in managed.dirs:
        sweep(repo / rel)
    for rel in managed.files:
        path = repo / rel
        if path.is_file() and is_owned(path, repo):
            path.unlink()
    for pattern in managed.assumed:
        for path in sorted(repo.glob(pattern)):
            if path.is_file():
                path.unlink()


def check_selection(
    groups: list[tuple[str, list, set[str]]],
) -> None:
    """Fail on any selection entry that names a library file which does not exist."""
    reports: list[str] = []
    for kind, all_sources, include_patterns in groups:
        literals, globs = unmatched_patterns(all_sources, include_patterns)
        available = [source.id for source in all_sources]
        for pattern in globs:
            close = suggestions(pattern.replace("*", "").replace("?", ""), available)
            hint = f" Closest names: {', '.join(close)}." if close else ""
            print(
                f"warning: glob {pattern!r} in agents.yml `{kind}:` selected nothing.{hint}"
            )
        if literals:
            reports.append(
                unknown_selection_error(
                    kind,
                    literals,
                    available,
                    extra=(
                        "Selection is a filter, so an entry naming a file that does not "
                        "exist would otherwise contribute nothing and install silently — "
                        "leaving the repo without something it declared."
                    ),
                )
            )
    if reports:
        raise SystemExit("\n\n".join(reports))


def home_duplicate_notices(
    skills: Sequence[Source],
    home_skills: dict[str, list[Source]],
    agents: dict[str, Any],
) -> list[str]:
    """One info line per selected skill that the user library also installs for an enabled harness."""
    at_home = {
        library_name(source)
        for harness, sources in home_skills.items()
        if agents.get(harness)
        for source in sources
    }
    return [
        f"info: skill {name!r} installs both in this repo and from the user library "
        "at home. The repo copy is the one every contributor gets."
        for name in sorted({library_name(source) for source in skills} & at_home)
    ]


def render_expected(
    config: dict[str, Any],
    repo: Path,
    instructions: Sequence[LocalInstruction],
    notices: list[str] | None = None,
) -> dict[Path, str]:
    repo_config = config.get("repo") or {}
    prefix = repo_prefix(repo, repo_config)
    agents = normalize_agents(config)
    if not any(agents.values()):
        raise SystemExit("No agents selected in config")

    (
        include_skills,
        include_prompts,
        roots,
        _scaffold_ids,
    ) = collect_selection(config)
    exclude = config.get("exclude") or {}

    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")
    all_policies = load_layered_sources("policy", "library", "policies")
    skills = selected_sources(
        all_skills, include_skills, set(exclude.get("skills", []) or [])
    )
    prompts = selected_sources(
        all_prompts, include_prompts, set(exclude.get("prompts", []) or [])
    )
    check_selection(
        [("skills", all_skills, include_skills), ("prompts", all_prompts, include_prompts)]
    )
    if not skills and not prompts:
        packs = available_names("packs", suffix=".yml")
        catalog = (
            "Available packs:\n" + "\n".join(f"  - {name}" for name in packs)
            if packs
            else "No packs found in the configured layers."
        )
        if not include_skills and not include_prompts:
            raise SystemExit(
                "The config selects nothing: `packs:` is empty and no skills or "
                f"prompts are named directly. {catalog}"
            )
        raise SystemExit(f"Selected packs did not match any skills or prompts. {catalog}")

    home_skills = {
        harness: selected
        for harness, (selected, _prompts) in user_selections(
            read_config(), all_skills, all_prompts
        ).items()
    }
    if notices is not None:
        notices.extend(home_duplicate_notices(skills, home_skills, agents))
    renderer = Renderer(
        repo,
        prefix,
        repo_config,
        collect_template_values(config),
        skills,
        prompts,
        all_policies,
        home_skills=home_skills,
    )
    outputs = renderer.render(agents, roots)

    for instruction in instructions:
        skill_names = instruction.skills
        prompt_names = instruction.prompts
        policy_names = instruction.policies
        include_readme = instruction.include_readme
        writes_claude_md = instruction.writes_claude_md
        claude_only = bool(agents.get("claude")) and not (
            agents.get("codex") or agents.get("copilot")
        )
        readme_import = include_readme and claude_only and writes_claude_md
        target = "claude" if claude_only else "codex"
        for rel in instruction.paths:
            directory = repo / rel
            if not directory.exists():
                raise SystemExit(
                    f"Local instruction path does not exist: {rel} "
                    "(create it first — e.g. `farrier scaffold <id>`)"
                )
            agents_path = directory / "AGENTS.md"
            outputs[agents_path] = renderer.render_local_instruction(
                skill_names,
                target,
                agents_path,
                include_readme and not readme_import,
                prompt_names,
                policy_names,
                instruction.text,
            )
            if writes_claude_md:
                claude_path = directory / "CLAUDE.md"
                outputs[claude_path] = renderer.render_claude_pointer(
                    skill_names,
                    claude_path,
                    prompt_names,
                    readme_import,
                    policy_names,
                )

    renderer.check_resolved()

    manager = configured_manager(config, repo)
    if manager != "none":
        outputs[repo / HOOK_RUNNER] = Rendered(
            runner_text(selected_hooks(prefix, skills)), executable=True
        )
    if manager == "lefthook":
        outputs[repo / LEFTHOOK_INCLUDE] = Rendered(lefthook_include_text())

    return outputs


def user_selections(
    config: dict[str, Any], all_skills: list[Source], all_prompts: list[Source]
) -> dict[str, tuple[list[Source], list[Source]]]:
    """Each harness's user-library skills and prompts, from the stablemate config."""
    selections: dict[str, tuple[list[Source], list[Source]]] = {}
    for harness, table in user_library_tables(config).items():
        include_skills, include_prompts, roots, _scaffolds = collect_selection(table)
        if roots:
            raise SystemExit(
                f"error: [user_library.{harness}] names roots. A root renders into a "
                "repo's always-on instruction file, and no harness reads one from the "
                "home directory."
            )
        if harness != "claude":
            if table.get("prompts"):
                raise SystemExit(
                    f"error: [user_library.{harness}] names prompts. Claude is the only "
                    "harness with a personal command directory (~/.claude/commands), so "
                    "prompts are Claude-only at user scope."
                )
            include_prompts = set()
        exclude = table.get("exclude") or {}
        skills = selected_sources(
            all_skills, include_skills, set(exclude.get("skills", []) or [])
        )
        prompts = selected_sources(
            all_prompts, include_prompts, set(exclude.get("prompts", []) or [])
        )
        check_selection(
            [
                ("skills", all_skills, include_skills),
                ("prompts", all_prompts, include_prompts),
            ]
        )
        if not skills and not prompts:
            raise SystemExit(
                f"error: [user_library.{harness}] selected no skills or prompts."
            )
        selections[harness] = (skills, prompts)
    return share_home_folders(selections)


def share_home_folders(
    selections: dict[str, tuple[list[Source], list[Source]]],
) -> dict[str, tuple[list[Source], list[Source]]]:
    """Each harness's selection widened to the union of every harness that installs into the same home folder."""
    by_folder: dict[str, list[str]] = {}
    for harness in selections:
        by_folder.setdefault(user_harness_dir(harness), []).append(harness)
    shared: dict[str, tuple[list[Source], list[Source]]] = {}
    for harnesses in by_folder.values():
        skills = list(dict.fromkeys(s for h in harnesses for s in selections[h][0]))
        prompts = list(dict.fromkeys(p for h in harnesses for p in selections[h][1]))
        for harness in harnesses:
            shared[harness] = (skills, prompts)
    return shared


def render_user_expected(config: dict[str, Any], home: Path) -> dict[Path, str]:
    """The complete user-scope output set, from the stablemate config's user_library."""
    if not user_library_tables(config):
        raise SystemExit(
            "error: no user library is configured. Add a "
            "[user_library.<harness>] table naming the skills to install for every "
            f"project — one of {', '.join(HARNESSES)} — to {config_path()}."
        )
    values = user_template_values(config)
    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")

    selections = user_selections(config, all_skills, all_prompts)
    outputs: dict[Path, str] = {}
    rendered: set[str] = set()
    for harness in HARNESSES:
        if harness not in selections or user_harness_dir(harness) in rendered:
            continue
        rendered.add(user_harness_dir(harness))
        skills, prompts = selections[harness]
        renderer = Renderer(home, "", {}, values, skills, prompts, scope="user")
        outputs.update(renderer.render({harness: True}, set()))
    return outputs


def selected_hooks(prefix: str, skills) -> list[SkillHook]:
    """Every hook the selected skills declare, in selection order."""
    hooks: list[SkillHook] = []
    for source in skills:
        data = frontmatter_mapping(source.path.read_text(encoding="utf-8"))
        hooks.extend(hooks_for(public_name(prefix, source), data))
    return hooks


def check_outputs(
    repo: Path,
    outputs: dict[Path, str],
    manager: str | None = None,
    managed: Managed = REPO_MANAGED,
) -> int:
    missing: list[str] = []
    changed: list[Drifted] = []
    extra: list[str] = []
    for path, content in outputs.items():
        expected = expected_text(content)
        rel = path.relative_to(repo).as_posix()
        if not path.exists():
            missing.append(rel)
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            changed.append(Drifted(rel, content, expected, actual))
        elif getattr(content, "executable", False) and not path.stat().st_mode & 0o111:
            changed.append(Drifted(rel, content, expected, actual))

    expected_paths = set(outputs)
    for rel in managed.dirs:
        for path in owned_files(repo / rel):
            if path not in expected_paths:
                extra.append(path.relative_to(repo).as_posix())
    named = list(managed.files)
    if managed.files:
        named.append(LAUNCHER_CONTEXT_MANIFEST)
    for rel in named:
        path = repo / rel
        if path not in expected_paths and path.is_file():
            if is_assumed_owned(repo, path, managed) or is_owned(path, repo):
                extra.append(path.relative_to(repo).as_posix())

    fences = fence_drift(repo, manager) if manager is not None else []

    if missing or changed or extra or fences:
        print(report(missing, changed, extra, fences))
        return 1
    return 0


def install_outputs(
    repo: Path,
    outputs: dict[Path, str],
    manager: str | None = None,
    managed: Managed = REPO_MANAGED,
) -> None:
    refuse_conflicts(repo, outputs, managed)
    remove_targets(repo, managed)
    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        write_text(path, content)
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_agents_gitignore(repo):
        print("Updated .agents .gitignore rules")
    if managed.repo_scaffolding and any(
        path.name == Path(GATE_SCRIPT).name for path in outputs
    ):
        if ensure_qa_gitignore(repo):
            print("Updated QA evidence .gitignore rules")
    if manager is not None:
        for line in install_manager(repo, manager):
            print(line)
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_makefile_include(repo):
        print("Added agent launcher include to root Makefile")
