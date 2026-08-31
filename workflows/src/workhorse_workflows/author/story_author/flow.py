"""Directly author one explicit story without selecting, branching, or committing."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done, Workflow, WorkflowFailed
from workhorse_workflows.author.main.nodes import (
    check_mockup_needed,
    check_story_feedback,
    check_story_grounding,
    load_config,
    record_attempt,
    validate_story,
)
from workhorse_workflows.author.shared import paths
from workhorse_workflows.author.shared.schemas import (
    AuditFinding,
    AuditResult,
    Config,
    MockupResult,
    OperatorResolution,
    WriteStoryResult,
)
from workhorse_workflows.author.story_author.nodes import migrate_story, record_story_audit
from workhorse_workflows.author.story_author.schemas import StoryAuthorDone, StoryTarget
from workhorse_workflows.kit.telemetry import counter_labels

MAX_REWORKS = 3
MAX_AUDIT_REWORKS = 1
MAX_RESOLVES = 2
UNBOUNDED = float("inf")
AUDIT_FINDING_FIELDS = ("id", "target", "issue", "repair")


def _format_audit_finding(finding: AuditFinding) -> str:
    issue = finding.issue.rstrip(". ")
    return f"{finding.id} [{finding.kind}] {finding.target}: {issue}. Repair: {finding.repair}"


def _audit_finding_problems(result: AuditResult) -> list[str]:
    problems: list[str] = []
    for index, finding in enumerate(result.findings, start=1):
        missing = [
            field for field in AUDIT_FINDING_FIELDS if not str(getattr(finding, field)).strip()
        ]
        if missing:
            problems.append(f"finding {index} missing {', '.join(missing)}")
    return problems


def _audit_notes(result: AuditResult) -> str:
    lines = [_format_audit_finding(finding) for finding in result.findings]
    if result.notes:
        lines.append(f"Summary: {result.notes}")
    return "\n".join(lines)


class StoryAuthor(Workflow):
    """Run the current per-story author pipeline for one caller-selected story."""

    epic: str = ""
    story: str = ""
    epics_dir: str = ""
    features_dir: str = ""
    mockup_dir: str = ""
    feedback_dir: str = ""
    operator_mode: str = "auto"

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = (
        "reworks",
        "resolves",
        "audit_reworks",
    )

    def setup(self) -> Config:
        """Resolve config only; direct story authoring never creates a branch."""
        cfg = self.call(load_config, "", self.epics_dir, mode="story-author")
        updates: dict[str, object] = {}
        if self.features_dir.strip():
            updates["features_dir"] = paths.features_dir(cfg.repo_root, self.features_dir)
        if self.mockup_dir.strip():
            updates["mockup_dir"] = self.mockup_dir.strip().rstrip("/")
        return cfg.model_copy(update=updates)

    def labels(self) -> dict[str, str]:
        return {"work_id": self.story, "epic": self.epic, "progress": "authoring one story"}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        return self.labels() | counter_labels(params, "story_author", self.BUDGET_LABELS)

    def _abs(self, relative: str) -> Path:
        return Path(self.ctx.repo_root) / relative

    def _resolve(self, target: StoryTarget, notes: str) -> OperatorResolution:
        self.logger.info("resolving the write-story block", extra={"activity": True})
        return self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power="high",
            timeout=UNBOUNDED,
            cwd=self.ctx.repo_root,
            args={
                "context_path": paths.story_context(target.story_dir),
                "epic_dir": target.epic_dir,
                "block_stage": "write-story",
                "block_notes": notes,
            },
        )

    def start(self) -> Continue:
        target = self.call(migrate_story, self.epic, self.story, self.ctx.epics_dir)
        gate = self.call(check_mockup_needed, target.story)
        if gate.required:
            return Continue(gate, self.design_mockup, target=target)
        return Continue(gate, self.write_story, target=target)

    def design_mockup(self, target: StoryTarget) -> Continue:
        result = self.agent(
            "story_author/prompts/design-mockup.md",
            returns=MockupResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
            },
        )
        return Continue(result, self.write_story, target=target, mockup=result.mockup)

    def write_story(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
        audit_reworks: int = 0,
        audit_findings: str = "",
    ) -> Continue | Await | Done:
        self.logger.info("authoring %s", target.story, extra={"activity": True})
        result = self.agent(
            "story_author/prompts/write-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_path": target.story_path,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
            },
        )
        if result.status == "blocked":
            return self._gate_story(result, result.notes, target, mockup, resolves)
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks,
            resolves=resolves,
            audit_reworks=audit_reworks,
            audit_findings=audit_findings,
        )

    def check_story(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
        audit_reworks: int = 0,
        audit_findings: str = "",
    ) -> Continue | Await | Done:
        structure = self.call(validate_story, target.story_dir)
        if not structure.ok:
            return self._rework(
                structure,
                structure.errors,
                target,
                mockup,
                reworks,
                resolves,
                audit_reworks,
                audit_findings,
            )
        grounding = self.call(
            check_story_grounding,
            target.story_dir,
            target.epic_dir,
            self.ctx.features_dir,
        )
        if not grounding.ok:
            return self._rework(
                grounding,
                grounding.errors,
                target,
                mockup,
                reworks,
                resolves,
                audit_reworks,
                audit_findings,
            )
        return Continue(
            grounding,
            self.audit_story,
            target=target,
            mockup=mockup,
            reworks=reworks,
            resolves=resolves,
            audit_reworks=audit_reworks,
            audit_findings=audit_findings,
        )

    def audit_story(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
        audit_reworks: int = 0,
        audit_findings: str = "",
    ) -> Continue | Await | Done:
        result = self.agent(
            "story_author/prompts/audit-story.md",
            returns=AuditResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_path": target.story_path,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "features_dir": self.ctx.features_dir,
                "prior_audit_findings": audit_findings,
            },
        )
        problems = _audit_finding_problems(result)
        if problems:
            raise WorkflowFailed(
                f"the audit of '{target.story}' returned findings the rework turn cannot act on: "
                + "; ".join(problems)
            )
        if not result.findings:
            return Continue(
                result,
                self.story_feedback,
                target=target,
                mockup=mockup,
                reworks=reworks,
                resolves=resolves,
            )
        notes = _audit_notes(result)
        if audit_reworks >= MAX_AUDIT_REWORKS:
            return self._gate_story(result, notes, target, mockup, resolves)
        return Continue(
            result,
            self.rework_story,
            target=target,
            mockup=mockup,
            notes=notes,
            reworks=reworks,
            resolves=resolves,
            audit_reworks=audit_reworks + 1,
            audit_findings=notes,
        )

    def _rework(
        self,
        result: object,
        notes: str,
        target: StoryTarget,
        mockup: str,
        reworks: int,
        resolves: int,
        audit_reworks: int,
        audit_findings: str,
    ) -> Continue | Await | Done:
        if reworks >= MAX_REWORKS:
            return self._gate_story(result, notes, target, mockup, resolves)
        return Continue(
            result,
            self.rework_story,
            target=target,
            mockup=mockup,
            notes=notes,
            reworks=reworks,
            resolves=resolves,
            audit_reworks=audit_reworks,
            audit_findings=audit_findings,
        )

    def _gate_story(
        self,
        result: object,
        notes: str,
        target: StoryTarget,
        mockup: str,
        resolves: int,
    ) -> Continue | Await | Done:
        resume = {
            "target": target,
            "mockup": mockup,
            "reworks": 0,
            "resolves": resolves,
        }
        context = self._abs(paths.story_context(target.story_dir))
        if self.operator_mode == "human":
            return Await(context, notes, self.write_story, **resume)
        if resolves >= MAX_RESOLVES:
            self.logger.warning(
                "parking story '%s' after %d autonomous resolutions: %s",
                target.story,
                resolves,
                notes,
            )
            return Done(StoryAuthorDone(
                status="blocked",
                epic=target.epic,
                story=target.story,
                story_path=target.story_path,
                mockup=mockup,
                notes=notes,
            ))
        return Continue(
            result,
            self.resolve_story,
            target=target,
            mockup=mockup,
            notes=notes,
            resolves=resolves,
        )

    def rework_story(
        self,
        target: StoryTarget,
        notes: str,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
        audit_reworks: int = 0,
        audit_findings: str = "",
    ) -> Continue:
        ledger = self.call(
            record_attempt,
            f"{target.story_dir.rstrip('/')}/attempts.md",
            str(reworks),
            notes,
        )
        result = self.agent(
            "story_author/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_path": target.story_path,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
                "validation_errors": notes,
                "prior_attempts": ledger.prior_attempts,
            },
        )
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks + 1,
            resolves=resolves,
            audit_reworks=audit_reworks,
            audit_findings=audit_findings,
        )

    def resolve_story(
        self,
        target: StoryTarget,
        notes: str,
        mockup: str = "",
        resolves: int = 0,
    ) -> Await:
        self._resolve(target, notes)
        return Await(
            self._abs(paths.story_context(target.story_dir)),
            notes,
            self.write_story,
            target=target,
            mockup=mockup,
            reworks=0,
            resolves=resolves + 1,
        )

    def story_feedback(
        self,
        target: StoryTarget,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue | Done:
        feedback = self.call(check_story_feedback, self.feedback_dir or str(self.run_dir))
        if feedback.present:
            return Continue(
                feedback,
                self.apply_feedback,
                target=target,
                mockup=mockup,
                notes=feedback.content,
                reworks=reworks,
                resolves=resolves,
            )
        self.call(record_story_audit, target.story_path)
        return Done(
            StoryAuthorDone(
                epic=target.epic,
                story=target.story,
                story_path=target.story_path,
                mockup=mockup,
            )
        )

    def apply_feedback(
        self,
        target: StoryTarget,
        notes: str,
        mockup: str = "",
        reworks: int = 0,
        resolves: int = 0,
    ) -> Continue:
        result = self.agent(
            "story_author/prompts/rework-story.md",
            returns=WriteStoryResult,
            power="high",
            cwd=self.ctx.repo_root,
            args={
                "epic": target.epic,
                "story_path": target.story_path,
                "story_slug": target.story,
                "story_dir": target.story_dir,
                "features_dir": self.ctx.features_dir,
                "mockup_dir": self.ctx.mockup_dir,
                "mockup_path": mockup,
                "validation_errors": "",
                "operator_feedback": notes,
            },
        )
        return Continue(
            result,
            self.check_story,
            target=target,
            mockup=mockup,
            reworks=reworks,
            resolves=resolves,
        )


__all__ = ["StoryAuthor"]
