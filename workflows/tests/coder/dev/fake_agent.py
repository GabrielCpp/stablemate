"""A scripted fake of the dev turn and the resolver, with the constants its answers carry."""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse.runner.failure import TurnDeadlineExceeded

from workhorse_workflows.coder.shared import commits
from workhorse_workflows.coder.shared.review import ANSWERS_FILE
from workhorse_workflows.kit.git import commit_all


RED_MAKEFILE = "lint:\n\t@echo 'links.go:1: undefined: allowList'; exit 1\n"

TEST_NAME = "TestRejectsRelativeDestination"

BLOCK_NOTE = "nobody has said whether a protocol-relative link counts as relative"

OPERATOR_ANSWER = "A protocol-relative link counts as external, so reject it."

API_SERVICE: dict[str, Any] = {
    "repo": "api",
    "path": ".",
    "type": "go",
    "plan_file": "plan-api.md",
}

FINDINGS: list[dict[str, Any]] = [
    {
        "target": "api/links.go:3",
        "issue": "a destination starting with `//` passes as internal",
        "repair": "treat a protocol-relative destination as external",
        "category": "Bug",
        "score": 90,
    },
    {
        "target": "api/links.go:1",
        "issue": "the validator could reuse the url package's parser",
        "repair": "parse with net/url",
        "category": "Reuse",
        "score": 40,
    },
]


def git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class FakeAgent:
    """The dev turn and the resolver, scripted on the flow's arms."""

    def __init__(
        self,
        workspace: dict[str, Path],
        *,
        blocked: int = 0,
        red: int = 0,
        unanswered: int = 0,
        stray: int = 0,
        also_fixed: tuple[str, ...] = (),
        follow_ups: tuple[dict[str, Any], ...] = (),
        outside: dict[str, str] | None = None,
        walk: tuple[int, ...] = (1,),
        failed: tuple[str, ...] = (),
        repo: str = "api",
        blocked_in: str = "review",
        departures: tuple[str, ...] = (),
        advise_from: int = 1,
        consult_from: int = 1,
        session: Callable[[int], str] | None = None,
        cut: tuple[str, ...] = (),
    ) -> None:
        self.cut = set(cut)
        self.nodes: list[Any] = []
        self.kwargs: list[dict[str, Any]] = []
        self.blocked_in = blocked_in
        self.departures = departures
        self.advise_from = advise_from
        self.consult_from = consult_from
        self.session = session
        self.workspace = workspace
        self.repo = repo
        self.outside = dict(outside or {})
        self.failed = failed
        self.walk = walk
        self.follow_ups = follow_ups
        self.also_fixed = also_fixed
        self.blocked = blocked
        self.red = red
        self.unanswered = unanswered
        self.stray = stray
        self.prefix = ""
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []
        self.powers: list[tuple[str, str | None]] = []
        self.rebriefs: list[Callable[[], str] | None] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        self.powers.append((stem, node.power))
        self.rebriefs.append(kwargs.get("rebrief"))
        self.nodes.append(node)
        self.kwargs.append(kwargs)
        if stem in self.cut:
            self.cut.discard(stem)
            raise TurnDeadlineExceeded(stem, node.deadline, node.deadline + 1.0)
        if self.session is not None and len(args) > 1:
            chain = Path(args[1])
            chain.parent.mkdir(parents=True, exist_ok=True)
            chain.write_text(self.session(len(self.calls)), encoding="utf-8")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def rebriefs_for(self, stem: str) -> list[Callable[[], str] | None]:
        return [r for s, r in zip(self.calls, self.rebriefs, strict=True) if s == stem]

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    def _dev_plan(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The plan phase: ready, or blocked while `blocked` counts it down."""
        if self.blocked_in == "plan" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        return {"status": "ready", "notes": "planned"}

    def _dev_build(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The build phase: ready with its departures, advised from the `advise_from`th turn on."""
        if self.blocked_in == "build" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        advice = "keep it" if nth >= self.advise_from else ""
        return {
            "status": "ready",
            "notes": "built",
            "departures": [
                {"change": change, "reason": "the plan fails a gate", "advice": advice}
                for change in self.departures
            ],
        }

    def _dev_follow_up(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """A later turn of a phase: what the phase's own turn would answer."""
        phase = str(data["phase"])
        handler = getattr(self, f"_dev_{phase}")
        spec = Path(str(data["spec_dir"]))
        carried = {
            **data,
            "answers_file": str(spec / ANSWERS_FILE),
            "review_prefix": self.prefix,
        }
        return handler(carried, self.counts()[f"dev-{phase}"] + nth)

    def _dev_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Build, commit, write the plan and the answers, and report the review's findings once."""
        if self.blocked_in == "review" and nth <= self.blocked:
            return {"status": "blocked", "notes": BLOCK_NOTE}
        spec = Path(str(data["spec_dir"]))
        spec.mkdir(parents=True, exist_ok=True)
        entries = "".join(
            f"\n### AC {n}: criterion {n}\n\n- **Met by**: {self.repo}/links.go:3\n"
            for n in self.walk
        )
        (spec / "plan.md").write_text(
            f"# Plan\n\nReject relative links in the api.\n\n## Acceptance Walk\n{entries}",
            encoding="utf-8",
        )
        if self.failed:
            log = spec / "qa" / "qa-run.ndjson"
            log.parent.mkdir(parents=True, exist_ok=True)
            rows: list[dict[str, Any]] = [
                {"kind": "session_start", "run_id": "qa-run-1"}
            ]
            rows += [
                {"kind": "assert", "scenario": sid, "action": 1, "result": "FAIL"}
                for sid in self.failed
            ]
            rows += [
                {
                    "kind": "assert",
                    "scenario": "scenario-ok",
                    "action": 1,
                    "result": "PASS",
                }
            ]
            log.write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
            )
        (spec / f"plan-{self.repo}.md").write_text(
            f"# Plan: {self.repo}\n\nValidate in links.go.\n", encoding="utf-8"
        )
        repo = self.workspace[self.repo]
        (repo / "links.go").write_text(
            f"package links\n\n// pass {nth}\n", encoding="utf-8"
        )
        (repo / "links_test.go").write_text(
            f"package links\n\nfunc {TEST_NAME}(t *testing.T) {{}}\n", encoding="utf-8"
        )
        makefile = repo / "Makefile"
        if nth <= self.red:
            makefile.write_text(RED_MAKEFILE, encoding="utf-8")
        elif makefile.exists():
            makefile.unlink()
        message = commits.message(
            "feat",
            commits.scope(repo.name),
            "reject relative link destinations",
            epic=str(data["epic"]),
            story=str(data["story_id"]),
        )
        commit_all(repo, message)
        if nth <= self.stray:
            (repo / "scratch.go").write_text("package links\n", encoding="utf-8")
        first = not self.prefix
        if first:
            self.prefix = str(data["review_prefix"])
        if nth > self.unanswered:
            sha = git_head(repo)
            Path(str(data["answers_file"])).write_text(
                f"## {self.prefix}1: fixed\n"
                f"- commit: {sha}\n"
                f"- path: {self.repo}/links.go\n"
                f"- test: {TEST_NAME}\n\n"
                f"## {self.prefix}2: declined\n"
                "Reason: coincidence: the story's technical notes keep the validator free of new imports; the url package parses another grammar.\n"
                + "".join(
                    f"\n## {item}: fixed\n- commit: {sha}\n- path: {self.repo}/links.go\n- test: {TEST_NAME}\n"
                    for item in self.also_fixed
                ),
                encoding="utf-8",
            )
        return {
            "status": "ready",
            "summary": "reject relative link destinations in the api",
            "notes": f"built and reviewed on pass {nth}",
            "services": [
                {**API_SERVICE, "repo": self.repo, "plan_file": f"plan-{self.repo}.md"}
            ],
            "findings": [
                {**f, "target": f["target"].replace("api/", f"{self.repo}/", 1)}
                for f in FINDINGS
            ]
            if first
            else [],
            "follow_ups": list(self.follow_ups) if first else [],
            "consults": [
                {
                    "finding": f"{self.prefix}2",
                    "question": "is the decline right?",
                    "advice": "yes",
                }
            ]
            if nth >= self.consult_from
            else [],
        }

    def _judge(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The judge's ruling: each scope subject its title names in `outside`, the rest at its default."""
        if data["kind"] == "scope":
            subjects: dict[str, str] = json.loads(str(data["subjects"]))
            return {
                "answers": {
                    rid: kind
                    for rid, text in subjects.items()
                    for title, kind in self.outside.items()
                    if text.startswith(f"{title}:")
                }
            }
        return {"answers": {}}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """The resolver's say on a block, which this fake declines to give."""
        return {"decision": "escalated", "summary": "only the operator can decide this"}
