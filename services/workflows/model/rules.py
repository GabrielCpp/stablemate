"""Why the workflows commands say no. The message is the one printed, word for
word, with the sandbox written `<sandbox>`. A rule reads the request (`a`) and
the directory (`s`)."""

from __future__ import annotations

import re

from ostler.book import Actor, Exited, Rule

from ..fixtures import DryRunArgs, NewArgs, NewProgramArgs
from .state import Workspace, skills_installed

NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")

USAGE = "usage: workhorse-new [-h] --check CHECK [--into DIR] name\nworkhorse-new: error: the following arguments are required: "

USAGE_ERROR = Exited(2)
REFUSED = Exited(1)


def _unreadable(skills: str) -> str:
    block = f"{skills.count(chr(10)) + 1} skill reference(s) will fail to render:\n{skills}\n"
    block += (
        "  A turn whose prompt makes one stops with an error.\n"
        "  Install the skill in this repo or at home with `farrier install`, "
        "and move a retired helper to the one its error names."
    )
    return f"[workhorse] WARNING: {block}\n[workhorse] ERROR: {block}"


PROGRAM_USAGE = (
    "usage: new_program.py [-h] [--repo REPO] --dir DIR --code-root CODE_ROOT\n"
    "                      [--name NAME] [--gate GATE] [--progress PROGRESS]\n"
    "                      [--result-branch RESULT_BRANCH] [--ram-gb RAM_GB]\n"
    "                      [--cpus CPUS] [--gpu GPU] [--disk-gb DISK_GB]\n"
    "                      [--min-containment {premium,best_effort,advisory}]\n"
    "                      [--set-default] [--force]\n"
    "new_program.py: error: the following arguments are required: "
)

OKF_BOOK_SKILLS = "\n".join(
    f"  - skill 'ostler-book' (referenced in {prompt})"
    for prompt in (
        "catch_up/prompts/update-book.md",
        "main/prompts/write-python-book.md",
        "main/prompts/write-screen-reasons.md",
        "main/prompts/write-screen-skeletons.md",
    )
)


def _no_name_and_no_check(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return a.name is None and a.check is None


def _no_name(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return a.name is None


def _no_check(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return a.check is None


def _not_a_name(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return a.name is not None and not NAME.fullmatch(a.name)


def _blank_check(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return a.check is not None and not a.check.strip()


def _target_exists(a: NewArgs, s: Workspace, by: Actor | None) -> bool:
    return f"{a.target}/pyproject.toml" in s.files


def _no_dir_and_no_code_root(a: NewProgramArgs, s: Workspace, by: Actor | None) -> bool:
    return a.dir is None and a.code_root is None


def _no_dir(a: NewProgramArgs, s: Workspace, by: Actor | None) -> bool:
    return a.dir is None


def _no_code_root(a: NewProgramArgs, s: Workspace, by: Actor | None) -> bool:
    return a.code_root is None


def _program_exists(a: NewProgramArgs, s: Workspace, by: Actor | None) -> bool:
    return not a.force and f"{a.program_dir}/program.yml" in s.files


def _skills_missing(a: DryRunArgs, s: Workspace, by: Actor | None) -> bool:
    return not skills_installed(s)


missing_name_and_check = Rule[NewArgs, Workspace](USAGE + "name, --check", _no_name_and_no_check, USAGE_ERROR)
missing_name = Rule[NewArgs, Workspace](USAGE + "name", _no_name, USAGE_ERROR)
missing_check = Rule[NewArgs, Workspace](USAGE + "--check", _no_check, USAGE_ERROR)
not_a_workflow_name = Rule[NewArgs, Workspace](
    "error: '{name}' is not a workflow name: use lowercase letters, digits and single dashes, starting with a letter",
    _not_a_name, REFUSED,
    why="the name becomes the command workhorse-NAME and the python package, so it is a kebab-case word.")
empty_check = Rule[NewArgs, Workspace](
    "error: --check is empty: give the shell command that decides when the work is done", _blank_check, REFUSED)
already_there = Rule[NewArgs, Workspace](
    "error: {target} already exists; pick another name or remove it", _target_exists, REFUSED,
    why="scaffolding never overwrites a distribution a person may have edited.")

okf_book_needs_its_skills = Rule[DryRunArgs, Workspace](_unreadable(OKF_BOOK_SKILLS), _skills_missing, REFUSED,
    why="the dry run resolves every skill a prompt names, and refuses when the repo and home hold none of them.")

program_needs_dir_and_code_root = Rule[NewProgramArgs, Workspace](
    PROGRAM_USAGE + "--dir, --code-root", _no_dir_and_no_code_root, USAGE_ERROR)
program_needs_dir = Rule[NewProgramArgs, Workspace](PROGRAM_USAGE + "--dir", _no_dir, USAGE_ERROR)
program_needs_code_root = Rule[NewProgramArgs, Workspace](PROGRAM_USAGE + "--code-root", _no_code_root, USAGE_ERROR)
program_already_there = Rule[NewProgramArgs, Workspace](
    "[new_program] scaffolding {program_dir} (repo=<sandbox>)\n"
    "[new_program] refusing to overwrite <sandbox>/{program_dir}/program.yml (pass --force)",
    _program_exists, REFUSED,
    why="a program folder holds a ledger a person fills in, so the scaffolder stops at the first file it would replace.")
