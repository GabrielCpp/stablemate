"""Shared utilities for workhorse workflow scripts.

Workflow scripts that need workspace resolution, JSON/JSONC parsing, or git and
GitHub operations import from here rather than maintaining a local ``lib/``
directory:

    from workhorse.scriptutil import resolve_workspace, load_json, build_dispatch_list

Because workhorse is installed editable (``pip install -e``), this module is
available to any script invoked via ``sys.executable``.

Two seams isolate external services so an in-process test can intercept them by
monkeypatching this module (no PATH shim, no subprocess for either):

- :func:`github_client` returns an authenticated PyGithub client — the single seam
  for GitHub API access (opening PRs, checks, merges). Scripts never shell out to
  the ``gh`` CLI.
- :func:`run_tool` runs an external CLI (e.g. ``ostler``) as a subprocess — the
  single seam for such tools.

Git operations go through GitPython (via :func:`open_repo`); under test the ``git``
CLI still runs for real against a throwaway repo, so only the GitHub seam is faked.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import yaml

if TYPE_CHECKING:
    from git import Repo


def load_jsonc(text: str) -> dict:
    """Parse JSON with Comments (trailing commas, // comments) as used by VSCode."""
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return json.loads(text)


def load_json(path: Path, label: str, logger: logging.Logger) -> dict:
    """Load a JSON file; logs warnings via caller's logger. Returns {} on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("%s not found at %s", label, path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("%s unreadable at %s: %s", label, path, exc)
    return {}


def die(message: str, *, code: int = 1) -> NoReturn:
    """Print ``message`` to stderr and exit with ``code`` — the hard-fail idiom
    for workflow scripts, defined once here instead of re-implemented per script.

    Unlike ``sys.exit(message)``, which always exits with code 1, this pairs an
    actionable message with any exit ``code`` (scripts use ``2`` to distinguish a
    bad/missing invocation target from an ordinary failure — a distinction the
    workhorse script runner propagates). Typed ``NoReturn`` so a caller's control
    flow narrows: statements after ``die(...)`` are unreachable, and a thin
    per-script wrapper that always ends in ``die`` is itself ``NoReturn``.
    """
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _repo_name_from_dir(path: Path) -> str:
    """Fallback repo name when agents.yml carries no ``repo.name``: the directory
    name normalized the same way farrier's kebab() derives it, so a checkout at
    ``.../Acme`` and a config value ``acme`` resolve to the same key."""
    name = re.sub(r"[^a-zA-Z0-9/-]+", "-", path.name.replace(".", "-").replace("_", "-"))
    return re.sub(r"-+", "-", name).strip("-").lower()


def _read_workspace_file(workspace_env_key: str) -> tuple[list[dict], Path] | None:
    """Parse the `.code-workspace` file named by ``workspace_env_key``, if set.

    Returns ``(folders, ws_dir)`` when the env var points at an existing file,
    else ``None`` — callers apply their own single-folder fallback in that case,
    since resolve_workspace() (read an existing checkout) and checkout_workspace()
    (create one) fall back differently.
    """
    workspace_path = os.environ.get(workspace_env_key)
    if not workspace_path or not Path(workspace_path).exists():
        return None
    ws = load_jsonc(Path(workspace_path).read_text(encoding="utf-8"))
    ws_dir = Path(workspace_path).parent
    return ws.get("folders", []), ws_dir


def resolve_workspace(workspace_env_key: str = "WORKSPACE_FILE") -> dict[str, dict]:
    """Build {repo_name: {path, ...}} from workspace file or CWD fallback.

    Resolution order:
    1. Read the env var named by ``workspace_env_key`` (caller-supplied; default
       ``WORKSPACE_FILE`` for generic use). Workflow scripts should pass their
       own convention (e.g. ``"CODER_WORKSPACE"``).
    2. If that env var points to an existing file, parse it as a VSCode workspace.
    3. Otherwise treat the repo root as a single-folder workspace.

    For each folder, reads agents.yml and merges the workspace: section into the record.
    """
    parsed = _read_workspace_file(workspace_env_key)
    if parsed is not None:
        folders, ws_dir = parsed
    else:
        # Script nodes run with cwd = the workflow definition's own directory, not the
        # consuming repo (see main.py's AGENT_REPO_DIR comment), so a bare Path.cwd()
        # here would synthesize a single-folder workspace keyed off the workflow dir's
        # name (e.g. "coder") instead of the real repo. Mirror find_repo_root()'s
        # AGENT_REPO_DIR-first resolution so mono-repo setups (no CODER_WORKSPACE) key
        # correctly off the actual repo.
        cwd = Path(os.environ.get("AGENT_REPO_DIR") or Path.cwd()).resolve()
        agents_yml = cwd / "agents.yml"
        if agents_yml.exists():
            try:
                meta = yaml.safe_load(agents_yml.read_text(encoding="utf-8")) or {}
                cwd_name = (meta.get("repo") or {}).get("name") or _repo_name_from_dir(cwd)
            except (yaml.YAMLError, OSError):
                cwd_name = _repo_name_from_dir(cwd)
        else:
            cwd_name = _repo_name_from_dir(cwd)
        folders = [{"name": cwd_name, "path": str(cwd)}]
        ws_dir = cwd.parent

    repos: dict[str, dict] = {}
    for folder in folders:
        name = folder.get("name", Path(folder["path"]).name)
        abs_path = (ws_dir / folder["path"]).resolve()
        agents_yml = abs_path / "agents.yml"
        if agents_yml.exists():
            try:
                meta = yaml.safe_load(agents_yml.read_text(encoding="utf-8"))
            except (yaml.YAMLError, OSError):
                repos[name] = {"path": str(abs_path)}
                continue
            ws_section = meta.get("workspace") or {}
            template = meta.get("template") or {}
            repos[name] = {"path": str(abs_path), "template": template, **ws_section}
        else:
            repos[name] = {"path": str(abs_path)}
    return repos


def _has_unsynced_work(dest: Path, branch: str) -> bool:
    """True if ``dest`` has uncommitted changes or commits not on ``origin/<branch>``.

    Used by ``checkout_workspace`` to tell "container restarted mid-run, resume
    where we left off" apart from "clean checkout, safe to fast-forward to the
    host's latest commit" — a bare reset can't distinguish the two, and would
    otherwise silently discard uncommitted in-container work (e.g. a blocked
    operator-gate node's edits) on every restart.
    """
    status = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain"], capture_output=True, text=True, check=True,
        timeout=10,
    )
    if status.stdout.strip():
        return True
    ahead = subprocess.run(
        ["git", "-C", str(dest), "rev-list", "--count", f"origin/{branch}..HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    return ahead.stdout.strip() != "0"


def _git_network_command(*args: str) -> list[str]:
    """Build a Git command with transient credentials for clone/fetch.

    A workflow-specific checkout hook may supply ``WORKHORSE_GIT_TOKEN`` after
    resolving credentials according to that workflow's own configuration. The
    generic checkout code does not know token names or provider conventions.
    """
    if not os.environ.get("WORKHORSE_GIT_TOKEN", ""):
        return ["git", *args]
    credential_helper = (
        '!f() { echo username=x-access-token; echo "password=$WORKHORSE_GIT_TOKEN"; }; f'
    )
    return ["git", "-c", f"credential.helper={credential_helper}", *args]


def _set_origin_url(dest: Path, url: str) -> None:
    """Make an existing persistent checkout follow the configured source."""
    current = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False, timeout=10,
    )
    if current.returncode == 0 and current.stdout.strip() == url:
        return
    action = "set-url" if current.returncode == 0 else "add"
    subprocess.run(
        ["git", "-C", str(dest), "remote", action, "origin", url],
        check=True, timeout=10,
    )


def checkout_workspace(
    workspace_env_key: str = "CODER_WORKSPACE",
    workspace_root: str | Path = "/workspace",
) -> None:
    """Clone/update every `url`-bearing folder in the `.code-workspace` file into
    ``workspace_root``, transparent to whichever workflow graph runs next.

    Meant to be invoked once from entrypoint.sh, before the workflow engine starts —
    neither coder nor author has a "setup" node; by the time the graph starts, every
    folder's working tree already exists under ``workspace_root/<folder name>``.

    Resolution order:
    1. If the workspace file (named by ``workspace_env_key``) is set, clone/update
       every folder in its `folders` list that carries a `url` key (its own optional
       schema extension — VSCode ignores unknown keys, so plain `.code-workspace`
       files stay valid whether or not they use it). A missing `branch` defaults to
       "main". Folders WITHOUT a `url` are left untouched — they may not be git repos
       at all (e.g. a plain documentation directory); their content can only reach the
       container via the workspace-directory bind mount (see compose.yaml), not a clone.
    2. Otherwise (no workspace file set), synthesize a single folder from the existing
       REPO_URL/REPO_NAME/REPO_BRANCH env vars (today's single-primary-repo mechanism)
       and feed it through the exact same clone path — this keeps 1-repo and N-repo
        runs on one code path with zero repo-name defaulting. The URL may be a local
        bind-mounted source or a remote authenticated through ``REPO_TOKEN_ENV``.
    """
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[checkout] %(message)s")
    logger = logging.getLogger("workhorse.checkout")
    workspace_root = Path(workspace_root)

    parsed = _read_workspace_file(workspace_env_key)
    if parsed is not None:
        folders, _ws_dir = parsed
    else:
        repo_url = os.environ.get("REPO_URL", "")
        if not repo_url:
            logger.info("no workspace file and no REPO_URL set — nothing to check out")
            return
        folders = [{
            "name": os.environ.get("REPO_NAME") or "repo",
            "url": repo_url,
            "branch": os.environ.get("REPO_BRANCH", "main"),
        }]

    workspace_root.mkdir(parents=True, exist_ok=True)

    for folder in folders:
        url = folder.get("url")
        if not url:
            continue
        name = folder.get("name") or Path(folder["path"]).name
        branch = folder.get("branch", "main")
        dest = workspace_root / name

        if (dest / ".git").exists():
            _set_origin_url(dest, url)
            subprocess.run(
                _git_network_command("-C", str(dest), "fetch", "--quiet", "origin"),
                check=True, timeout=300,
            )
            if _has_unsynced_work(dest, branch):
                logger.info(
                    "%s has uncommitted changes or commits not on origin/%s — "
                    "preserving existing checkout, skipping reset",
                    name, branch,
                )
                continue
            logger.info("updating %s from %s (%s)", name, url, branch)
            subprocess.run(
                ["git", "-C", str(dest), "checkout", "--quiet", branch],
                check=True, timeout=10,
            )
            subprocess.run(
                ["git", "-C", str(dest), "reset", "--quiet", "--hard", f"origin/{branch}"],
                check=True, timeout=10,
            )
        else:
            logger.info("cloning %s from %s (%s)", name, url, branch)
            subprocess.run(
                _git_network_command(
                    "clone", "--quiet", "--branch", branch, "--single-branch", url, str(dest)
                ),
                check=True, timeout=600,
            )


def find_repo_root() -> Path:
    """Find repo root via AGENT_REPO_DIR env or walking up from CWD."""
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return here


def find_docs_root(docs_path: str = "") -> Path:
    """Resolve the docs repo root.

    Priority:
    1. Explicit ``docs_path`` argument (from workflow var)
    2. ``CODER_DOCS_PATH`` environment variable
    3. Falls back to ``find_repo_root()`` (AGENT_REPO_DIR / CWD walk)
    """
    path = docs_path or os.environ.get("CODER_DOCS_PATH", "")
    if path:
        p = Path(path)
        if p.is_absolute():
            return p.resolve()
        return (find_repo_root() / p).resolve()
    return find_repo_root()


def get_repo_config(repo_name: str, key: str, default=None, *, repos: dict | None = None):
    """Get a config value from a repo's agents.yml workspace section.

    Examples:
        get_repo_config("api-service", "qa_mode")            # → "cli"
        get_repo_config("api-service", "base_branch", "main") # → "develop"
    """
    if repos is None:
        repos = resolve_workspace()
    repo = repos.get(repo_name, {})
    return repo.get(key, default)


def build_dispatch_list(plan_ctx: dict, repos: dict[str, dict], *, fallback: bool = False) -> list[dict]:
    """Build ordered dispatch records from plan-context.json + workspace repos.

    When ``fallback=True`` and the plan has no services (i.e., plan-context.json is
    absent or empty), returns a single fallback record using the first workspace repo.
    Pass ``fallback=True`` only from callers that know the plan-context was not found.
    """
    services = plan_ctx.get("services") or []
    impl_order = plan_ctx.get("implementation_order") or []

    service_map: dict[str, dict] = {}
    for svc in services:
        key = f"{svc['repo']}::{svc['path']}"
        service_map[key] = svc

    ordered_keys = impl_order if impl_order else [f"{s['repo']}::{s['path']}" for s in services]

    dispatch_list: list[dict] = []
    for key in ordered_keys:
        svc = service_map.get(key)
        if not svc:
            continue
        repo_name = svc["repo"]
        repo_info = repos.get(repo_name, {})
        repo_path = repo_info.get("path", "")
        template = repo_info.get("template") or {}
        svc_type = svc.get("type", "unknown")
        label = template.get("backend_layer_name") or template.get("mobile_layer_name") or svc_type

        dispatch_list.append({
            "service": key,
            "repo": repo_name,
            "cwd": repo_path,
            "service_path": svc["path"],
            "type": svc_type,
            "plan_file": svc.get("plan_file", "plan.md"),
            "skills": svc.get("skills", []),
            "qa_mode": repo_info.get("qa_mode", "cli"),
            "qa_skills": repo_info.get("qa_skills", []),
            "verification": repo_info.get("verification", ""),
            "label": label,
        })

    if fallback and not dispatch_list and repos:
        repo_name = next(iter(repos))
        repo_info = repos[repo_name]
        dispatch_list = [{
            "service": f"{repo_name}::.",
            "repo": repo_name,
            "cwd": repo_info.get("path", "."),
            "service_path": ".",
            "type": "unknown",
            "plan_file": "plan.md",
            "skills": [],
            "qa_mode": repo_info.get("qa_mode", "cli"),
            "qa_skills": [],
            "verification": repo_info.get("verification", ""),
            "label": repo_name,
        }]

    return dispatch_list


def get_affected_repos(plan_ctx: dict, repos: dict[str, dict]) -> list[str]:
    """Deduplicated sorted list of repo names from plan-context services."""
    names: set[str] = set()
    for svc in plan_ctx.get("services") or []:
        name = svc.get("repo", "")
        if name and name in repos:
            names.add(name)
    return sorted(names)


def open_repo(path: str | Path) -> Repo:
    # Import GitPython lazily: importing it runs a `git --version` probe at import
    # time, which crashes (IndexError parsing the version) whenever `git` is shadowed
    # by a stub — e.g. the workflow test harness mocks `git`, returning empty output.
    # Only the handful of scripts that actually open a repo should pay that cost; the
    # many git-free scripts (select-next-*, resolve-*, detect-*) must import this
    # module without needing a real git on PATH.
    from git import Repo

    return Repo(str(path))


_GITHUB_URL_PREFIXES = (
    "git@github.com:",
    "ssh://git@github.com/",
    "https://github.com/",
)


def repo_full_name_from_url(url: str) -> str | None:
    """Derive a github.com ``owner/repo`` slug from an origin URL (SSH or HTTPS).
    Returns None when the origin is not a github.com remote."""
    for prefix in _GITHUB_URL_PREFIXES:
        if url.startswith(prefix):
            path = url[len(prefix):]
            return path[:-4] if path.endswith(".git") else path
    return None


def run_tool(
    argv: list[str],
    cwd: str | Path | None = None,
    *,
    check: bool = False,
    logger: logging.Logger | None = None,
) -> subprocess.CompletedProcess:
    """Run an external CLI tool (e.g. ``ostler``) as a subprocess and return the
    completed process.

    The single seam workflow scripts route external-CLI calls through, so an
    in-process test can monkeypatch ``run_tool`` to return a canned result — no PATH
    shim. In production it runs the real binary (the "real passthrough" contract). Set
    ``check=True`` to raise ``RuntimeError`` on a non-zero exit."""
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    if result.returncode != 0 and check:
        if logger is not None:
            logger.error(
                "%s failed (exit %d): %s",
                " ".join(argv), result.returncode, result.stderr.strip(),
            )
        raise RuntimeError(f"{argv[0]} failed: {result.stderr.strip()}")
    return result


def github_client(token: str | None = None):
    """Return an authenticated PyGithub ``Github`` client.

    The one seam every workflow script goes through for GitHub API access (opening
    PRs, checking checks, merging) instead of shelling out to the ``gh`` CLI. Because
    it is a plain Python call, an in-process test monkeypatches ``github_client`` to
    return a fake — no PATH shim, no CLI, no network. ``token`` defaults to
    ``GH_TOKEN`` / ``WORKHORSE_GIT_TOKEN`` from the environment. Imported lazily
    (like :func:`open_repo`) so the many GitHub-free scripts need not import PyGithub.
    """
    from github import Auth, Github

    tok = token or os.environ.get("GH_TOKEN") or os.environ.get("WORKHORSE_GIT_TOKEN")
    if tok:
        return Github(auth=Auth.Token(tok))
    return Github()


# ── git operations (GitPython, via open_repo) ──────────────────────────────────
# The handful of git commands the workflow scripts need, wrapped behind the same
# GitPython seam as open_repo() so a script never shells out to `git` itself.
# GitPython is a thin wrapper over the git CLI, so behaviour matches the old
# subprocess calls while the error handling routes through GitError. Under test
# the git CLI still runs for real against a throwaway repo (workhorse.testing.
# make_git_repo) — there is nothing to monkeypatch here; only the GitHub seam
# (github_client) is faked. Each helper opens the repo lazily and returns a plain
# value / bool so callers stay fail-soft: a bad repo or failed command yields
# None/False/-1 rather than raising into an unattended run.


def origin_url(path: str | Path) -> str | None:
    """The ``origin`` remote URL of the repo at ``path``, or None when absent."""
    from git.exc import GitError

    try:
        repo = open_repo(path)
        return next((r.url for r in repo.remotes if r.name == "origin"), None)
    except GitError:
        return None


def local_branch_exists(path: str | Path, branch: str) -> bool:
    """True if ``branch`` exists as a local branch (mirrors GitPython's repo.heads)."""
    from git.exc import GitError

    try:
        return branch in [h.name for h in open_repo(path).heads]
    except GitError:
        return False


def branch_exists(path: str | Path, ref: str) -> bool:
    """True if ``ref`` resolves in the repo (mirrors ``git rev-parse --verify``)."""
    from git.exc import GitError

    try:
        open_repo(path).git.rev_parse("--verify", "--quiet", ref)
        return True
    except GitError:
        return False


def current_branch(path: str | Path) -> str:
    """The current branch name, or ``"main"`` if detached/unresolvable."""
    from git.exc import GitError

    try:
        name = open_repo(path).active_branch.name
        return name if name and name != "HEAD" else "main"
    except (GitError, TypeError):
        return "main"


def active_branch(path: str | Path) -> str | None:
    """The current branch name, or None when HEAD is detached/unresolvable.

    Unlike :func:`current_branch` (which defaults to ``"main"``), this preserves the
    'no branch' signal callers use to fall back to a trunk."""
    from git.exc import GitError

    try:
        name = open_repo(path).active_branch.name
    except (GitError, TypeError):
        return None
    return name or None


def checkout(path: str | Path, branch: str, *, create: bool = False, reset: bool = False) -> bool:
    """Check out ``branch``. ``create`` cuts it with ``-b``; ``reset`` create-or-resets
    it to the current HEAD with ``-B`` (and wins over ``create``). Returns success; a
    failure is reported as False rather than raised (best-effort)."""
    from git.exc import GitError

    if reset:
        args = ["-B", branch]
    elif create:
        args = ["-b", branch]
    else:
        args = [branch]
    try:
        open_repo(path).git.checkout(*args)
        return True
    except GitError:
        return False


def commits_ahead(path: str | Path, branch: str, base: str) -> int:
    """Commits reachable from ``branch`` but not ``origin/<base>``. Returns -1 when
    the range is unresolvable (e.g. no ``origin/<base>`` yet)."""
    from git.exc import GitError

    try:
        out = open_repo(path).git.rev_list("--count", f"origin/{base}..{branch}")
        return int(out.strip())
    except (GitError, ValueError):
        return -1


def commit_paths(path: str | Path, message: str, *pathspecs: str) -> bool:
    """Stage ``pathspecs`` (everything, via ``-A``, when none are given) and commit.

    Returns False when nothing was staged (or the commit failed), True when a
    commit was made. The staged-change check is scoped to the same pathspecs, so a
    scoped commit lands only when those paths actually changed."""
    from git.exc import GitCommandError, GitError

    scope = ["--", *pathspecs] if pathspecs else []
    try:
        repo = open_repo(path)
        repo.git.add(*(pathspecs or ("-A",)))
        try:
            repo.git.diff("--cached", "--quiet", *scope)
            return False  # nothing staged
        except GitCommandError:
            pass  # staged changes present
        repo.git.commit("-m", message, *scope)
        return True
    except GitError:
        return False


def commit_all(path: str | Path, message: str) -> bool:
    """Stage every change (``git add -A``) and commit it. Returns False when there
    was nothing to commit (or the commit failed)."""
    return commit_paths(path, message)


# The token is read from GH_TOKEN by this inline credential helper at git-exec
# time, so it is never written into a remote URL, git config, or the process
# arguments (which would leak it into logs / `ps`).
_PUSH_CRED_HELPER = '!f() { echo username=x-access-token; echo "password=${GH_TOKEN}"; }; f'


def push_branch(
    path: str | Path, token: str, branch: str, *, verify: bool = True, slug: str | None = None
) -> bool:
    """Push ``branch`` to a github.com repo over HTTPS with a transient token.

    The target repo is the ``origin`` slug by default; pass ``slug`` to override it
    (for a bind-mount clone whose ``origin`` is a local path but that pushes to a
    known ``owner/repo``). With ``verify`` (the default) returns True only after
    confirming the remote branch head advanced to the local head — a push can
    report success while leaving the ref unmoved, which is exactly what let a fix
    loop spin against a stale PR head. Returns False on any failure (no github
    target, push rejected, or unverified head)."""
    from git.exc import GitError

    if slug is None:
        url = origin_url(path)
        slug = repo_full_name_from_url(url) if url else None
    if not slug:
        return False
    push_url = f"https://github.com/{slug}.git"
    try:
        git = open_repo(path).git
    except GitError:
        return False
    git.update_environment(GH_TOKEN=token)
    cred = f"credential.helper={_PUSH_CRED_HELPER}"
    try:
        git(c=cred).push(push_url, f"{branch}:{branch}")
    except GitError:
        return False
    if not verify:
        return True
    try:
        local_head = git.rev_parse(branch).strip()
        ls_remote = git(c=cred).ls_remote(push_url, f"refs/heads/{branch}")
    except GitError:
        return False
    remote_head = ls_remote.split()[0] if ls_remote.split() else ""
    return bool(remote_head) and remote_head == local_head


def sync_to_origin(path: str | Path, token: str, base: str) -> str | None:
    """Fetch ``base`` from the github.com ``origin`` over HTTPS and hard-set the local
    ``base`` to it (``git checkout -B <base> FETCH_HEAD``).

    Returns the new short HEAD sha on success, or None on any failure. Used after a
    merge lands to move the local checkout to the merged tip, so the next branch is
    cut from it. The token rides the same inline credential helper as
    :func:`push_branch` — never written into a URL, git config, or the logs."""
    from git.exc import GitError

    url = origin_url(path)
    slug = repo_full_name_from_url(url) if url else None
    if not slug:
        return None
    fetch_url = f"https://github.com/{slug}.git"
    try:
        git = open_repo(path).git
    except GitError:
        return None
    git.update_environment(GH_TOKEN=token)
    try:
        git(c=f"credential.helper={_PUSH_CRED_HELPER}").fetch(fetch_url, base)
        git.checkout("-B", base, "FETCH_HEAD")
        return git.rev_parse("--short", "HEAD").strip()
    except GitError:
        return None


# ── GitHub operations (PyGithub, via github_client) ────────────────────────────
# Thin helpers over github_client() + repo_full_name_from_url() so a script talks
# to GitHub through PyGithub rather than the `gh` CLI. Tests fake GitHub by
# monkeypatching github_client — these helpers inherit that seam.

_GH_TOKEN_FALLBACKS = ("GH_TOKEN", "GITHUB_TOKEN")


def _configured_token_env(root: Path) -> str | None:
    """The env-var name configured in agents.yml ``workflow.githubTokenEnv`` (or None)."""
    cfg = root / "agents.yml"
    if not cfg.is_file():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    workflow = data.get("workflow") or {}
    if isinstance(workflow, dict):
        name = workflow.get("githubTokenEnv") or workflow.get("github_token_env")
        if name:
            return str(name).strip()
    return None


def resolve_github_token(root: str | Path | None = None) -> str:
    """Resolve the GitHub token for the coder PR/CI steps.

    Order: the env var named by agents.yml ``workflow.githubTokenEnv`` (repo-
    configurable, not hardcoded), then the conventional ``GH_TOKEN``, then
    ``GITHUB_TOKEN``. Returns ``""`` when none is set — callers treat empty as
    "no token" and skip (best-effort). ``root`` defaults to :func:`find_repo_root`."""
    root = Path(root).resolve() if root is not None else find_repo_root()
    names: list[str] = []
    configured = _configured_token_env(root)
    if configured:
        names.append(configured)
    for fallback in _GH_TOKEN_FALLBACKS:
        if fallback not in names:
            names.append(fallback)
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def resolve_repo(path: str | Path, token: str | None = None):
    """Resolve the GitHub repository for the ``origin`` at ``path``.

    Returns ``(repo, slug)`` where ``repo`` is a PyGithub ``Repository`` (via the
    :func:`github_client` seam) or None when there is no origin, the origin is not a
    github.com remote, or the API can't be reached; ``slug`` is the ``owner/repo``
    string (or None when it can't be derived) for logging."""
    from github import GithubException

    url = origin_url(path)
    if not url:
        return None, None
    slug = repo_full_name_from_url(url)
    if not slug:
        return None, None
    try:
        return github_client(token).get_repo(slug), slug
    except GithubException:
        return None, slug


def find_open_pr(gh_repo, branch: str):
    """The first OPEN pull request on ``gh_repo`` whose head is ``branch``, or None."""
    from github import GithubException

    try:
        owner = gh_repo.owner.login
        for pr in gh_repo.get_pulls(state="open", head=f"{owner}:{branch}"):
            return pr
    except GithubException:
        return None
    return None


# ── more git read/plumbing helpers (GitPython, via open_repo) ───────────────────
# The remaining git commands the workflow scripts need, so a script never shells
# out to `git`. Same contract as the helpers above: fail-soft, real git under test.


def short_sha(path: str | Path, ref: str = "HEAD") -> str:
    """The abbreviated commit sha for ``ref`` (``git rev-parse --short``), or "" when
    it can't be resolved."""
    from git.exc import GitError

    try:
        return open_repo(path).git.rev_parse("--short", ref).strip()
    except GitError:
        return ""


def rename_branch(path: str | Path, old: str, new: str) -> bool:
    """Rename branch ``old`` to ``new`` (``git branch -m``). Returns success."""
    from git.exc import GitError

    try:
        open_repo(path).git.branch("-m", old, new)
        return True
    except GitError:
        return False


def restore_paths(path: str | Path, *pathspecs: str) -> bool:
    """Discard working-tree changes to ``pathspecs`` (``git checkout -- <paths>``).
    Returns success; a no-pathspec call is a no-op that returns False."""
    from git.exc import GitError

    if not pathspecs:
        return False
    try:
        open_repo(path).git.checkout("--", *pathspecs)
        return True
    except GitError:
        return False


def default_branch(path: str | Path) -> str | None:
    """The remote's default branch (``origin/HEAD`` → e.g. ``main``), or None when
    ``origin/HEAD`` is not set / unresolvable."""
    from git.exc import GitError

    try:
        ref = open_repo(path).git.symbolic_ref("--short", "refs/remotes/origin/HEAD").strip()
    except GitError:
        return None
    if ref.startswith("origin/"):
        ref = ref[len("origin/"):]
    return ref or None


def merge_base(path: str | Path, *refs: str) -> str | None:
    """The best common ancestor of ``refs`` (``git merge-base``), or None."""
    from git.exc import GitError

    try:
        out = open_repo(path).git.merge_base(*refs).strip()
    except GitError:
        return None
    return out or None


def show_file(path: str | Path, ref: str, relpath: str) -> str | None:
    """The contents of ``relpath`` at ``ref`` (``git show <ref>:<relpath>``), or None
    when it didn't exist there (or git is unavailable)."""
    from git.exc import GitError

    try:
        return open_repo(path).git.show(f"{ref}:{relpath}")
    except GitError:
        return None


def diff_text(path: str | Path, *args: str) -> str:
    """Raw ``git diff <args>`` output ("" on error). The caller passes the diff
    arguments, e.g. ``diff_text(root, "--unified=0", base, "HEAD", "--")``."""
    from git.exc import GitError

    try:
        return open_repo(path).git.diff(*args)
    except GitError:
        return ""


def list_tracked_files(path: str | Path, *pathspecs: str) -> list[str]:
    """Repo-relative paths git tracks (``git ls-files``), optionally limited to
    ``pathspecs``. Empty list when git is unavailable."""
    from git.exc import GitError

    try:
        out = open_repo(path).git.ls_files(*pathspecs)
    except GitError:
        return []
    return [line for line in out.splitlines() if line]


def remote_urls(path: str | Path, name: str = "origin") -> list[str]:
    """The configured URLs for remote ``name`` — its push URL then its fetch URL,
    de-duplicated in order. Empty when the remote or repo is absent.

    Uses a bare ``git`` bound to ``path`` (not :func:`open_repo`) plus a per-call
    ``safe.directory`` trust, so it can read a repo whose working tree is owned by
    another user — e.g. a host-owned bind mount inside a container, which git would
    otherwise refuse to touch with a "dubious ownership" error."""
    from git import Git
    from git.exc import GitError

    repo_path = str(Path(path).resolve())
    git = Git(repo_path)
    urls: list[str] = []
    for extra in (["--push", name], [name]):
        try:
            url = git(c=f"safe.directory={repo_path}").remote("get-url", *extra).strip()
        except GitError:
            url = ""
        if url and url not in urls:
            urls.append(url)
    return urls


def set_identity(path: str | Path, name: str, email: str) -> bool:
    """Set the repo-local ``user.name`` / ``user.email`` (``git config``). Returns
    success. Used by unattended committers (e.g. a container agent) that have no
    ambient git identity."""
    from git.exc import GitError

    try:
        repo = open_repo(path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", name)
            cw.set_value("user", "email", email)
        return True
    except GitError:
        return False


def allow_all_directories() -> None:
    """Add ``*`` to the GLOBAL ``safe.directory`` list (``git config --global``), so
    git operates on repos owned by another user — a host-owned bind mount inside a
    disposable, isolated container. Best-effort: a failure is swallowed."""
    from git import Git
    from git.exc import GitError

    try:
        Git().config("--global", "--add", "safe.directory", "*")
    except GitError:
        pass


def clone(url: str, dest: str | Path, *, branch: str | None = None, single_branch: bool = True) -> bool:
    """Clone ``url`` into ``dest`` (``git clone``). Returns success. Honors the ambient
    ``GIT_SSH_COMMAND`` for SSH remotes (git inherits it from the environment)."""
    from git import Repo
    from git.exc import GitError

    kwargs: dict = {}
    if branch:
        kwargs["branch"] = branch
    if single_branch:
        kwargs["single_branch"] = True
    try:
        Repo.clone_from(url, str(dest), **kwargs)
        return True
    except GitError:
        return False


def fetch_reset(path: str | Path, branch: str, *, remote: str = "origin") -> bool:
    """Fetch ``remote`` and hard-reset the local ``branch`` to ``<remote>/<branch>``
    (``git fetch`` → ``checkout`` → ``reset --hard``). Returns success."""
    from git.exc import GitError

    try:
        git = open_repo(path).git
        git.fetch("--quiet", remote)
        git.checkout("--quiet", branch)
        git.reset("--quiet", "--hard", f"{remote}/{branch}")
        return True
    except GitError:
        return False


def push_to_origin(
    path: str | Path, branch: str, *, remote: str = "origin", force_with_lease: bool = False
) -> bool:
    """Push ``branch`` to ``remote`` using the checkout's AMBIENT credentials (SSH key
    or a cached helper) — not a token (see :func:`push_branch` for token pushes).
    ``force_with_lease`` adds ``--force-with-lease``. Returns success."""
    from git.exc import GitError

    args = ["--quiet"]
    if force_with_lease:
        args.append("--force-with-lease")
    try:
        open_repo(path).git.push(*args, remote, branch)
        return True
    except GitError:
        return False
