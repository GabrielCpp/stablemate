"""Where things are: repo-root resolution, and the derived artifact paths.

Two kinds of thing live here, and both are here for the same reason — they were
duplicated verbatim across the YAML workflow's scripts, once per file, and a derivation
copied 30 times is a derivation nobody can change.

**Three repo-root resolvers, deliberately.** The scripts did not agree on how to find the
consuming repo, and the disagreement is behavioral rather than cosmetic: a run launched
from a subdirectory of a repo with no `agents.yml` resolves to a *different* root under
each. So all three are kept, named for what they actually do, and each ported node calls
the one its script called:

Every one of them takes the run's `repo_dir` as its argument and reads no environment
variable, per the rule in `workflows/README.md`: the consuming repo is an *input*, so it
travels down from `Workflow.repo_dir` through the state that calls the node. An empty
`repo_dir` still falls back to a walk — a visible, overridable default, unlike an ambient
variable.

* `survey_repo_root()` — `repo_dir`, else the first ancestor with `agents.yml` or a
  `docs/epics/` directory. Used by the surveyor's own scripts, and by most of the main
  graph's own nodes (`load_config`, `select_epic`, `select_story`, `validate_story`,
  `check_story_grounding`, `validate_coverage`, `record_attempt`, `prune_bullet`,
  `validate_artifacts`) — despite the name, which reads narrower than
  its use.
* `launch_repo_root()` — `repo_dir`, else the current directory, with no walk at
  all. Used by the parity surveyor and by the two tri-state verifiers
  (`verify_reconcile`, `verify_integrity`).
* `workhorse_workflows.kit.find_repo_root` — `repo_dir`, else the first ancestor with
  `agents.yml` or `.git`. Used by the git node (`commit_author`), and imported from the
  engine where it already lives rather than copied to a fourth spelling here.

Unifying them would be a narrowing, so it is a decision for the deletion loop and not
something the port does silently.

`check_story_feedback` no longer resolves a repo root at all: it polls the run's own
`inbox.jsonl` (`Workflow.run_dir`), not a file inside the consuming repo, so the fourth
resolver these scripts used (`feedback_repo_root`) has no caller left and is gone.

**The derived paths are repo-relative strings**, matching the config models, which hold
relative paths so a checkpoint survives a machine change. A node joins one onto a freshly
resolved root; only an `Await`'s context file needs an absolute `Path`, and the workflow
makes that join at the call site.

**Where a document lives is ostler's answer, not this module's.** Every derivation below
routes through `ostler.path`, so a repo that moved its epics with `docRoots:` is followed
rather than assumed away, and an epic folder numbered `0001-checkout` is found from the
bare slug the queue carries. What stays here is the part ostler has no opinion about: the
*filenames this workflow invented* — `_author-context.md`, `context.md`, `feedback.md` —
joined onto a directory ostler resolved. A join built the other way round, a literal
`docs/epics` in this file, is the failure the rule exists for: the second derivation never
learns about the config, and the symptom is a run writing where nothing reads.
"""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path


def survey_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as the surveyor's scripts resolved it.

    `repo_dir` is the run's input, carried down from the workflow; a script's own
    location points into the shared library, so it wins over any walk.
    """
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def launch_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as the parity surveyor's scripts resolved it: input, else cwd."""
    if repo_dir:
        return Path(repo_dir).resolve()
    return Path.cwd().resolve()


# ── derived artifact paths, all repo-relative ───────────────────────────────


def _rel(root: str | Path, target: Path) -> str:
    """*target* as a repo-relative posix string, or absolute if it is outside the repo."""
    root = Path(root)
    try:
        return target.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def epics_dir(root: str | Path) -> str:
    """Where epics live, repo-relative — ostler's answer, read from `docRoots:`.

    There is no parameter that can move it. One used to exist, and what it bought was a run
    writing epics into a tree `ostler backlog`, `coverage` and `doctor` do not read: two
    records of one location, with the copy winning.
    """
    return _rel(root, okf_path.epics_root_in(Path(root)))


def backlog_file(root: str | Path) -> str:
    """The worklist, repo-relative — where ostler keeps it.

    A run scoped to a subset of the work says so in `docRoots: backlog:`, where `ostler
    backlog` and `doctor` read the same answer. A parameter here could only disagree with
    them.
    """
    return _rel(root, okf_path.backlog_path_in(Path(root)))


def roadmaps_dir(root: str | Path) -> str:
    """Where roadmaps live, repo-relative — the location ostler was finally taught."""
    return _rel(root, okf_path.roadmaps_root_in(Path(root)))


def features_dir(root: str | Path) -> str:
    """The OKF feature book, repo-relative — the same directory `ostler coverage` reads."""
    return _rel(root, okf_path.features_root_in(Path(root)))


def epic_dir(root: str | Path, epic: str) -> str:
    """Where one epic's artifacts live, repo-relative — ostler resolves the folder.

    Epic folders are numbered (`0001-checkout`) while the queue, the prompts and an
    operator all name epics by bare slug, so this is a lookup rather than a join:
    `ostler.path` matches the slug against the folders on disk and returns the numbered
    one. A name that resolves to nothing comes back as the literal join, so a caller keeps
    reporting the name it was handed.
    """
    epics_root = Path(root) / epics_dir(root)
    return _rel(root, okf_path.epic_dir_under(epics_root, epic))


def story_dir(epic_dir_rel: str, slug: str) -> str:
    """Where one story's artifacts live, under its epic — `<epic>/stories/<slug>`.

    Only `seed_story` builds this itself. Everywhere else the story directory arrives
    from ostler (`next_story_report`), because ostler knows where it actually put the
    file and this derivation is only correct for stories ostler laid out.
    """
    return okf_path.story_dir_under(Path(epic_dir_rel), slug).as_posix()


def author_context(root: str | Path) -> str:
    """The run-wide operator context file: the whole-backlog gates write here.

    The *name* is this workflow's (`_author-context.md`, leading underscore so it sorts
    above the epics it sits beside); the directory is ostler's.
    """
    return f"{epics_dir(root)}/_author-context.md"


def epic_context(epic_dir_rel: str) -> str:
    """One epic's operator context file: the write-epic, split and coverage gates."""
    return f"{epic_dir_rel.rstrip('/')}/context.md"


def story_context(story_dir_rel: str) -> str:
    """One story's operator context file: the write-story gate."""
    return f"{story_dir_rel.rstrip('/')}/context.md"


__all__ = [
    "author_context",
    "backlog_file",
    "epic_context",
    "epic_dir",
    "epics_dir",
    "features_dir",
    "launch_repo_root",
    "roadmaps_dir",
    "story_context",
    "story_dir",
    "survey_repo_root",
]
