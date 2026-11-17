"""What each command does to the directory and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Select, Transaction, Update

from ..fixtures import DryRunArgs, NewArgs
from . import rules
from .files import SKILL_NAME, SKILLS, RUN, TREE, FileRecord
from .state import Workspace


def write(s: Workspace, path: str, *strings: str) -> Create | Update:
    """The change that leaves this file holding these strings."""
    record = FileRecord.holding(path, *strings)
    return Update(s.files, path, record) if path in s.files else Create(s.files, record)


class RunNew(Action[NewArgs, Workspace]):
    accept = NewArgs
    rules = (
        rules.missing_name_and_check,
        rules.missing_name,
        rules.missing_check,
        rules.not_a_workflow_name,
        rules.empty_check,
        rules.already_there,
    )

    @staticmethod
    def reduce(a: NewArgs, s: Workspace, by: Actor | None) -> Transaction:
        assert a.check is not None
        held = {
            "pyproject.toml": ('name = "fix-tests"', 'workhorse-fix-tests = "fix_tests.workflow:main"'),
            "README.md": ("# fix-tests", f"`{a.check}`"),
            "src/fix_tests/__init__.py": ("`workhorse-fix-tests`",),
            "src/fix_tests/workflow.py": (f'check: str = "{a.check}"',),
            "src/fix_tests/prompts/fix.md": ("Fix the cause, not the check.",),
        }
        changes = [write(s, f"{a.target}/{path}", *held[path]) for path in TREE]
        says = (
            f"wrote {a.shown}",
            "next:",
            f"  uv tool install {a.shown}",
            "  cd path/to/your/repo",
            "  workhorse-fix-tests run --dry-run",
        )
        return Transaction(*changes, says=says)


def ran(s: Workspace, workflow: str, class_name: str, flows: tuple[tuple[str, str], ...] = ()) -> Transaction:
    run = f"{workflow}-dry-run"
    return Transaction(
        write(s, f".agents/runs/{run}/run.json", RUN.format(workflow)),
        *(write(s, f".agents/runs/{run}/{folder}/_flow/run.json", RUN.format(name)) for folder, name in flows),
        says=(
            f"[workhorse] starting '{workflow}' {class_name} (run: {run})",
            f"[workhorse] dry-run ok — every node ran its stand-in — artifacts in <sandbox>/.agents/runs/{run}",
        ),
    )


class RunLoopRunner(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "loop-runner", "LoopRunner")


class RunResearch(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "research", "Research")


class RunAuthor(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "author", "Author", (("finalize", "Finalize"),))


class RunCoder(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "coder", "Coder", (("book_qa", "BookQa"), ("dev", "Dev"), ("docs", "Docs"), ("fix", "Fix"), ("qa", "Qa")))


class RunOkfBook(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs
    rules = (rules.okf_book_needs_its_skills,)

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "okf-book", "WritePythonBook")


class RunReviewDebt(Action[DryRunArgs, Workspace]):
    accept = DryRunArgs

    @staticmethod
    def reduce(a: DryRunArgs, s: Workspace, by: Actor | None) -> Transaction:
        return ran(s, "review-debt", "ReviewDebt")


class ListFiles(Action[object, Workspace]):
    @staticmethod
    def reduce(a: object, s: Workspace, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)


class InstallSkillsByHand(Action[object, Workspace]):
    @staticmethod
    def reduce(a: object, s: Workspace, by: Actor | None) -> Transaction:
        return Transaction(*(write(s, f".claude/skills/{skill}/SKILL.md", SKILL_NAME.format(skill)) for skill in SKILLS))
