"""Full-render orchestration and the writes that install it."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from farrier.agents import Agents, parse_agents
from farrier.drift import Drifted, report
from farrier.frontmatter import frontmatter_mapping
from farrier.home_mcp import tool_server_names
from farrier.local_instructions import LocalInstruction, local_instructions
from farrier.hook_managers import (
    LEFTHOOK_INCLUDE,
    RUNNERS,
    configured_manager,
    fence_drift,
    install_manager,
    lefthook_include_text,
    runner_text,
)
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_CONTEXT_MANIFEST,
)
from farrier.managed_blocks import (
    GATE_SCRIPT,
    ensure_agents_gitignore,
    ensure_makefile_include,
    ensure_qa_gitignore,
)
from farrier._vendor.stablemate_core.config import config_path, load_home_config
from farrier._vendor.stablemate_core.harness import (
    home_harnesses,
)
from farrier._vendor.stablemate_core.schema import HomeConfig
from farrier.layers import available_names
from farrier.managed_scopes import REPO_MANAGED, Managed, link_map
from farrier.manifest import ConfigLike, as_manifest, excluded
from farrier.naming import repo_prefix
from farrier.ownership import (
    is_owned,
    is_owned_link,
    owned_files,
    owned_links,
    sweep,
)
from farrier.render_groups import render_groups, skill_forms
from farrier.renderer import (
    Output,
    Rendered,
    Renderer,
    Symlink,
    user_harness_dir,
)
from farrier.selection_errors import (
    suggestions,
    unknown_selection_error,
)
from farrier.skill_hooks import (
    SKILL_ROOTS,
    STAGES,
    CommitCheck,
    SkillHook,
    checks_for,
    hooks_for,
)
from farrier.home_agents import agent_files, agent_names
from farrier.home_guards import (
    guard_files,
    guard_names,
)
from farrier.sources import (
    POLICY_ROOT,
    Source,
    build_policy_lookup,
    collect_selection,
    library_name,
    load_layered_sources,
    matches,
    public_name,
    selected_sources,
    unmatched_patterns,
)
from farrier.template_values import collect_template_values
from farrier.user_library import (
    user_library_origin, user_library_tables, user_template_values,
)


HOME_ONLY = {"mcp", "hooks", "agents", "settings"}

READS_OTHER_SKILLS = {
    spec.name for spec in home_harnesses() if spec.skills_reads_others
}


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


def write_link(path: Path, link: Symlink) -> None:
    """Point the symlink at *path* to *link*'s target, replacing a symlink already there."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    os.symlink(link.target, path, target_is_directory=True)


def write_output(path: Path, content: Output) -> None:
    """Install one output, whichever kind it is."""
    if isinstance(content, Symlink):
        write_link(path, content)
    else:
        write_text(path, content)


def normalize_agents(config: ConfigLike) -> Agents:
    return parse_agents(config)


def is_assumed_owned(repo: Path, path: Path, managed: Managed = REPO_MANAGED) -> bool:
    """True when *path* is one farrier owns by convention rather than by a mark."""
    rel = path.relative_to(repo).as_posix()
    return any(fnmatch(rel, pattern) for pattern in managed.assumed)


def sweeps_clean(path: Path, repo: Path) -> bool:
    """True when every file under the real directory *path* is farrier's, so a sweep empties it."""
    if path.is_symlink() or not path.is_dir():
        return False
    return all(
        entry.is_dir() and not entry.is_symlink() or is_owned(entry, repo)
        for entry in path.rglob("*")
    )


def holds_link(path: Path, content: Symlink, repo: Path, managed: Managed) -> bool:
    """True when something farrier may not replace stands where the symlink *content* goes."""
    if not (path.is_symlink() or path.exists()):
        return False
    source_dir = link_map(repo, managed).get(path.parent)
    if source_dir is not None and is_owned_link(path, source_dir):
        return False
    return not sweeps_clean(path, repo)


def behind_foreign_link(path: Path, repo: Path, managed: Managed) -> bool:
    """True when *path* sits inside a symlinked folder of a repo skills directory."""
    if not managed.repo_scaffolding:
        return False
    skill_dirs = {repo / rel for rel in managed.dirs}
    return any(
        parent.is_symlink() and parent.parent in skill_dirs
        for parent in path.parents
        if repo in parent.parents
    )


def conflicts(
    repo: Path, outputs: Mapping[Path, Output], managed: Managed = REPO_MANAGED
) -> list[str]:
    """The paths farrier is about to write that are held by files it did not generate."""
    held: list[str] = []
    for path, content in outputs.items():
        if isinstance(content, Symlink):
            is_held = holds_link(path, content, repo, managed)
        else:
            is_held = behind_foreign_link(path, repo, managed) or (
                path.exists()
                and not getattr(content, "assumed", False)
                and not is_assumed_owned(repo, path, managed)
                and not is_owned(path, repo)
            )
        if is_held:
            held.append(path.relative_to(repo).as_posix())
    return sorted(held)


def refuse_conflicts(
    repo: Path, outputs: Mapping[Path, Output], managed: Managed = REPO_MANAGED
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
    links = link_map(repo, managed)
    for rel in managed.dirs:
        sweep(repo / rel, links)
    for rel in managed.files:
        path = repo / rel
        if path.is_file() and is_owned(path, repo):
            path.unlink()
    for pattern in managed.assumed:
        for path in sorted(repo.glob(pattern)):
            if path.is_file():
                path.unlink()


def check_selection(
    groups: list[tuple[str, list, set[str]]], origin: str = "agents.yml"
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
                f"warning: glob {pattern!r} in {origin} `{kind}:` selected nothing.{hint}"
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
                    origin=origin,
                )
            )
    if reports:
        raise SystemExit("\n\n".join(reports))


def home_duplicate_notices(
    skills: Sequence[Source],
    home_skills: dict[str, list[Source]],
    agents: Agents,
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


def build_renderer(
    config: ConfigLike,
    repo: Path,
    agents: Agents,
    notices: list[str] | None = None,
) -> tuple[Renderer, set[str], list[Source]]:
    """The renderer for *config*'s selection, the roots it names and the skills it selects."""
    repo_config = as_manifest(config).repo.mapping()
    prefix = repo_prefix(repo, repo_config)

    (
        include_skills,
        include_prompts,
        roots,
        _scaffold_ids,
    ) = collect_selection(config)

    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")
    all_policies = load_layered_sources("policy", "library", "policies")
    skills = selected_sources(all_skills, include_skills, excluded(config, "skills"))
    prompts = selected_sources(
        all_prompts, include_prompts, excluded(config, "prompts")
    )
    check_selection(
        [
            ("skills", all_skills, include_skills),
            ("prompts", all_prompts, include_prompts),
        ]
    )
    if not skills and not prompts and (include_skills or include_prompts):
        packs = available_names("packs", suffix=".yml")
        catalog = (
            "Available packs:\n" + "\n".join(f"  - {name}" for name in packs)
            if packs
            else "No packs found in the configured layers."
        )
        raise SystemExit(
            f"Selected packs did not match any skills or prompts. {catalog}"
        )

    home_skills = {
        harness: selected
        for harness, (selected, _prompts) in user_selections(
            load_home_config(), all_skills, all_prompts
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
        hand_written_dirs=agents.real_skill_dirs(),
        skill_forms=skill_forms(
            render_groups(
                "repo",
                {
                    harness: (skills, prompts)
                    for harness in agents.enabled
                    if agents.get(harness)
                },
            )
        ),
    )
    return renderer, roots, skills


def local_instruction_target(agents: Agents) -> str:
    """The harness a localInstructions file renders its templates for."""
    others = agents.get("codex") or agents.get("copilot") or agents.get("pi")
    if agents.get("claude") and not (others or agents.get("antigravity")):
        return "claude"
    if agents.get("antigravity") and not others:
        return "antigravity"
    return "codex"


def render_expected(
    config: ConfigLike,
    repo: Path,
    instructions: Sequence[LocalInstruction],
    notices: list[str] | None = None,
) -> dict[Path, Output]:
    agents = normalize_agents(config)
    if not agents.any_enabled():
        raise SystemExit("No agents selected in config")

    renderer, roots, skills = build_renderer(config, repo, agents, notices)
    prefix = renderer.prefix
    files = renderer.render(agents.enabled, roots, agents.links)
    outputs: dict[Path, Output] = {**files, **renderer.link_skills(agents.links, files)}

    for instruction in instructions:
        skill_names = instruction.skills
        prompt_names = instruction.prompts
        policy_names = instruction.policies
        include_readme = instruction.include_readme
        writes_claude_md = instruction.writes_claude_md
        target = local_instruction_target(agents)
        readme_import = include_readme and target == "claude" and writes_claude_md
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

    policy_names = [
        name for instruction in instructions for name in instruction.policies
    ]
    outputs.update(renderer.policy_bundles(policy_names))
    renderer.check_resolved()

    manager = configured_manager(config, repo)
    if manager != "none":
        policies = dict.fromkeys(renderer.policy_source(name) for name in policy_names)
        hooks = [*selected_hooks(prefix, skills), *policy_hooks(policies)]
        for stage in STAGES:
            outputs[repo / RUNNERS[stage]] = Rendered(
                runner_text(hooks, stage), executable=True
            )
    if manager == "lefthook":
        outputs[repo / LEFTHOOK_INCLUDE] = Rendered(lefthook_include_text())

    return outputs


def user_selections(
    home: HomeConfig, all_skills: list[Source], all_prompts: list[Source]
) -> dict[str, tuple[list[Source], list[Source]]]:
    """Each harness's user-library skills and prompts, from the stablemate config."""
    selections: dict[str, tuple[list[Source], list[Source]]] = {}
    for harness, table in user_library_tables(home).items():
        origin = user_library_origin(harness)
        include_skills, include_prompts, roots, _scaffolds = collect_selection(
            table.model_dump(exclude_unset=True, exclude=HOME_ONLY), origin
        )
        exclude = table.exclude
        skills = selected_sources(
            all_skills, include_skills, set(exclude.skills if exclude else [])
        )
        prompts = selected_sources(
            all_prompts, include_prompts, set(exclude.prompts if exclude else [])
        )
        groups = [("skills", all_skills, include_skills), ("prompts", all_prompts, include_prompts)]
        check_selection(groups, origin)
        if not (
            skills
            or prompts
            or roots
            or tool_server_names(table)
            or guard_names(table)
            or agent_names(table)
            or table.settings
        ):
            raise SystemExit(
                f"error: [user_library.{harness}] selected no skills, prompts, roots, "
                "MCP servers, guards, agents or settings."
            )
        if harness in READS_OTHER_SKILLS:
            skills, prompts = [], []
        selections[harness] = (skills, prompts)
    return {
        harness: (group.skills, group.prompts)
        for group in render_groups("home", selections)
        for harness in group.harnesses
    }


def user_roots(home: HomeConfig) -> dict[str, str]:
    """The root each harness renders into its home instruction file."""
    selected: dict[str, str] = {}
    for harness, table in user_library_tables(home).items():
        _skills, _prompts, roots, _scaffolds = collect_selection(
            table.model_dump(exclude_unset=True, exclude=HOME_ONLY), user_library_origin(harness)
        )
        if not roots:
            continue
        if len(roots) > 1:
            raise SystemExit(
                f"error: [user_library.{harness}] names {len(roots)} roots "
                f"({', '.join(sorted(roots))}). A home has one instruction file, so "
                "it takes one root."
            )
        selected[harness] = next(iter(roots))
    return selected


def render_user_expected(config: HomeConfig, home: Path) -> dict[Path, str]:
    """The complete user-scope output set, from the stablemate config's user_library."""
    if not user_library_tables(config):
        raise SystemExit(
            "error: no user library is configured. Add a "
            "[user_library.<harness>] table naming the skills to install for every "
            f"project — one of {', '.join(spec.name for spec in home_harnesses())} — to {config_path()}."
        )
    values = user_template_values(config)
    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")

    groups = render_groups("home", user_selections(config, all_skills, all_prompts))
    forms = skill_forms(groups)
    roots = user_roots(config)
    outputs: dict[Path, str] = {}
    for group in groups:
        renderer = Renderer(
            home,
            "",
            {},
            values,
            group.skills,
            group.prompts,
            scope="user",
            skill_forms=forms,
        )
        outputs.update(renderer.render({group.harnesses[0]: True}, set()))
        for harness in group.harnesses:
            if harness in roots:
                outputs.update(renderer.home_root(roots[harness], harness))
    outputs.update(guard_files(config, home))
    outputs.update(agent_files(config, home))
    return outputs


def selected_hooks(prefix: str, skills) -> list[SkillHook]:
    """Every hook the selected skills declare, in selection order."""
    hooks: list[SkillHook] = []
    for source in skills:
        data = frontmatter_mapping(source.path.read_text(encoding="utf-8"))
        hooks.extend(hooks_for(public_name(prefix, source), data))
    return hooks


def policy_hooks(policies) -> list[SkillHook]:
    """Every hook the selected policies declare, run from their installed folders."""
    hooks: list[SkillHook] = []
    for source in policies:
        data = frontmatter_mapping(source.path.read_text(encoding="utf-8"))
        hooks.extend(hooks_for(library_name(source), data, (POLICY_ROOT,)))
    return hooks


def _split_selection(
    config: ConfigLike, home_config: HomeConfig
) -> tuple[list[Source], dict[str, list[Source]]]:
    """The skills the repo selects, and per harness the user-library skills the repo neither selects nor excludes."""
    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")
    include, _, _, _ = collect_selection(config)
    exclude = excluded(config, "skills")
    repo_skills = selected_sources(all_skills, include, exclude)
    user_only = {
        harness: [
            source
            for source in skills
            if source not in repo_skills and not matches(source, exclude)
        ]
        for harness, (skills, _) in user_selections(
            home_config, all_skills, all_prompts
        ).items()
    }
    return repo_skills, user_only


@dataclass(frozen=True)
class ListedCheck:
    """A commit check resolved to the command that runs it."""

    owner: str
    command: str
    budget: float


def check_command(script: Path) -> str:
    """The shell command that runs *script*."""
    quoted = shlex.quote(str(script))
    return f"python3 {quoted}" if script.suffix == ".py" else quoted


def _source_checks(prefix: str, source: Source) -> list[CommitCheck]:
    data = frontmatter_mapping(source.path.read_text(encoding="utf-8"))
    return checks_for(public_name(prefix, source), data)


def _listed(check: CommitCheck, folders: Sequence[Path], source: Source) -> ListedCheck:
    script = next(
        (
            folder / check.owner / check.run
            for folder in folders
            if (folder / check.owner / check.run).is_file()
        ),
        source.path.parent / check.run,
    )
    return ListedCheck(check.owner, check_command(script), check.budget)


def selected_policies(config: ConfigLike) -> list[Source]:
    """The library policies *config*'s localInstructions name, each once."""
    lookup = build_policy_lookup(load_layered_sources("policy", "library", "policies"))
    keys = [
        name.replace(".", "-")
        for instruction in local_instructions(config)
        for name in instruction.policies
    ]
    return list(dict.fromkeys(lookup[key] for key in keys if key in lookup))


def commit_checks(
    repo: Path,
    config: ConfigLike,
    home_config: HomeConfig,
    home: Path,
    prefix: str,
) -> list[ListedCheck]:
    """Every commit check that applies to *repo*: its skills', its policies', then the user library's.

    A check runs from its installed copy, or from the library when nothing is installed yet.
    """
    repo_skills, user_only = _split_selection(config, home_config)
    listed: dict[tuple[str, str], ListedCheck] = {}
    repo_folders = [repo / root for root in SKILL_ROOTS]
    for source in repo_skills:
        for check in _source_checks(prefix, source):
            listed.setdefault(
                (check.owner, check.run), _listed(check, repo_folders, source)
            )
    policy_folders = [repo / POLICY_ROOT]
    for source in selected_policies(config):
        for check in _source_checks("", source):
            listed.setdefault(
                (check.owner, check.run), _listed(check, policy_folders, source)
            )
    for harness, skills in user_only.items():
        folders = [home / user_harness_dir(harness) / "skills"]
        for source in skills:
            for check in _source_checks("", source):
                listed.setdefault(
                    (check.owner, check.run), _listed(check, folders, source)
                )
    return list(listed.values())


def link_drift(path: Path, rel: str, link: Symlink) -> Drifted | None:
    """How the symlink at *path* departs from *link*, or None when it is in place."""
    expected = f"symlink to {link.target}"
    if path.is_symlink():
        actual_target = os.readlink(path)
        if actual_target == link.target:
            return None
        return Drifted(rel, "", expected, f"symlink to {actual_target}", is_link=True)
    kind = "a real folder" if path.is_dir() else "a real file"
    return Drifted(rel, "", expected, kind, is_link=True)


def check_outputs(
    repo: Path,
    outputs: Mapping[Path, Output],
    manager: str | None = None,
    managed: Managed = REPO_MANAGED,
) -> int:
    missing: list[str] = []
    changed: list[Drifted] = []
    extra: list[str] = []
    for path, content in outputs.items():
        rel = path.relative_to(repo).as_posix()
        if isinstance(content, Symlink):
            if not (path.is_symlink() or path.exists()):
                missing.append(rel)
            elif (drift := link_drift(path, rel, content)) is not None:
                changed.append(drift)
            continue
        expected = expected_text(content)
        if not path.exists():
            missing.append(rel)
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            changed.append(Drifted(rel, content, expected, actual))
        elif getattr(content, "executable", False) and not path.stat().st_mode & 0o111:
            changed.append(Drifted(rel, content, expected, actual))

    expected_paths = set(outputs)
    links = link_map(repo, managed)
    for rel in managed.dirs:
        owned = owned_files(repo / rel) + owned_links(repo / rel, links)
        for path in sorted(owned):
            if path not in expected_paths:
                extra.append(path.relative_to(repo).as_posix())
    named = list(managed.files)
    if managed.repo_scaffolding:
        named.append(LAUNCHER_CONTEXT_MANIFEST)
    for rel in named:
        path = repo / rel
        if path not in expected_paths and path.is_file():
            if is_assumed_owned(repo, path, managed) or is_owned(path, repo):
                extra.append(path.relative_to(repo).as_posix())

    fences = fence_drift(repo, manager) if manager is not None else []

    if missing or changed or extra or fences:
        print(report(missing, changed, extra, fences, managed.regenerate))
        return 1
    return 0


def install_outputs(
    repo: Path,
    outputs: Mapping[Path, Output],
    manager: str | None = None,
    managed: Managed = REPO_MANAGED,
) -> None:
    refuse_conflicts(repo, outputs, managed)
    remove_targets(repo, managed)
    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        write_output(path, content)
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
