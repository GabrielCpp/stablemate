"""Full-render orchestration and the repo mutations that install it.

Turns an agents.yml config into the complete output set, checks it under
``--check``, and writes it — including the managed .gitignore and Makefile-include
upkeep. The write side of the pipeline the CLI drives.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from farrier.frontmatter import (
    mapping_include_readme,
    mapping_prompt_names,
    mapping_skill_names,
)
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_ROOT_MAKEFILE,
)
from farrier.layers import available_names
from farrier.naming import repo_prefix
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
from farrier.template_values import collect_template_values


TARGET_DIRS = [
    ".agents/skills",
    ".agents/prompts",
    ".claude/skills",
    ".claude/commands",
    ".github/instructions",
    ".github/prompts",
]


def expected_text(content: str) -> str:
    """The exact bytes *content* installs as — the one place the rule is stated.

    ``--check`` compares against what ``write_text`` would write, so the two must agree
    by construction rather than by both remembering to ``rstrip``. Verbatim outputs
    (bundled scripts and non-markdown references) are exempt: their trailing whitespace
    is theirs, and a here-doc or fixture that ends in a blank line means it.
    """
    if getattr(content, "verbatim", False):
        return content
    return content.rstrip() + "\n"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected_text(content), encoding="utf-8")
    # A bundled script exists to be run, and a skill that says `./scripts/check.sh`
    # is wrong the moment the installed copy is not executable. Mirrors chmod +x
    # for the owner/group/other read bits already on the file.
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


def remove_targets(repo: Path) -> None:
    for rel in TARGET_DIRS:
        path = repo / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
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
    prefix = repo_prefix(repo)
    agents = normalize_agents(config)
    if not any(agents.values()):
        raise SystemExit("No agents selected in config")

    (
        include_skills,
        include_prompts,
        roots,
        _scaffold_ids,  # consumed by `farrier scaffold`, not by install
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
    # way `packs` already does. Selection is a filter, so without this a typo
    # silently yields a repo missing a skill it declared — and the symptom is an agent running
    # unskilled while every gate still reports success.
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

    renderer = Renderer(
        repo, prefix, repo_config, collect_template_values(config), skills, prompts
    )
    outputs = renderer.render(agents, roots)

    for mapping in config.get("localInstructions", []) or []:
        skill_names = mapping_skill_names(mapping)
        prompt_names = mapping_prompt_names(mapping)
        if not skill_names and not prompt_names:
            raise SystemExit(
                "A localInstructions entry must select at least one source "
                "(`skill`/`skills` and/or `prompt`/`prompts`)"
            )
        include_readme = mapping_include_readme(mapping)
        claude_only = bool(agents.get("claude")) and not (
            agents.get("codex") or agents.get("copilot")
        )
        # The aggregated body is written once, to AGENTS.md — the one name every
        # harness reads natively. Its template helpers resolve against the shared
        # `.agents/` layout unless Claude is the only adapter, because a link into
        # `.claude/skills/` in a file codex also reads points at a copy codex was
        # never given.
        target = "claude" if claude_only else "codex"
        for rel in mapping.get("paths", []) or []:
            directory = repo / rel
            if not directory.exists():
                raise SystemExit(
                    f"Local instruction path does not exist: {rel} "
                    "(create it first — e.g. `farrier scaffold <id>`)"
                )
            agents_path = directory / "AGENTS.md"
            # Claude alone can pull the README in by reference, which keeps the
            # always-loaded file lean. With another adapter present the body has
            # to be copied into AGENTS.md — and then Claude gets it through the
            # import chain, so importing it again would load it twice.
            outputs[agents_path] = renderer.render_local_instruction(
                skill_names,
                target,
                agents_path,
                include_readme and not claude_only,
                prompt_names,
            )
            if agents.get("claude"):
                claude_path = directory / "CLAUDE.md"
                outputs[claude_path] = renderer.render_claude_pointer(
                    skill_names,
                    claude_path,
                    prompt_names,
                    include_readme and claude_only,
                )

    return outputs


def check_outputs(repo: Path, outputs: dict[Path, str]) -> int:
    missing: list[str] = []
    changed: list[str] = []
    extra: list[str] = []
    for path, content in outputs.items():
        expected = expected_text(content)
        if not path.exists():
            missing.append(path.relative_to(repo).as_posix())
        elif path.read_text(encoding="utf-8") != expected:
            changed.append(path.relative_to(repo).as_posix())
        elif getattr(content, "executable", False) and not path.stat().st_mode & 0o111:
            # Identical text but not runnable — a `./scripts/x.sh` in a skill fails at
            # the shell, so --check has to call it out rather than report the repo current.
            changed.append(path.relative_to(repo).as_posix())

    # Neither `.agents/workflows` nor `.agents/local.compose.yaml` is scanned. Farrier
    # rendered a workflow's YAML tree into the first and a per-workflow compose override
    # into the second while workflows were its concern; it emits neither now, so scanning
    # them would only report a leftover from an older install as `extra:` — a --check
    # failure the operator cannot fix by re-rendering. `remove_targets` still deletes the
    # compose override, which is where a leftover is actually disposed of.
    expected_paths = set(outputs)
    for rel in TARGET_DIRS:
        target = repo / rel
        if not target.exists():
            continue
        for path in sorted(item for item in target.rglob("*") if item.is_file()):
            if path not in expected_paths:
                extra.append(path.relative_to(repo).as_posix())
    for rel in [
        ".github/copilot-instructions.md",
        ".github/agents/copilot-instructions.md",
        LAUNCHER_AGENTS_MK,
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


# Managed .gitignore rules for the generated `.agents/` directory.
#
# **The block names what to ignore, not what to keep.** It used to be an
# exclude-everything list — `/.agents/*` plus a negation per survivor — and that
# shape is wrong by default: anything a *later* tool starts writing under
# `.agents/` is born ignored, and nobody notices until the file that should have
# been committed isn't. ostler's `.agents/ids.json` is the case that proved it —
# the id registry is repo state every clone and worktree has to agree on, and the
# catch-all silently kept it out of every commit.
#
# So each generated or ephemeral path is listed explicitly, and everything else
# under `.agents/` is tracked by default. The cost is that a new *generated*
# output has to be added here; that failure is loud (a diff full of machine
# output at review time) where the old one was silent.
#
# The entries carry no leading slash. Every one of them has a slash in the middle,
# and git anchors any pattern containing a non-trailing separator to the directory
# holding the .gitignore — so `/.agents/runs/` and `.agents/runs/` match exactly
# the same paths. The leading slash was noise that read as though it meant
# something.
#
# The rendered adapters — `.agents/skills/` and `.agents/prompts/` — are *not*
# listed. They are generated, but so are `.claude/skills/` and `.github/prompts/`,
# and those have always been committed. An adapter directory is what a checkout of
# this repo gives an assistant *before* anyone runs farrier; ignoring one CLI's
# copy while committing another's meant codex users got nothing from a fresh clone,
# and `install --check` had no committed baseline to diff against in CI.
AGENTS_GITIGNORE_BLOCK = (
    ".agents/runs/",              # run logs, pids and copied-out artifacts
    # Per-run git worktrees, and the staged credentials copy beside each. Both are
    # emphatically not repo content: a worktree is a second checkout of this very
    # repo (committing it nests the repo in itself), and the credentials copy is a
    # secret. This entry is load-bearing rather than tidy.
    ".agents/worktrees/",
    ".agents/workflows/",         # legacy rendered workflow trees
    ".agents/operator/",          # per-run operator gate context files
    ".agents/local.compose.yaml",  # generated compose override
    ".agents/agents-context.json",  # generated context manifest
    ".agents/agents-context.*.json",  # …and its per-CLI variants
)


#: Lines a previous installer wrote that this block replaces. They are stripped
#: rather than left in place because leaving one behind keeps ignoring a path the
#: current block deliberately tracks. Three generations are represented: the
#: wholesale `.agents` ignore, the `/.agents/*` exclude-list whose negations are
#: meaningless without it, and the slash-prefixed spelling of the current block —
#: including the two rendered-adapter entries that are no longer ignored at all.
_SUPERSEDED_GITIGNORE_LINES = (
    ".agents",
    ".agents/",
    "/.agents",
    "/.agents/*",
    "!/.agents/agents.mk",
    "!/.agents/flavors/",
    ".agents/runs",
    ".agents/skills/",
    ".agents/prompts/",
    "/.agents/runs/",
    "/.agents/worktrees/",
    "/.agents/skills/",
    "/.agents/prompts/",
    "/.agents/workflows/",
    "/.agents/operator/",
    "/.agents/local.compose.yaml",
    "/.agents/agents-context.json",
    "/.agents/agents-context.*.json",
)


def ensure_agents_gitignore(repo: Path) -> bool:
    """Install/upgrade the managed `.agents/` ignore block in the repo's .gitignore.

    Idempotent: returns True only when the file was actually modified. Strips the
    lines of every earlier spelling of this block — the legacy standalone `.agents`
    wholesale-ignore line, and the `/.agents/*` + negations exclude-list that
    replaced it — then re-appends the current block at the end.
    """
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    managed = set(AGENTS_GITIGNORE_BLOCK) | set(_SUPERSEDED_GITIGNORE_LINES)
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
    but the agent targets (`agent-install`/`agent-check`) live in the generated
    ``.agents/agents.mk``, so the root Makefile has to ``include`` it to
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
        "# Surfaces agent-install / agent-check from the generated\n"
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
    # Workflow runs write logs/artifacts under .agents/runs (see workhorse's --runs-dir
    # RUNS_DIR). Keep them out of version control. Guarded on the launcher because the
    # block also covers the adapter directories rendered alongside it.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_agents_gitignore(repo):
        print("Updated .agents .gitignore rules")
    # When the repo already had a root Makefile, farrier left it untouched above —
    # wire the generated launcher into it so its agent targets are reachable.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_makefile_include(repo):
        print("Added agent launcher include to root Makefile")
