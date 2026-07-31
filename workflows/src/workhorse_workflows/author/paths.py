"""Where things are: repo-root resolution, and the derived artifact paths.

Two kinds of thing live here, and both are here for the same reason — they were
duplicated verbatim across the YAML workflow's scripts, once per file, and a derivation
copied 30 times is a derivation nobody can change.

**Four repo-root resolvers, deliberately.** The scripts did not agree on how to find the
consuming repo, and the disagreement is behavioral rather than cosmetic: a run launched
from a subdirectory of a repo with no `agents.yml` resolves to a *different* root under
each. So all four are kept, named for what they actually do, and each ported node calls
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
  `prune_backlog`, `validate_artifacts`) — despite the name, which reads narrower than
  its use.
* `launch_repo_root()` — `repo_dir`, else the current directory, with no walk at
  all. Used by the parity surveyor and by the two tri-state verifiers
  (`verify_reconcile`, `verify_integrity`).
* `workhorse.scriptutil.find_repo_root` — `repo_dir`, else the first ancestor with
  `agents.yml` or `.git`. Used by the three git/GitHub nodes (`branch_author`,
  `commit_author`, `open_author_pr`), and imported from the engine where it already
  lives rather than copied to a fourth spelling here.
* `feedback_repo_root()` — `repo_dir`, else the current directory *if* it looks
  like a repo, else the first ancestor with `agents.yml` or `.git`. `check_feedback.py`
  alone resolved this way; `check_story_feedback` keeps it.

Unifying them would be a narrowing, so it is a decision for the deletion loop and not
something the port does silently.

**The derived paths are repo-relative strings**, matching the config models, which hold
relative paths so a checkpoint survives a machine change. A node joins one onto a freshly
resolved root; only an `Await`'s context file needs an absolute `Path`, and the workflow
makes that join at the call site.
"""
from __future__ import annotations

from pathlib import Path


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


def feedback_repo_root(repo_dir: str | Path = "") -> Path:
    """The consuming repo, as `check_feedback.py` alone resolved it.

    The difference from `survey_repo_root` is the first step: the current directory is
    accepted if it carries *any* of the three markers, and only then are its parents
    walked, looking for the two git-ish ones.
    """
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    if (here / "docs" / "epics").is_dir() or (here / "agents.yml").exists() or (here / ".git").exists():
        return here
    for candidate in here.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


# ── derived artifact paths, all repo-relative ───────────────────────────────


def epic_dir(epics_dir: str, epic: str) -> str:
    """Where one epic's artifacts live, under the configured epics directory.

    `epic` must be the directory name ostler created — epic folders are numbered
    (`0001-checkout`), so joining a bare slug here names a folder that does not exist.
    `select_epic` resolves the queue entry through `ostler path epic` before this is
    called, and nothing else should be building the name itself.
    """
    return f"{epics_dir.rstrip('/')}/{epic}"


def story_dir(epic_dir_rel: str, slug: str) -> str:
    """Where one story's artifacts live, under its epic.

    Only `seed_story` builds this itself. Everywhere else the story directory arrives
    from ostler (`next_story_report`), because ostler knows where it actually put the
    file and this derivation is only correct for stories ostler laid out.
    """
    return f"{epic_dir_rel.rstrip('/')}/stories/{slug}"


def author_context(epics_dir: str) -> str:
    """The run-wide operator context file: the whole-backlog gates write here."""
    return f"{epics_dir.rstrip('/')}/_author-context.md"


def epic_context(epic_dir_rel: str) -> str:
    """One epic's operator context file: the write-epic, split and coverage gates."""
    return f"{epic_dir_rel.rstrip('/')}/context.md"


def story_context(story_dir_rel: str) -> str:
    """One story's operator context file: the write-story gate."""
    return f"{story_dir_rel.rstrip('/')}/context.md"


def story_feedback(story_dir_rel: str) -> str:
    """Where an operator leaves a note for a story that is already written."""
    return f"{story_dir_rel.rstrip('/')}/feedback.md"


__all__ = [
    "author_context",
    "epic_context",
    "epic_dir",
    "feedback_repo_root",
    "launch_repo_root",
    "story_context",
    "story_dir",
    "story_feedback",
    "survey_repo_root",
]
