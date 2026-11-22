"""The half of an operator gate that tries to answer the block before parking on it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workhorse.pyflow import AgentTimeout, Workflow
from workhorse._vendor.stablemate_core import books

from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.owner import cut_notes
from workhorse_workflows.coder.shared.schemas.dev import OperatorResolution
from workhorse_workflows.kit.schema import schema_block
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.kit import find_book_package, find_book_root, find_docs_root, find_repo_root

RESOLVER_POWER = "max"


@dataclass(frozen=True)
class ResolverCut:
    """A resolver turn that ran out of time or went quiet, with the block's notes and what cut it."""

    notes: str


class Resolving(Workflow):
    """The base of a flow whose blocks go to the resolver turn before the operator."""

    @property
    def _turn_s(self) -> float:
        """The wall-clock allowance of one turn of this flow, in seconds."""
        raise NotImplementedError

    def _resolver_turn(
        self,
        *,
        block_kind: str,
        notes: str,
        add_dirs: list[str],
        story: StoryPaths | None = None,
    ) -> OperatorResolution | ResolverCut:
        """Run the resolver turn on a block, or report it cut with the notes the operator should read."""
        try:
            return self.agent(
                "shared/prompts/resolve-operator.md",
                returns=OperatorResolution,
                power=RESOLVER_POWER,
                timeout=self._turn_s,
                deadline=self._turn_s,
                add_dirs=add_dirs,
                args=resolver_args(self, block_kind=block_kind, notes=notes, story=story),
            )
        except AgentTimeout as exc:
            return ResolverCut(f"{notes}\n\n{cut_notes('The resolver turn', exc)}")


def resolver_args(
    flow: Workflow,
    *,
    block_kind: str,
    notes: str,
    story: StoryPaths | None = None,
) -> dict[str, str]:
    """The template arguments a `shared/prompts/resolve-operator.md` turn takes."""
    ident: StoryPaths | Any = story if story is not None else flow.ctx
    return {
        "story_path": ident.story_path,
        "spec_dir": ident.spec_dir,
        "decisions_dir": str(decisions_dir(flow.repo_dir)),
        "book_root": str(find_book_root(flow.repo_dir)),
        "service_package": find_book_package(flow.repo_dir),
        "service_books": str(find_book_root(flow.repo_dir) / books.package_folder(find_book_package(flow.repo_dir))),
        "product_dir": str(books.product_folder(find_repo_root(flow.repo_dir)) or find_book_root(flow.repo_dir) / "product"),
        "block_kind": block_kind,
        "block_notes": notes,
        "result_schema": schema_block(OperatorResolution),
    }


def decisions_dir(repo_dir: str) -> Path:
    """Where this run's standing decisions live, absolute — see `paths.decisions_dir`."""
    return paths.decisions_dir(find_docs_root(repo_dir))


def answered(flow: Workflow, result: OperatorResolution, block_kind: str) -> bool:
    """Did the resolver settle the block itself, and say what settled it?"""
    if result.decision != "answered":
        return False
    flow.logger.info(
        "the %s block was resolved from what is already written down — %s%s",
        block_kind,
        result.summary or "no summary given",
        (
            f" (grounded in: {'; '.join(result.grounded)}"
            + (f", recorded as {result.record}" if result.record else "")
            + ")"
            if result.grounded
            else " — WITH NO GROUNDING CITED, which the prompt requires; check this one"
        ),
        extra={"activity": True},
    )
    return True


__all__ = [
    "RESOLVER_POWER",
    "ResolverCut",
    "Resolving",
    "answered",
    "decisions_dir",
    "resolver_args",
]
