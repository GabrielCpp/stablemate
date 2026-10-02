"""What code does with one repair turn's changes: put back what its batch may not keep, then stamp and commit the rest.

Code puts back each page a turn changed that its batch may not keep, by the rules of `nodes/repair_put_back.py`.
Code then carves each endpoint the book holds inline onto a page of its own, and commits those pages with the turn.
A turn may delete a page the entries page links, so code drops that link and commits the entries page with the turn.

A page someone left uncommitted when the repair started has no committed copy of their edit to go
back to, so a turn that changed one waits for the operator. A commit the repo refuses waits for them too.

A small model reads the staged diff and names what the commit changed. When it cannot, the commit
keeps the fixed subject, so a repair never waits on its own message.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done
from workhorse_workflows.kit import diff_to_commit
from workhorse_workflows.okf_book.main.nodes.repair_batch_models import RepairBatch
from workhorse_workflows.okf_book.main.nodes.repair_put_back import (
    entry_pages_changed_beyond_links,
    pages_to_stamp,
    stamp_repaired_pages,
    turn_changes,
)
from workhorse_workflows.okf_book.shared.book_commits import repair_description_refusal, repaired_book_commit_message
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.shared.book_shape import carve_inline_endpoints, carved_pages
from workhorse_workflows.okf_book.shared.confine import Snapshot, committed_text, put_back_outside, restore
from workhorse_workflows.okf_book.shared.entries import drop_links, entries_path, links_to_deleted

UNCOMMITTED_PAGE_GATE = "uncommitted-page-changed.md"
DESCRIBE_LABEL = "describe-repair-commit"
DESCRIBE_TIMEOUT = 300.0
DIFF_LIMIT = 40_000
DESCRIBE_PROMPT = """Write the commit message for the repair of pages of the {{ service }} book.

The commit takes these paths:

{% for page in pages %}- {{ page }}
{% endfor %}
Here is what it records{% if truncated %}, cut at {{ limit }} characters{% endif %}:

```diff
{{ diff }}
```

Reply with only a JSON object, `{"description": "...", "body": "..."}`, written from the diff alone.
Run no command.

- The description follows `docs({{ service }}): ` in the subject, so the whole subject stays within 72
  characters. It is a lowercase imperative that names what changed for a reader of the book, such as
  "document the refund flow's error responses". It has no trailing period.
- The body is empty, or one to three lines wrapped at 72 columns saying why the pages changed.
"""


class RepairCommitDescription(BaseModel):
    """What the small model says one repair commit changed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str
    body: str = ""


class SettledTurn(BaseModel):
    """What the repair reads back from a settled turn: the pages it committed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: tuple[str, ...] = ()


class SettleRepairTurn(BookFlow):
    """Puts back what one repair turn changed but its batch may not keep, then stamps and commits the pages it repaired."""

    service: str = ""
    batch: RepairBatch
    closed_pages: tuple[str, ...] = ()
    before: Snapshot
    repair_run_dir: str = ""

    def start(self) -> Continue[...]:
        """Put back each path the turn changed outside the book, but the repair's own run directory."""
        stray = put_back_outside(self.root, self.service, self.before, Path(self.repair_run_dir))
        for path in stray:
            self.logger.warning("put back %s, which the repair turn changed outside its book", path)
        return Continue(stray, self.put_back_pages_batch_may_not_keep).because("put back the book pages the turn may not keep")

    def put_back_pages_batch_may_not_keep(self) -> Continue[...] | Await[...]:
        """Put back each book page the turn changed but may not keep: the entries page, a page its batch does not own, and a page an earlier batch closed.

        A page someone left uncommitted has no committed copy of their edit to go back to, so a turn
        that changed one waits for the operator.
        """
        changes = turn_changes(self.root, self.service, self.before, self.batch, self.closed_pages)
        unrestorable_uncommitted = restore(self.root, changes.to_put_back, self.before)
        for path in sorted(set(changes.to_put_back) - set(unrestorable_uncommitted) - {changes.entries_page}):
            self.logger.warning("put back %s, which the repair turn changed outside the pages its batch owns", path)
        kept = list(changes.kept)
        if unrestorable_uncommitted:
            return Await(
                self.run_dir / UNCOMMITTED_PAGE_GATE,
                "The repair turn changed pages someone left uncommitted, and code has no copy of their edits to put back:\n\n"
                + "\n".join(f"- {path}" for path in unrestorable_uncommitted)
                + "\n\nSort each page out in the repo, then answer here. No commit takes these pages.",
                self.put_back_entry_overreach,
                kept=kept,
            ).because("the repair turn changed a page someone left uncommitted")
        return Continue(changes.to_put_back, self.put_back_entry_overreach, kept=kept).because(
            "put back the entry pages the turn changed beyond link lines"
        )

    def put_back_entry_overreach(self, kept: list[str]) -> Continue[...]:
        """Put back each entry page the turn kept but changed beyond adding link lines."""
        overreach = entry_pages_changed_beyond_links(self.root, self.batch, kept)
        _ = restore(self.root, overreach, self.before)
        for path in overreach:
            self.logger.warning("put back %s, an entry page the repair turn changed beyond adding link lines", path)
        return Continue(overreach, self.carve_endpoints).because("carve the endpoints written inline")

    def carve_endpoints(self) -> Continue[...]:
        """Move each endpoint the book holds inline on a server page onto a page of its own, so the server page stays small enough for one writer."""
        carves = carve_inline_endpoints(self.root, self.service, frozenset(self.before.digests))
        for carve in carves:
            if carve.refusal:
                self.logger.warning("left the endpoints of %s inline: %s", carve.server, carve.refusal)
            else:
                self.logger.info("carved the endpoints of %s, writing %d pages", carve.server, len(carve.pages))
        carved = carved_pages(carves)
        return Continue(carved, self.stamp_pages, carved=carved).because("stamp the repaired pages")

    def stamp_pages(self, carved: tuple[str, ...] = ()) -> Continue[...]:
        """Stamp each page the turn changed that its batch owns, but the entries page and the pages someone left uncommitted, and each page a carve wrote."""
        pages = tuple(sorted({*pages_to_stamp(self.root, self.service, self.before, self.batch), *carved}))
        changed_journey_pages = sorted(set(pages) - set(self.batch.page_paths))
        if changed_journey_pages:
            self.logger.info("the repair turn also changed %d journey pages: %s", len(changed_journey_pages), ", ".join(changed_journey_pages))
        stamp_repaired_pages(self.root, pages)
        return Continue(pages, self.drop_dead_entry_links, pages=pages).because("drop the entries links to pages the turn deleted")

    def drop_dead_entry_links(self, pages: tuple[str, ...]) -> Continue[...]:
        """Drop each entries link to a page the turn deleted, and commit the entries page with the turn's pages, since only code writes it.

        An entries page someone left uncommitted stays theirs, so code leaves it as it is. Code commits the
        entries page whenever it differs from HEAD, so a retry after the drop still commits it.
        """
        entries_page = entries_path(self.root, self.service).relative_to(self.root).as_posix()
        if entries_page in self.before.digests or not (self.root / entries_page).is_file():
            return Continue(pages, self.render_agent_files, pages=pages).because("render the agent files")
        dead_links = links_to_deleted(self.root, self.service, pages)
        if dead_links:
            drop_links(self.root, self.service, dead_links)
            self.logger.info("dropped the links of %s to pages the repair turn deleted", entries_page)
        if (self.root / entries_page).read_text(encoding="utf-8") != committed_text(self.root, entries_page):
            pages = (*pages, entries_page)
        return Continue(pages, self.render_agent_files, pages=pages).because("render the agent files")

    def render_agent_files(self, pages: tuple[str, ...]) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the repaired pages are committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render_agent_files, pages=pages)
        if waiting:
            return waiting
        return Continue(pages, self.describe_commit, pages=pages).because("describe the repaired pages")

    def describe_commit(self, pages: tuple[str, ...]) -> Continue[...]:
        """A small model names what the staged pages changed. A turn that fails, or a diff with nothing in it, keeps the fixed subject."""
        diff = diff_to_commit(self.root, *pages)
        if not diff:
            return Continue(pages, self.commit_pages, pages=pages, commit_message=repaired_book_commit_message(self.service)).because(
                "nothing staged to describe"
            )
        try:
            described = self.agent(
                DESCRIBE_PROMPT,
                label=DESCRIBE_LABEL,
                returns=RepairCommitDescription,
                power="low",
                timeout=DESCRIBE_TIMEOUT,
                args={
                    "service": self.service,
                    "pages": list(pages),
                    "diff": diff[:DIFF_LIMIT],
                    "truncated": len(diff) > DIFF_LIMIT,
                    "limit": DIFF_LIMIT,
                },
                cwd=self.root,
                accept=self._accept_description,
            )
        except (AgentTurnFailed, AgentTimeout) as ended:
            self.logger.warning("kept the fixed repair subject, since the describe turn ended without a reply: %s", ended)
            return Continue(pages, self.commit_pages, pages=pages, commit_message=repaired_book_commit_message(self.service)).because(
                "the describe turn failed"
            )
        message = repaired_book_commit_message(self.service, described.description, described.body)
        return Continue(pages, self.commit_pages, pages=pages, commit_message=message).because("commit the repaired pages")

    def _accept_description(self, described: RepairCommitDescription) -> None:
        refusal = repair_description_refusal(self.service, described.description)
        if refusal:
            raise ValueError(refusal)

    def commit_pages(self, pages: tuple[str, ...], commit_message: str = "") -> Await[...] | Done:
        """Commit the batch's pages under *commit_message*, else under the fixed subject. A refused commit waits for the operator, and its retry keeps the message."""
        message = commit_message or repaired_book_commit_message(self.service)
        waiting = self._commit_or_await(message, pages, self.commit_pages, pages=pages, commit_message=message)
        if waiting:
            return waiting
        return Done(SettledTurn(pages=pages)).because("the repaired pages are committed")
