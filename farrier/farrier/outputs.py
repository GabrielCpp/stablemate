"""Full-render orchestration and the repo mutations that install it.

Turns an agents.yml config into the complete output set, checks it under
``--check``, and writes it — including the managed .gitignore and Makefile-include
upkeep. The write side of the pipeline the CLI drives.
"""
from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from farrier.drift import Drifted, report
from farrier.frontmatter import (
    frontmatter_mapping,
    mapping_include_readme,
    mapping_policy_names,
    mapping_prompt_names,
    mapping_skill_names,
)
from farrier.hook_managers import (
    HOOK_RUNNER,
    LEFTHOOK_INCLUDE,
    configured_manager,
    fence_drift,
    install_manager,
    lefthook_include_text,
    runner_text,
)
from farrier.hooks import GATE_SCRIPT, ensure_qa_gitignore
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_ROOT_MAKEFILE,
)
from farrier._vendor.stablemate_core.config import config_path
from farrier.layers import available_names
from farrier.naming import repo_prefix
from farrier.ownership import is_owned, owned_files, sweep
from farrier.renderer import Rendered, Renderer
from farrier.selection_errors import (
    suggestions,
    unknown_selection_error,
)
from farrier.skill_hooks import SkillHook, hooks_for
from farrier.sources import (
    collect_selection,
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


#: The directories farrier renders into. It scans these for its *own* files — see
#: ``farrier.ownership`` — rather than treating everything inside them as its own, so a
#: hand-written skill can sit next to the generated ones and survive an install.
#:
#: ``.agents`` is deliberately not listed whole: ``.agents/runs`` holds workflow output
#: that nothing here generates and nothing here should be walking.
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

#: Single files farrier renders outside any managed directory. Tag-checked one by one,
#: for the same reason: the root instruction file in particular is a name a repo may
#: well have written by hand before it ever adopted farrier.
MANAGED_FILES = [
    ".github/copilot-instructions.md",
    # Generated launcher scaffolding. The root Makefile is intentionally NOT listed: a
    # user may hand-author it, and the installer must never delete or overwrite it.
    LAUNCHER_AGENTS_MK,
    # The hook side. Listed so switching `hooks.manager` — or turning it off with
    # `none` — takes the previous manager's files with it, rather than leaving a runner
    # that nothing calls and `--check` then reports as `extra`.
    LEFTHOOK_INCLUDE,
]

#: Paths farrier owns by convention because they have nowhere to carry a mark. A JSON
#: manifest has no comment syntax, and a `generated_by` key inside its object would
#: change the document every reader parses. These are deleted and overwritten
#: unconditionally, and they are exempt from the conflict check for the same reason.
ASSUMED_OWNED = [
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    # Per-assistant context manifests are emitted only for currently-enabled
    # assistants, so a disabled assistant's stale manifest is cleared by the glob.
    ".agents/agents-context.*.json",
]


@dataclass(frozen=True)
class Managed:
    """What one install scope owns — the directories it sweeps and the files it names.

    Repo scope and user scope render into different trees and own different things: a
    user-scope install writes skills and commands and nothing else, so it has no
    launcher, no hook runner and no root instruction file to dispose of. Passing the
    set in makes that a parameter of the scope rather than four module globals every
    caller has to remember not to apply.
    """

    dirs: tuple[str, ...]
    files: tuple[str, ...] = ()
    assumed: tuple[str, ...] = ()
    #: Whether the scope owns a repo's surroundings — the managed .gitignore rules and
    #: the launcher include. A home directory is not a checkout: it usually is not a git
    #: repo at all, and writing ignore rules into one that is would be farrier editing a
    #: file it was never pointed at.
    repo_scaffolding: bool = True


REPO_MANAGED = Managed(tuple(MANAGED_DIRS), tuple(MANAGED_FILES), tuple(ASSUMED_OWNED))

#: User scope, relative to the user's home. Every entry is a directory the harness
#: itself reads for every project; nothing outside them is farrier's to touch, which is
#: why the file and assumed-owned lists are empty rather than inherited.
USER_MANAGED = Managed(
    (".claude/skills", ".claude/commands", ".codex/skills", ".copilot/skills"),
    repo_scaffolding=False,
)


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


def is_assumed_owned(
    repo: Path, path: Path, managed: Managed = REPO_MANAGED
) -> bool:
    """True when *path* is one farrier owns by convention rather than by a mark."""
    rel = path.relative_to(repo).as_posix()
    return any(fnmatch(rel, pattern) for pattern in managed.assumed)


def conflicts(
    repo: Path, outputs: dict[Path, str], managed: Managed = REPO_MANAGED
) -> list[str]:
    """The paths farrier is about to write that are held by files it did not generate.

    Repo-root-relative, sorted, and complete: an operator fixing these wants the whole
    list, not the first one, because each fix is a rename or a delete they have to
    decide on individually.

    An output whose own render declares itself assumed-owned is exempt, for the reason
    the ``ASSUMED_OWNED`` paths are: the aggregated AGENTS.md deliberately carries no
    banner, so on the second install farrier would read the file it wrote itself as a
    hand-written rules file and refuse. The declaration rides on the render rather than
    on a path pattern because which directories get one is the repo's
    ``localInstructions`` mapping, not a fixed list farrier could name here.
    """
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
    """Abort the install when any output path holds a file farrier does not own.

    Before anything is deleted or written, so a refusal leaves the repo exactly as it
    was. Overwriting was the old behaviour and it is not a choice farrier gets to make:
    the file is somebody's work, and the only two answers — keep it under another name,
    or throw it away — are both theirs.
    """
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
    """Delete farrier's previous output — and only farrier's.

    A scan for the generated-by mark rather than an ``rmtree`` of every managed
    directory. What that buys is the whole point of the tag: a hand-written skill in
    `.claude/skills/` is somebody's, and the install that used to remove it did so
    silently, leaving nothing to notice.

    No legacy path list rides alongside. Every markdown file farrier has generated
    carries either the `metadata:` block or the DO-NOT-EDIT banner, so an older
    install's leftovers are found by the same scan; anything so old it carries
    neither is reported as a conflict, by name, rather than deleted on a guess.
    """
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
    # Every policy in every layer, unfiltered. Policies have no `packs:`/`skills:`-style
    # selection because they are not installed anywhere: one exists in a repo exactly
    # when a localInstructions mapping names it, so "available but unselected" is not a
    # state a policy can be in, and an `exclude.policies` would have nothing to subtract
    # from. Overlay shadowing still applies — load_layered_sources gives the higher
    # layer's file for a shared id.
    all_policies = load_layered_sources("policy", "library", "policies")
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
        repo,
        prefix,
        repo_config,
        collect_template_values(config),
        skills,
        prompts,
        all_policies,
    )
    outputs = renderer.render(agents, roots)

    for mapping in config.get("localInstructions", []) or []:
        skill_names = mapping_skill_names(mapping)
        prompt_names = mapping_prompt_names(mapping)
        policy_names = mapping_policy_names(mapping)
        if not skill_names and not prompt_names and not policy_names:
            raise SystemExit(
                "A localInstructions entry must select at least one source "
                "(`policy`/`policies`, `skill`/`skills` and/or `prompt`/`prompts`)"
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
                policy_names,
            )
            if agents.get("claude"):
                claude_path = directory / "CLAUDE.md"
                outputs[claude_path] = renderer.render_claude_pointer(
                    skill_names,
                    claude_path,
                    prompt_names,
                    include_readme and claude_only,
                    policy_names,
                )

    # The hook side of the install. Both files are farrier's whole, which is what lets
    # the region spliced into the user's manager config stay one unchanging reference:
    # everything per-repo (which skills declared a hook, what lefthook must run) lives
    # here instead of inside their file.
    manager = configured_manager(config, repo)
    if manager != "none":
        outputs[repo / HOOK_RUNNER] = Rendered(
            runner_text(selected_hooks(prefix, skills)), executable=True
        )
    if manager == "lefthook":
        outputs[repo / LEFTHOOK_INCLUDE] = Rendered(lefthook_include_text())

    return outputs


def render_user_expected(config: dict[str, Any], home: Path) -> dict[Path, str]:
    """The complete user-scope output set, from the stablemate config's user_library.

    The user-scope sibling of :func:`render_expected`. Everything below the selection is
    the same machinery — the same layer stack, the same source loading, the same
    renderer — so a skill installs identically whichever scope brought it in. What
    differs is above it: no repo, so no repo prefix, no `agents:` list (each harness is
    named by having a table), no roots, no localInstructions and no hooks. A hook is a
    repo's git config; there is nothing at user scope for one to attach to.
    """
    selections = user_library_tables(config)
    if not selections:
        raise SystemExit(
            "error: no user library is configured. Add a "
            "[user_library.<harness>] table naming the skills to install for every "
            f"project — one of {', '.join(HARNESSES)} — to {config_path()}."
        )
    values = user_template_values(config)
    all_skills = load_layered_sources("skill", "library", "skills")
    all_prompts = load_layered_sources("prompt", "library", "prompts")

    outputs: dict[Path, str] = {}
    for harness, table in selections.items():
        include_skills, include_prompts, roots, _scaffolds = collect_selection(table)
        if roots:
            raise SystemExit(
                f"error: [user_library.{harness}] names roots. A root renders into a "
                "repo's always-on instruction file, and no harness reads one from the "
                "home directory."
            )
        if include_prompts and harness != "claude":
            raise SystemExit(
                f"error: [user_library.{harness}] names prompts. Claude is the only "
                "harness with a personal command directory (~/.claude/commands), so "
                "prompts are Claude-only at user scope."
            )
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
        renderer = Renderer(home, "", {}, values, skills, prompts, scope="user")
        outputs.update(renderer.render({harness: True}, set()))
    return outputs


def selected_hooks(prefix: str, skills) -> list[SkillHook]:
    """Every hook the selected skills declare, in selection order.

    Read off the *library source*, not off the rendered copy: the rendered SKILL.md is
    what a hand-edit would have reached, and a hook installed because somebody added a
    `hooks:` key to a generated file is a hook nothing regenerates.
    """
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
            # Identical text but not runnable — a `./scripts/x.sh` in a skill fails at
            # the shell, so --check has to call it out rather than report the repo current.
            changed.append(Drifted(rel, content, expected, actual))

    # Neither `.agents/workflows` nor `.agents/local.compose.yaml` is scanned. Farrier
    # rendered a workflow's YAML tree into the first and a per-workflow compose override
    # into the second while workflows were its concern; it emits neither now, so scanning
    # them would only report a leftover from an older install as `extra:` — a --check
    # failure the operator cannot fix by re-rendering. `remove_targets` still deletes the
    # compose override, which is where a leftover is actually disposed of.
    # `extra` means "farrier generated this and no longer would" — a stale output the
    # next install removes. An UNTAGGED file in a managed directory is not that: it is
    # somebody's own file, sitting where farrier also writes, and install leaves it
    # alone. Reporting it as drift would fail --check with nothing to fix.
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

    # The fenced region inside a file farrier does not own is checked the same way and
    # for the same reason: `install` rewrites it, so an edit there is an edit about to
    # be lost. Only when the caller knows which manager is configured — `check_outputs`
    # is also called with a bare output map by callers that have no config.
    fences = fence_drift(repo, manager) if manager is not None else []

    if missing or changed or extra or fences:
        print(report(missing, changed, extra, fences))
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
    # Workflow runs write logs/artifacts under .agents/runs (see workhorse's --runs-dir
    # RUNS_DIR). Keep them out of version control. Guarded on the launcher because the
    # block also covers the adapter directories rendered alongside it.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_agents_gitignore(repo):
        print("Updated .agents .gitignore rules")
    # The staged-files gate is text until something runs it, and the ignore line is what
    # keeps the artifacts out of the index before the hook ever has to refuse them. Both
    # are guarded on the gate script itself being among the outputs: a repo that did not
    # select the ostler skill has not asked for either.
    if managed.repo_scaffolding and any(
        path.name == Path(GATE_SCRIPT).name for path in outputs
    ):
        if ensure_qa_gitignore(repo):
            print("Updated QA evidence .gitignore rules")
    # Splice farrier's one fenced entry into the repo's hook manager. Last, because the
    # command inside the fence runs the files written above — wiring a hook to a runner
    # that is not there yet would make the window between the two a failing commit.
    if manager is not None:
        for line in install_manager(repo, manager):
            print(line)
    # When the repo already had a root Makefile, farrier left it untouched above —
    # wire the generated launcher into it so its agent targets are reachable.
    if (repo / LAUNCHER_AGENTS_MK) in outputs and ensure_makefile_include(repo):
        print("Added agent launcher include to root Makefile")
