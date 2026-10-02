#!/usr/bin/env python3
"""Hold the implementing agent at Stop until a fresh reviewer passes its diff."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from fnmatch import fnmatch
from pathlib import Path

CONFIG = ".agent-checks.toml"
TABLE = "code-review"
PROMPT_PATH = Path(__file__).resolve().with_name("review_prompt.md")
SKILLS_DIR = Path(__file__).resolve().parents[2]
HOOK_STATE_FILE = "review-gate.json"
BASE_STATE_FILE = "review-gate-base.json"

PRIMARY_MODEL = "sonnet"
TIEBREAK_MODEL = "opus"
ROUNDS_BEFORE_TIEBREAK = 2
MAX_BLOCKED_ROUNDS = 10
PROMPT_BUDGET_TOKENS = 60_000
CHARS_PER_TOKEN = 4
MAX_BATCHES = 4
MAX_TURNS = 40
TIMEOUT_SECONDS = 900

SOURCE_EXTENSIONS = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".dart",
        ".ex",
        ".exs",
        ".go",
        ".h",
        ".hpp",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".lua",
        ".mjs",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".swift",
        ".ts",
        ".tsx",
    }
)

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "rule": {"type": "string"},
                    "problem": {"type": "string"},
                },
                "required": ["file", "line", "rule", "problem"],
            },
        }
    },
    "required": ["findings"],
}


class ConfigError(Exception):
    pass


class ReviewError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    extensions: frozenset[str]
    exclude: tuple[str, ...]
    rules: tuple[str, ...]

    def covers(self, path: str) -> bool:
        return Path(path).suffix in self.extensions and not any(
            fnmatch(path, pattern) for pattern in self.exclude
        )


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    problem: str

    def render(self) -> str:
        return f"{self.file}:{self.line} [{self.rule}] {self.problem}"


@dataclass(frozen=True)
class Verdict:
    model: str
    findings: tuple[Finding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings


Reviewer = Callable[[str, str], Verdict]


@dataclass(frozen=True)
class GateState:
    base_tree: str | None
    base_head: str | None
    blocked_rounds: int


EMPTY_STATE = GateState(base_tree=None, base_head=None, blocked_rounds=0)


@dataclass(frozen=True)
class PendingChange:
    head: str
    base_tree: str
    tree: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class ReviewBatches:
    batches: tuple[str, ...]
    too_large: tuple[Finding, ...]


@dataclass(frozen=True)
class BatchedVerdict:
    verdict: Verdict
    unreviewed: str | None


@dataclass(frozen=True)
class Block:
    reason: str

    def payload(self) -> dict[str, str]:
        return {"decision": "block", "reason": self.reason}


@dataclass(frozen=True)
class GiveUp:
    message: str

    def payload(self) -> dict[str, str]:
        return {"systemMessage": self.message}


type Outcome = Block | GiveUp | None


def git(repo: Path, *args: str, env: Mapping[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def git_succeeds(repo: Path, *args: str) -> bool:
    probe = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    return probe.returncode == 0


def git_path(repo: Path, name: str) -> Path:
    return repo / git(repo, "rev-parse", "--git-path", name)


def snapshot_tree(repo: Path) -> str:
    with tempfile.TemporaryDirectory() as scratch:
        index = Path(scratch) / "index"
        live_index = git_path(repo, "index")
        if live_index.is_file():
            shutil.copy2(live_index, index)
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        git(repo, "add", "-A", env=env)
        return git(repo, "write-tree", env=env)


def config_strings(table: Mapping[str, object], key: str) -> tuple[str, ...] | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{CONFIG} [{TABLE}] {key} must be a list of strings")
    return tuple(str(item) for item in value)


def load_settings(repo: Path) -> Settings:
    path = repo / CONFIG
    document = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    table = document.get(TABLE, {})
    if not isinstance(table, dict):
        raise ConfigError(f"{CONFIG} [{TABLE}] must be a table")
    extensions = config_strings(table, "extensions")
    return Settings(
        extensions=SOURCE_EXTENSIONS if extensions is None else frozenset(extensions),
        exclude=config_strings(table, "exclude") or (),
        rules=config_strings(table, "rules") or (),
    )


def text_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def load_state(repo: Path, name: str) -> GateState:
    path = git_path(repo, name)
    if not path.is_file():
        return EMPTY_STATE
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return EMPTY_STATE
    rounds = raw.get("blocked_rounds")
    return GateState(
        base_tree=text_or_none(raw.get("base_tree")),
        base_head=text_or_none(raw.get("base_head")),
        blocked_rounds=rounds if isinstance(rounds, int) else 0,
    )


def save_state(repo: Path, name: str, state: GateState) -> None:
    body = {
        "base_tree": state.base_tree,
        "base_head": state.base_head,
        "blocked_rounds": state.blocked_rounds,
    }
    git_path(repo, name).write_text(json.dumps(body) + "\n", encoding="utf-8")


def next_state(state: GateState, change: PendingChange, verdict: Verdict) -> GateState:
    if verdict.passed:
        return GateState(base_tree=change.tree, base_head=change.head, blocked_rounds=0)
    return GateState(
        base_tree=change.base_tree,
        base_head=state.base_head or change.head,
        blocked_rounds=state.blocked_rounds + 1,
    )


def resolve_base(repo: Path, state: GateState, head: str, base: str | None) -> str:
    if base is not None:
        return git(repo, "rev-parse", f"{base}^{{tree}}")
    pinned = state.base_tree
    if pinned and git_succeeds(repo, "cat-file", "-e", f"{pinned}^{{tree}}"):
        if state.blocked_rounds > 0:
            return pinned
        if state.base_head and git_succeeds(
            repo, "merge-base", "--is-ancestor", state.base_head, head
        ):
            return pinned
    return git(repo, "rev-parse", "HEAD^{tree}")


def pending_change(
    repo: Path, settings: Settings, state: GateState, base: str | None
) -> PendingChange:
    head = git(repo, "rev-parse", "HEAD")
    base_tree = resolve_base(repo, state, head, base)
    tree = snapshot_tree(repo)
    names = git(
        repo, "diff", "--name-only", "--no-renames", base_tree, tree
    ).splitlines()
    return PendingChange(
        head=head,
        base_tree=base_tree,
        tree=tree,
        paths=tuple(p for p in names if settings.covers(p)),
    )


def split_diff(diff: str) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    for body in f"\n{diff}".split("\ndiff --git ")[1:]:
        header = body.split("\n", 1)[0]
        pieces.append((header.rsplit(" b/", 1)[-1], f"diff --git {body}\n"))
    return pieces


def too_large(path: str, problem: str) -> Finding:
    return Finding(file=path, line=1, rule="too-large", problem=problem)


def pack(pieces: list[tuple[str, str]], budget_tokens: int) -> ReviewBatches:
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    oversized = tuple(
        too_large(
            path,
            f"its diff is about {len(text) // CHARS_PER_TOKEN} tokens, over the {budget_tokens}-token"
            " review budget. Split the change so each file's diff fits.",
        )
        for path, text in pieces
        if len(text) > budget_chars
    )
    if oversized:
        return ReviewBatches(batches=(), too_large=oversized)
    batches: list[str] = []
    current = ""
    for _, text in pieces:
        if current and len(current) + len(text) > budget_chars:
            batches.append(current)
            current = ""
        current += text
    if current:
        batches.append(current)
    if len(batches) > MAX_BATCHES:
        problem = f"the change needs {len(batches)} review batches, over the cap of {MAX_BATCHES}. Land it in smaller steps."
        return ReviewBatches(batches=(), too_large=(too_large(pieces[0][0], problem),))
    return ReviewBatches(batches=tuple(batches), too_large=())


def rule_documents(repo: Path, settings: Settings) -> list[Path]:
    found = sorted(SKILLS_DIR.glob("*code-structure/SKILL.md"))
    return [*found, *(repo / rule for rule in settings.rules)]


def shown(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)


def rubric_for(repo: Path, settings: Settings) -> str:
    documents = rule_documents(repo, settings)
    listing = (
        "\n".join(f"- `{shown(repo, doc)}`" for doc in documents)
        or "- none is installed"
    )
    return PROMPT_PATH.read_text(encoding="utf-8").replace("{rule_documents}", listing)


def plan_review(repo: Path, change: PendingChange, rubric: str) -> ReviewBatches:
    diff = git(
        repo,
        "diff",
        "--no-color",
        "-M",
        "-D",
        change.base_tree,
        change.tree,
        "--",
        *change.paths,
    )
    return pack(split_diff(diff), PROMPT_BUDGET_TOKENS - len(rubric) // CHARS_PER_TOKEN)


def model_for(state: GateState) -> str:
    return (
        TIEBREAK_MODEL
        if state.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK
        else PRIMARY_MODEL
    )


def run_batches(
    rubric: str, plan: ReviewBatches, reviewer: Reviewer, model: str
) -> BatchedVerdict:
    findings = list(plan.too_large)
    for done, batch in enumerate(plan.batches):
        try:
            findings.extend(reviewer(rubric + batch, model).findings)
        except ReviewError as exc:
            unreviewed = f"batch {done + 1} of {len(plan.batches)}: {exc}"
            return BatchedVerdict(Verdict(model, tuple(findings)), unreviewed)
    return BatchedVerdict(Verdict(model, tuple(findings)), None)


def parse_finding(item: object) -> Finding:
    if not isinstance(item, dict):
        raise ReviewError(f"the reviewer returned a malformed finding: {item!r}")
    file, line, rule, problem = (
        item.get(key) for key in ("file", "line", "rule", "problem")
    )
    if not (
        isinstance(file, str)
        and isinstance(line, int)
        and isinstance(rule, str)
        and isinstance(problem, str)
    ):
        raise ReviewError(
            f"the reviewer returned a finding with a missing or mistyped field: {item!r}"
        )
    return Finding(file=file, line=line, rule=rule, problem=problem)


def findings_from_output(
    completed: subprocess.CompletedProcess[str],
) -> tuple[Finding, ...]:
    try:
        payload: object = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReviewError(
            f"exit {completed.returncode}: {completed.stderr.strip()[-500:]}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("is_error"):
        raise ReviewError(f"the reviewer failed: {str(payload)[-500:]}")
    structured: object = payload.get("structured_output")
    items = structured.get("findings") if isinstance(structured, dict) else None
    if not isinstance(items, list):
        raise ReviewError(f"the reviewer returned no findings list: {structured!r}")
    return tuple(parse_finding(item) for item in items)


def claude_reviewer(repo: Path, extra_dirs: list[Path]) -> Reviewer:
    def review(prompt: str, model: str) -> Verdict:
        command = [
            "claude",
            "-p",
            "--model",
            model,
            "--max-turns",
            str(MAX_TURNS),
            "--tools",
            "Read,Grep,Glob",
            "--setting-sources",
            "user",
            "--settings",
            json.dumps({"disableAllHooks": True}),
            "--json-schema",
            json.dumps(VERDICT_SCHEMA),
            "--output-format",
            "json",
            "--no-session-persistence",
        ]
        for directory in extra_dirs:
            command += ["--add-dir", str(directory)]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                cwd=repo,
                check=False,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise ReviewError(
                f"the reviewer ran past {TIMEOUT_SECONDS} seconds"
            ) from exc
        except OSError as exc:
            raise ReviewError(str(exc)) from exc
        return Verdict(model=model, findings=findings_from_output(completed))

    return review


def outside_dirs(repo: Path, settings: Settings) -> list[Path]:
    return sorted(
        {
            doc.parent.parent
            for doc in rule_documents(repo, settings)
            if not doc.is_relative_to(repo)
        }
    )


def unfinished_reason(review: BatchedVerdict) -> str:
    found = [f"- {finding.render()}" for finding in review.verdict.findings]
    return "\n".join(
        [
            f"The review gate ({review.verdict.model}) failed on {review.unreviewed},"
            " so your diff is not approved and this round does not count.",
            "Fix what the finished batches found, then stop again."
            if found
            else "Stop again to review the whole diff.",
            *found,
        ]
    )


def block_reason(verdict: Verdict, state: GateState) -> str:
    lines = [
        f"The review gate ({verdict.model}, round {state.blocked_rounds}) found problems in your diff.",
        "Fix each one, then stop again. The next stop reviews the whole diff since the last approval.",
        *(f"- {finding.render()}" for finding in verdict.findings),
    ]
    if state.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK:
        lines.append(
            f"The next round goes to the tie-break reviewer, {TIEBREAK_MODEL}."
        )
    return "\n".join(lines)


def give_up_message(verdict: Verdict, rounds: int) -> str:
    return "\n".join(
        [
            f"The review gate ({verdict.model}) gave up after {rounds} blocked rounds, so this stop goes through unapproved.",
            "The next stop reviews the same diff again, from round 1.",
            *(f"- {finding.render()}" for finding in verdict.findings),
        ]
    )


def hook_decision(repo: Path, reviewer: Reviewer) -> Outcome:
    settings = load_settings(repo)
    state = load_state(repo, HOOK_STATE_FILE)
    change = pending_change(repo, settings, state, None)
    if not change.paths:
        return None
    rubric = rubric_for(repo, settings)
    review = run_batches(
        rubric, plan_review(repo, change, rubric), reviewer, model_for(state)
    )
    if review.unreviewed is not None:
        return Block(unfinished_reason(review))
    updated = next_state(state, change, review.verdict)
    save_state(repo, HOOK_STATE_FILE, updated)
    if review.verdict.passed:
        return None
    if updated.blocked_rounds >= MAX_BLOCKED_ROUNDS:
        save_state(repo, HOOK_STATE_FILE, replace(updated, blocked_rounds=0))
        return GiveUp(give_up_message(review.verdict, updated.blocked_rounds))
    return Block(block_reason(review.verdict, updated))


def review_from(repo: Path, base: str, reviewer: Reviewer) -> int:
    settings = load_settings(repo)
    state = load_state(repo, BASE_STATE_FILE)
    change = pending_change(repo, settings, state, base)
    if not change.paths:
        print(f"verdict: pass (no source file changed since {base})")
        return 0
    rubric = rubric_for(repo, settings)
    review = run_batches(
        rubric, plan_review(repo, change, rubric), reviewer, model_for(state)
    )
    if review.unreviewed is not None:
        print(unfinished_reason(review))
        return 1
    updated = next_state(state, change, review.verdict)
    save_state(repo, BASE_STATE_FILE, updated)
    outcome = "pass" if review.verdict.passed else "block"
    print(
        f"verdict: {outcome} ({review.verdict.model}, {len(change.paths)} files since {base})"
    )
    for finding in review.verdict.findings:
        print(f"- {finding.render()}")
    if not review.verdict.passed and updated.blocked_rounds >= ROUNDS_BEFORE_TIEBREAK:
        print(f"The next round goes to the tie-break reviewer, {TIEBREAK_MODEL}.")
    return 0 if review.verdict.passed else 1


def stop_event_repo(text: str) -> Path | None:
    try:
        payload: object = json.loads(text or "{}")
    except json.JSONDecodeError:
        return None
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    if not isinstance(cwd, str):
        return None
    probe = subprocess.run(
        ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    return Path(probe.stdout.strip()) if probe.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--hook", action="store_true", help="run as the Claude Code Stop hook"
    )
    mode.add_argument("--base", help="review the working tree against this revision")
    args = parser.parse_args(argv)
    if args.hook:
        repo = stop_event_repo(sys.stdin.read())
        if repo is None:
            return 0
        outcome = hook_decision(
            repo, claude_reviewer(repo, outside_dirs(repo, load_settings(repo)))
        )
        if outcome is not None:
            print(json.dumps(outcome.payload()))
        return 0
    repo = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
    return review_from(
        repo, args.base, claude_reviewer(repo, outside_dirs(repo, load_settings(repo)))
    )


if __name__ == "__main__":
    sys.exit(main())
