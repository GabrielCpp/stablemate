"""Where things are: repo-root resolution, and the derived artifact paths.

Both kinds of thing here are here for the same reason `author/shared/paths.py` gives — they were
duplicated verbatim across the YAML workflow's 71 scripts, once per file, and a
derivation copied dozens of times is a derivation nobody can change.

**Three repo-root resolvers, deliberately.** The scripts did not agree on how to find the
consuming repo, and the disagreement is behavioral, not cosmetic: a run launched from a
subdirectory, or from a repo whose `docs/epics/` exists but whose `.git` does not, lands
on a *different* root under each. So each is kept, named for what it actually does, and
each ported node calls the one its script called:

Every one of them takes the run's `repo_dir` as its argument and reads no environment
variable, per the rule in `workflows/README.md`: the consuming repo is an *input*, so it
travels down from `Workflow.repo_dir` through the state that calls the node. An empty
`repo_dir` still falls back to a walk — a visible, overridable default, unlike an
ambient variable.

* `workhorse_workflows.kit.find_repo_root` — `repo_dir`, else the first of
  `[cwd, *cwd.parents]` carrying `agents.yml` or `.git`. Four scripts
  (`check-sentinel-ids.py`, `detect-regression-platform.py`, `flush-root-screenshots.py`,
  `verify_qa_evidence.py`) had re-typed this function *character for character* rather
  than importing it; those nodes now call the engine's copy, which is not a narrowing —
  the bodies were identical.
* `epics_repo_root()` — the same walk, but marked by `agents.yml` or a `docs/epics/`
  **directory** rather than `.git`. `prune-epic.py` alone resolves this way, and the
  difference matters exactly where it is used: a docs checkout with no `.git` (a
  bind-mounted clone) still has its epic queue popped.
* `launch_repo_root()` — `repo_dir`, else `cwd` *if* it looks like a project root
  (`docs/epics/`, `agents.yml` or `.git`), else the first ancestor with `agents.yml` or
  `.git`, else `cwd`. The operator-gate scripts (`await_operator.py`,
  `await-ci-operator.py`, `await-merge-operator.py`) and `check_feedback.py` resolve this
  way. Its `cwd`-first probe is what lets a test harness point the gate at a sandbox by
  chdir alone, which the plain upward walk does not do.

The `await-*` scripts carried a fourth rung after all of that — a walk upward from
`__file__` — reached only when nothing above matched. Under the driver `__file__` is this
installed package, never the consuming repo, so that rung could only ever have returned
something wrong. It is dropped, and it is the one narrowing in this module; it is
recorded as a finding rather than passed over.

**The derived paths are repo-relative strings** wherever the YAML's scripts emitted them
that way, so a checkpoint survives a machine change. A node joins one onto a freshly
resolved root; only an `Await`'s context file needs an absolute `Path`, and the workflow
makes that join at the call site.

**Where a document lives is ostler's answer, not this module's.** Every doc-tree
derivation below routes through `ostler.path`, so a repo that moved its epics with
`docRoots:` is followed rather than assumed away, and an epic folder numbered
`0001-checkout` is found from the bare slug the queue carries. What stays here is the part
ostler has no opinion about: the *filenames this workflow invented* — `<gate>-context.md`,
`context.md`, `attempts.md` — joined onto a directory ostler resolved, and the run
artifacts that are not documents at all (`.agents/operator`, the dream inbox and ledger).

The `docs/epics/` probes in the root resolvers above are the one exception, and they are
not a second derivation: they are how a *root* is recognized before there is a root to ask
ostler about. Once the root is known, every path comes from here.
"""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path

#: Where a run's operator gates leave the file a human answers in. Repo-relative, one
#: file per gate kind, so two gates open in the same story do not overwrite each other.
OPERATOR_DIR = ".agents/operator"

#: Where `dream` drains its proposals from, and the durable ledger it drains into.
DREAM_INBOX = "docs/.dream-improvements.inbox.json"
DREAM_LEDGER = "docs/workflow-improvements"

#: The run's ambient path inputs: which checkout, which docs checkout, which workspace
#: manifest, and which library layers a turn resolves its prompt body against. All four
#: are *where* rather than *what*, they are wanted by roughly every second node, and no
#: state chooses them — which is exactly the shape that used to be an environment read.
#: `Workflow.injects` fills them in for any node or sub-flow that declares a parameter of
#: the same name and was not passed one. `library_dirs` is on the engine's base class,
#: and is restated here because naming `injects` at all replaces the base's tuple.
AMBIENT = ("repo_dir", "docs_path", "workspace_file", "library_dirs")


def epics_repo_root(repo_dir: str | Path = "") -> Path:
    """`prune-epic.py`'s resolution: `agents.yml` or a `docs/epics/` **directory**.

    Not `.git`, which is the difference from `find_repo_root` and the whole point of
    keeping it separate — the epic queue lives in the docs checkout, and a bind-mounted
    docs clone has no `.git` of its own to be found by.
    """
    if repo_dir:
        return Path(repo_dir).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def launch_repo_root(repo_dir: str | Path = "") -> Path:
    """The operator gates' resolution: prefer `cwd` when it already looks like a root.

    The upward walk only starts at `cwd.parents`, so a `cwd` that carries `docs/epics/`
    but neither `agents.yml` nor `.git` still wins — which is what a test harness relies
    on when it chdirs into a sandbox, and what `find_repo_root` would walk straight past.
    """
    if repo_dir:
        return Path(repo_dir).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def operator_context_path(root: Path, gate: str, epic: str = "") -> Path:
    """The absolute file an `Await` writes its questions into, for `gate` on `epic`.

    Absolute because `Await` takes a real path to poll, unlike everything else here.

    The three rungs are `await-ci-operator.py`'s and `await-merge-operator.py`'s, in their
    order, and they are a *per-epic* resolution rather than a per-gate one:

    1. `docs/epics/<NNNN-epic>/<gate>-context.md` when that epic folder exists — the questions
       land next to the epic they are about, which is where the operator is already looking.
       The folder is resolved through ostler, so a bare slug finds its numbered directory;
    2. `<root>/<gate>-context.<epic>.md` when it does not, so an epic with no folder still
       gets a file of its own;
    3. `<root>/<gate>-context.md` with no epic at all.

    Rungs 1 and 2 are what keep two epics escalating in the same checkout from overwriting
    each other's questions. `gate` is `ci-operator` or `merge-operator`.
    """
    if epic:
        # ostler owns the folder rule, not this join: epic directories are numbered
        # (`0001-checkout`) and a gate is normally invoked with the bare slug, so a literal
        # join would miss the folder and silently demote every question to rung 2.
        epic_dir = okf_path.epic_dir_in(root, epic)
        if epic_dir.is_dir():
            return epic_dir / f"{gate}-context.md"
        return root / f"{gate}-context.{epic}.md"
    return root / f"{gate}-context.md"


def _rel(root: Path, target: Path) -> str:
    """*target* as a repo-relative posix string, or absolute if it is outside the repo."""
    try:
        return target.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return target.as_posix()


def epics_dir(root: Path, configured: str = "") -> str:
    """Where epics live, repo-relative: what the run was told, else what ostler says.

    `configured` is a run's `epics_dir` parameter — an operator pointing it at a
    non-standard tree. Empty, the normal case, asks ostler, which reads `docRoots:`.
    """
    return configured.strip().rstrip("/") or _rel(root, okf_path.epics_root_in(root))


def backlog_file(root: Path, configured: str = "") -> str:
    """The worklist the coder files defects onto, repo-relative — ostler's, unless told.

    The coder→author edge: an item filed here is what the author workflow authors next
    run, so both sides have to name the same file, and ostler is where that is decided.
    """
    return configured.strip() or _rel(root, okf_path.backlog_path_in(root))


def epic_dir_rel(root: Path, epic: str, configured: str = "") -> str:
    """:func:`epic_dir` as a repo-relative string, honouring an operator's epics root."""
    return _rel(root, okf_path.epic_dir_under(root / epics_dir(root, configured), epic))


def features_dir(root: Path, configured: str = "") -> str:
    """The OKF feature book, repo-relative: what the run was told, else ostler's."""
    return configured.strip().rstrip("/") or _rel(root, okf_path.features_root_in(root))


def epics_index(root: Path) -> str:
    """The epic queue, repo-relative: `index.md` in whichever directory holds the epics.

    Repo-relative because every caller hands it to git — `git show`, `git checkout`,
    `commit_paths` — which pathspecs against the work tree rather than the filesystem.
    """
    return _rel(root, okf_path.epics_index_in(root))


def epic_dir(root: Path, epic: str) -> Path:
    """The absolute folder of *epic*, by number or by bare slug — ostler resolves it."""
    return okf_path.epic_dir_in(root, epic)


def story_md(root: Path, epic: str, slug: str) -> Path:
    """The absolute `story.md` of *slug* in *epic*, when nothing else has resolved it.

    The name is this workflow's convention; `<epic>/stories/<slug>` is ostler's layout.
    """
    return okf_path.story_dir_in(root, epic, slug) / "story.md"


def story_context_path(story_path: str, repo_dir: str | Path = "") -> Path:
    """The per-story operator context file: `<story-folder>/context.md`.

    A second gate location, not a duplicate of `operator_context_path`. The coder's
    per-story gates (`await_operator` and its siblings) put the questions *next to the
    story* so the operator answering them is reading the story they are about, and
    `await_operator.py` derived exactly this path. Without a story — a standalone run
    pointed at no slug — it falls back to the launch root, as that script did.

    `story_path` is already absolute by the time a flow has it (`prepare_story` resolves
    it), so this is a `.parent`; the fallback is what needs a root.
    """
    if story_path:
        return Path(story_path).parent / "context.md"
    return launch_repo_root(repo_dir) / "context.md"


def decisions_dir(docs_root: Path) -> Path:
    """Where the operator's standing decisions live: `<docs-root>/decisions/`.

    The place a resolver may answer *from*, and the place it writes to when it answers
    something no record covered yet. It is this workflow's own invention rather than one
    of ostler's document types, which is why it is joined here: ostler has no opinion
    about it, the same way it has none about `context.md` or `attempts.md`.

    A decision record is not a spec. A spec says what the product does; a record here says
    what the operator ruled when two documents disagreed about it, so that the next run to
    hit the same question reads the ruling instead of parking on it a second time. That
    accumulation is the whole point: a block answered once should cost a human once.
    """
    return docs_root / "decisions"


def is_gate_context(path: str | Path) -> bool:
    """Is *path* a file an operator gate wrote, rather than work a story produced?

    Both gate locations at once, because the cleanliness check reads one flat list of
    repo-relative paths and cannot tell them apart by directory: `<story>/context.md` from
    :func:`story_context_path`, and `<gate>-context.md` / `<gate>-context.<epic>.md` from
    :func:`operator_context_path`.

    It matters that these are excused. A gate writes its questions into the working tree
    and the operator answers in the same file, so every escalation leaves the tree dirty by
    construction — and a run that parked once would then park forever, blaming the agent
    for the note the workflow itself left. The old `git commit -a` had the opposite bug:
    it swept the questions and the answers into the story's own commit.

    A hand-written document that happens to be called `something-context.md` is excused
    along with them. That is the trade this spelling makes, and it errs the safe way: a
    file wrongly excused is one the operator sees in `git status` afterwards, while a gate
    file wrongly flagged stops the run.
    """
    name = Path(path).name
    if not name.endswith(".md"):
        return False
    stem = name[: -len(".md")]
    return stem == "context" or stem.split(".", 1)[0].endswith("-context")


__all__ = [
    "AMBIENT",
    "DREAM_INBOX",
    "DREAM_LEDGER",
    "OPERATOR_DIR",
    "backlog_file",
    "epic_dir",
    "epic_dir_rel",
    "epics_dir",
    "epics_index",
    "epics_repo_root",
    "features_dir",
    "is_gate_context",
    "launch_repo_root",
    "operator_context_path",
    "story_context_path",
    "story_md",
]
