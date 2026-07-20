"""Full-render orchestration and the repo mutations that install it.

Turns an agents.yml config into the complete output set, checks it under
``--check``, and writes it — including the managed .gitignore and Makefile-include
upkeep. The write side of the pipeline the CLI drives.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from farrier.frontmatter import mapping_skill_names
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_ROOT_MAKEFILE,
)
from farrier.naming import kebab
from farrier.renderer import Renderer
from farrier.selection_errors import (
    suggestions,
    unknown_selection_error,
)
from farrier.sources import (
    collect_selection,
    load_layered_sources,
    selected_sources,
    unmatched_patterns,
)
from farrier.workflows import (
    collect_template_values,
    resolve_workflow_meta,
    should_skip_workflow_file,
)


TARGET_DIRS = [
    ".agents/skills",
    ".agents/prompts",
    ".claude/skills",
    ".claude/commands",
    ".github/instructions",
    ".github/prompts",
]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def normalize_agents(config: dict[str, Any]) -> dict[str, bool]:
    agents = config.get("agents") or {}
    if isinstance(agents, list):
        return {name: name in agents for name in ["codex", "claude", "copilot"]}
    return {
        name: bool(agents.get(name, False)) for name in ["codex", "claude", "copilot"]
    }


def remove_targets(repo: Path) -> None:
    for rel in TARGET_DIRS:
        path = repo / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
        ".agents/workflows",
        # Generated launcher scaffolding (always owned by the installer). The
        # root Makefile is intentionally NOT listed: a user may hand-author it,
        # and the installer must never delete or overwrite it.
        LAUNCHER_AGENTS_MK,
        LAUNCHER_COMPOSE,
        LAUNCHER_CONTEXT_MANIFEST,
    ]:
        path = repo / rel
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    # Per-assistant context manifests (agents-context.<assistant>.json) are emitted
    # only for currently-enabled assistants, so clear any prior ones by glob — a
    # disabled assistant's stale manifest must not linger.
    agents_dir = repo / ".agents"
    if agents_dir.is_dir():
        for path in agents_dir.glob("agents-context.*.json"):
            if path.is_file():
                path.unlink()


def check_selection(
    groups: list[tuple[str, list, set[str]]],
) -> None:
    """Fail on any selection entry that names a library file which does not exist.

    ``groups`` is ``[(kind, all_sources, include_patterns), ...]``. Literal names that match
    nothing are typos and hard-fail; globs that match nothing are filters that selected
    nothing, which is legitimate, so they are reported as a warning instead. Every miss across
    every group is collected before raising so one run surfaces them all rather than making the
    operator fix them one at a time.
    """
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


def render_expected(config: dict[str, Any], repo: Path) -> dict[Path, str]:
    repo_config = config.get("repo") or {}
    prefix = kebab(
        str(repo_config.get("prefix") or repo_config.get("name") or repo.name)
    )
    agents = normalize_agents(config)
    if not any(agents.values()):
        raise SystemExit("No agents selected in config")

    (
        include_skills,
        include_prompts,
        roots,
        _scaffold_ids,  # consumed by `farrier scaffold`, not by install
        workflows,
    ) = collect_selection(config)
    exclude = config.get("exclude") or {}

    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")
    skills = selected_sources(
        all_skills, include_skills, set(exclude.get("skills", []) or [])
    )
    prompts = selected_sources(
        all_prompts, include_prompts, set(exclude.get("prompts", []) or [])
    )
    # Fail loudly on a selection entry that names a file the library does not have, the same
    # way `packs` and `workflows` already do. Selection is a filter, so without this a typo
    # silently yields a repo missing a skill it declared — and the symptom is an agent running
    # unskilled while every gate still reports success.
    check_selection(
        [("skills", all_skills, include_skills), ("prompts", all_prompts, include_prompts)]
    )
    if not skills and not prompts and not workflows:
        raise SystemExit(
            "Selected packs did not match any skills, prompts, or workflows"
        )

    renderer = Renderer(
        repo, prefix, repo_config, collect_template_values(config), skills, prompts
    )
    workflow_meta = resolve_workflow_meta(
        config, repo, str(repo_config.get("name") or kebab(repo.name))
    )
    workflow_meta["repo_src_default"] = repo.as_posix()
    workflow_meta["repo_config_default"] = (repo / "agents.yml").as_posix()
    outputs = renderer.render(agents, roots, workflows, workflow_meta)

    for mapping in config.get("localInstructions", []) or []:
        skill_names = mapping_skill_names(mapping)
        # `includeReadme` controls how a sibling README.md is folded in:
        #   inline (default) — copy the rendered README body into the file
        #   import           — reference it via Claude's `@README.md` directive
        #   none             — omit it
        # Booleans are accepted too: true → inline, false → none.
        readme_flag = mapping.get("includeReadme", "inline")
        if readme_flag is True:
            readme_mode = "inline"
        elif readme_flag is False:
            readme_mode = "none"
        else:
            readme_mode = str(readme_flag)
        if readme_mode not in ("inline", "import", "none"):
            raise SystemExit(
                f"localInstructions.includeReadme must be one of inline/import/none (got {readme_flag!r})"
            )
        for rel in mapping.get("paths", []) or []:
            directory = repo / rel
            if not directory.exists():
                raise SystemExit(
                    f"Local instruction path does not exist: {rel} "
                    "(create it first — e.g. `farrier scaffold <id>`)"
                )
            if agents.get("codex"):
                for filename in ["AGENTS.md", "CODEX.md"]:
                    output_path = directory / filename
                    outputs[output_path] = renderer.render_local_instruction(
                        skill_names, "codex", output_path, readme_mode
                    )
            if agents.get("claude"):
                output_path = directory / "CLAUDE.md"
                outputs[output_path] = renderer.render_local_instruction(
                    skill_names, "claude", output_path, readme_mode
                )

    return outputs


def check_outputs(repo: Path, outputs: dict[Path, str]) -> int:
    missing: list[str] = []
    changed: list[str] = []
    extra: list[str] = []
    for path, content in outputs.items():
        expected = content.rstrip() + "\n"
        if not path.exists():
            missing.append(path.relative_to(repo).as_posix())
        elif path.read_text(encoding="utf-8") != expected:
            changed.append(path.relative_to(repo).as_posix())

    expected_paths = set(outputs)
    for rel in TARGET_DIRS + [".agents/workflows"]:
        target = repo / rel
        if not target.exists():
            continue
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            if rel == ".agents/workflows" and should_skip_workflow_file(path, target):
                continue
            if path not in expected_paths:
                extra.append(path.relative_to(repo).as_posix())
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
        LAUNCHER_AGENTS_MK,
        LAUNCHER_COMPOSE,
        LAUNCHER_CONTEXT_MANIFEST,
    ]:
        path = repo / rel
        if path.exists() and path not in expected_paths:
            extra.append(path.relative_to(repo).as_posix())

    if missing or changed or extra:
        for rel in missing:
            print(f"missing: {rel}")
        for rel in changed:
            print(f"changed: {rel}")
        for rel in extra:
            print(f"extra: {rel}")
        return 1
    return 0


def ensure_gitignore_entry(repo: Path, entry: str) -> bool:
    """Append `entry` to the repo's .gitignore if not already ignored.

    Idempotent: returns True only when the file was actually modified. Matches
    on the exact stripped line so trailing-slash or comment variants don't
    cause duplicates. Creates .gitignore if it does not exist. When appending to
    a non-empty file, a blank line is inserted before the entry so it is visually
    separated from the repo's own existing rules rather than glued onto them.
    """
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if entry in {line.strip() for line in existing.splitlines()}:
        return False
    if not existing:
        prefix = ""
    else:
        prefix = existing if existing.endswith("\n") else existing + "\n"
        if not prefix.endswith("\n\n"):
            prefix += "\n"
    gitignore.write_text(f"{prefix}{entry}\n", encoding="utf-8")
    return True


# Managed .gitignore rules for the generated `.agents/` directory. Generated
# adapter outputs (context manifests, runs/, skills/, prompts/, workflows/) are
# ignored, but hand-authored files are tracked: the launcher Makefile and prompt
# *flavor* overrides under `.agents/flavors/`. `/.agents/*` matches only the direct
# children one level deep, so the negated `flavors/` subtree's deeper files stay
# tracked. This supersedes a bare `.agents` line, which ignored the whole directory
# and stopped git descending — making `.agents/flavors/` impossible to track.
AGENTS_GITIGNORE_BLOCK = (
    "/.agents/*",
    "!/.agents/agents.mk",
    "!/.agents/flavors/",
)


def ensure_agents_gitignore(repo: Path) -> bool:
    """Install/upgrade the managed `.agents/` ignore block in the repo's .gitignore.

    Idempotent: returns True only when the file was actually modified. Strips any
    legacy standalone `.agents` wholesale-ignore line (so git descends into
    `.agents/` and the hand-authored `flavors/` subtree can be tracked) and any
    prior copy of the managed block, then re-appends the block at the end.
    """
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    managed = set(AGENTS_GITIGNORE_BLOCK) | {".agents", ".agents/", "/.agents"}
    kept = [ln for ln in existing.splitlines() if ln.strip() not in managed]
    body = "\n".join(kept).rstrip("\n")
    prefix = f"{body}\n\n" if body else ""
    desired = prefix + "\n".join(AGENTS_GITIGNORE_BLOCK) + "\n"
    if desired == existing:
        return False
    gitignore.write_text(desired, encoding="utf-8")
    return True


MAKEFILE_INCLUDE_MARKER = "# >>> farrier: agent launcher include (generated) >>>"
MAKEFILE_INCLUDE_END = "# <<< farrier: agent launcher include <<<"


def ensure_makefile_include(repo: Path) -> bool:
    """Ensure the repo's existing root Makefile includes the generated launcher.

    When a repo already ships its own root Makefile, farrier must not clobber it —
    but the agent targets (`agent-run`/`agent-install`/`agent-check`/…) live in the
    generated ``.agents/agents.mk``, so the root Makefile has to ``include`` it to
    surface them. This appends a marked ``include .agents/agents.mk`` block at the
    *end* of the file, so the repo's own first target stays the default goal.

    Idempotent: returns True only when the file was modified. No-ops when the
    include line is already present, or when no root Makefile exists (the caller
    writes a thin one carrying the include in that case).
    """
    makefile = repo / LAUNCHER_ROOT_MAKEFILE
    if not makefile.exists():
        return False
    include_line = f"include {LAUNCHER_AGENTS_MK}"
    existing = makefile.read_text(encoding="utf-8")
    if include_line in {line.strip() for line in existing.splitlines()}:
        return False
    prefix = existing if existing.endswith("\n") else existing + "\n"
    if not prefix.endswith("\n\n"):
        prefix += "\n"
    block = (
        f"{MAKEFILE_INCLUDE_MARKER}\n"
        "# Surfaces agent-run / agent-install / agent-check etc. from the generated\n"
        "# launcher. Re-created by `farrier install`; remove this block to opt out.\n"
        f"{include_line}\n"
        f"{MAKEFILE_INCLUDE_END}\n"
    )
    makefile.write_text(prefix + block, encoding="utf-8")
    return True


def install_outputs(repo: Path, outputs: dict[Path, str]) -> None:
    remove_targets(repo)
    for path, content in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
        write_text(path, content)
    # Workflow runs write logs/artifacts under .agents/runs (see render_agents_mk
    # RUNS_DIR). Keep them out of version control. Only relevant when a workflow
    # launcher was generated.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_agents_gitignore(repo):
        print("Updated .agents .gitignore rules")
    # When the repo already had a root Makefile, farrier left it untouched above —
    # wire the generated launcher into it so its agent targets are reachable.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_makefile_include(repo):
        print("Added agent launcher include to root Makefile")
