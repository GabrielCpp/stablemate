from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import ostler_qa_diagnostics
import ostler_qa_transfer
from ostler_qa_checks import QaChecks
from ostler_qa_diagnostics import ARRIVAL_WAIT_S, DEVICE_LAYOUT_SCHEMA, SETTLE_WAIT_MS
from ostler_qa_elements import choose, name_pattern, template_pattern
from ostler_qa_settle import (
    ANNOUNCED_ROLES,
    PageScreen,
    Screen,
    announced,
    settle_screen,
)


class QaPage(QaChecks):
    """The browser and device surface of a scenario."""

    def by_role(self, role: str, *, name: str | None = None, template: str | None = None, within: Any = None, **kwargs: Any) -> Any:
        """The element with this role and name. A name addresses an element that carries it whole, never one whose longer name merely contains it.

        A page that shows no such element yet is waited on until one appears, so the choice is made against what it renders.
        A page that streams data never goes idle, so the element itself is the signal, not the network.
        A *template* names a control rendered once per item, so each hole matches any text and the first instance answers.
        A *within* container holds the search when the template is only holes, since its name then matches every control of that role on the page.
        A live region answers to the label it carries, or else to the text it announces, since a browser computes no name from an alert's or a status's content.
        """
        if role in ANNOUNCED_ROLES and isinstance(name, str) and not kwargs:
            found = announced(self.browser_page, role, name)
            if found.count() == 0:
                try:
                    found.first.wait_for(state="attached", timeout=SETTLE_WAIT_MS)
                except Exception:
                    return found
            return found
        if template is not None:
            found = (within or self.browser_page).get_by_role(role, name=template_pattern(template), **kwargs)
            try:
                found.first.wait_for(state="attached", timeout=SETTLE_WAIT_MS)
            except Exception:
                pass
            return found.first
        if not isinstance(name, str) or not name.split() or "exact" in kwargs:
            return self.browser_page.get_by_role(role, name=name, **kwargs)
        found = self.browser_page.get_by_role(role, name=name_pattern(name), **kwargs)
        if found.count() == 0:
            try:
                found.first.wait_for(state="attached", timeout=SETTLE_WAIT_MS)
            except Exception:
                return found
        return found

    def by_label(self, text: str, **kwargs: Any) -> Any:
        return self.browser_page.get_by_label(text, **kwargs)

    def by_test_id(self, value: str) -> Any:
        return self.browser_page.get_by_test_id(value)

    def by_text(self, text: str | re.Pattern[str], **kwargs: Any) -> Any:
        return self.browser_page.get_by_text(text, **kwargs)

    def by_css(self, selector: str) -> Any:
        return self.browser_page.locator(selector)

    def goto(self, url: str, **kwargs: Any) -> Any:
        """Navigate a relative path against the target's `base_url`, once a save the last step started has landed."""
        recorder = self.diagnostics
        if recorder is not None and hasattr(recorder, "writes_done"):
            recorder.writes_done()
        return self.browser_page.goto(self.http.url_for(url), **kwargs)

    def paste(self, locator: Any, *, text: str | None = None, html: str | None = None) -> None:
        """Paste *text* or *html* into *locator*, as the user's clipboard would."""
        ostler_qa_transfer.paste(locator, text=text, html=html)

    def drop(self, locator: Any, file: str) -> None:
        """Drop the checkout's *file* on *locator*, as a file manager's drag would."""
        ostler_qa_transfer.drop(locator, self.root / file)

    def select(self, locator: Any, option: str) -> None:
        """Make the chooser *locator* hold *option*, as the user picking it would."""
        choose(self.browser_page, locator, option)

    def upload(self, locator: Any, file: str) -> None:
        """Hand *locator* the checkout's *file*, as the user picking it in the file picker would."""
        ostler_qa_transfer.upload(self.browser_page, locator, self.root / file)

    def back(self) -> Any:
        """Go back one entry in the page's history, as the browser's Back button does."""
        return self.browser_page.go_back()

    def print_page(self) -> None:
        """Lay the page out for printing, as the browser does when the user prints it, until the scenario ends."""
        self.browser_page.emulate_media(media="print")

    def answer_dialogs(self, answer: str) -> None:
        """Answer every dialog the page opens from here on with *answer*, as the user would click OK or Cancel."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "answer_dialogs"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} answers a browser dialog, but its target "
                f"'{self.target.name}' declares driver '{self.target.driver}'. Only "
                "driver='playwright' opens a page that shows one"
            )
        recorder.answer_dialogs(answer)

    def window(self) -> Any:
        """Open an observation window over the exchanges this page is about to make."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "window"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} reads an HTTP exchange the browser made, but "
                f"its target '{self.target.name}' declares driver '{self.target.driver}' — "
                "only driver='playwright' records what the page requested"
            )
        return recorder.window()

    def intercept(self, effect: str, **params: Any) -> None:
        """Alter or keep back the server's answer to one request, so a `verify:` can prove the screen did not take its figures from it, or read a state that lasts only until it arrives."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "intercept"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} intercepts a request the browser makes, but "
                f"its target '{self.target.name}' declares driver '{self.target.driver}' — "
                "only driver='playwright' can alter what the page receives"
            )
        recorder.intercept(effect, **params)

    def release(self, event: str) -> None:
        """Let the requests a `hold` on *event* kept open go on to the server."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "release"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} releases a request the browser made, but "
                f"its target '{self.target.name}' declares driver '{self.target.driver}' — "
                "only driver='playwright' can keep back what the page receives"
            )
        recorder.release(event)

    def mark(self) -> int:
        """The number of the next request the page makes, to hand `settle` as the point after which its requests count."""
        recorder = self.diagnostics
        if recorder is None or not hasattr(recorder, "mark"):
            raise RuntimeError(
                f"scenario {self.scenario_id!r} marks the requests the browser made, but "
                f"its target '{self.target.name}' declares driver '{self.target.driver}' — "
                "only driver='playwright' records what the page requested"
            )
        return recorder.mark()

    def settle(
        self,
        node: str,
        *,
        since: int | None = None,
        requests: Sequence[tuple[str, str]] = (),
        busy: Mapping[str, Any] | None,
        states: Mapping[str, Sequence[Mapping[str, Any]]],
        expect: str,
        covers: Sequence[str] | None = None,
        origins: Sequence[str] = (),
    ) -> bool:
        """Wait for a screen to settle, then record whether the state it settled on is the one the book names.

        The screen has `ceiling_s` seconds, shared by every wait: its requests answering, its busy sign going, a declared state holding. A device has no request feed, so only a browser waits on `requests` or takes `origins`. With `origins`, a `fetch` or `xhr` request since *since* to the page's own origin or one of them that `requests` do not declare fails the settle.
        """
        driver = self.target.driver
        if driver == "playwright":
            self.mark()
            screen: Screen = PageScreen(self.browser_page)
            exchanges = self.diagnostics
            watched = [self.browser_page.url, *origins] if origins else []
        elif driver == "maestro":
            if requests or origins:
                raise ValueError(
                    f"scenario {self.scenario_id!r} settles '{node}' on a device with requests to wait for, "
                    "and a device has no request feed"
                )
            watched = []
            screen = ostler_qa_diagnostics.harness_module("ostler_qa_hierarchy").DeviceScreen()
            exchanges = None
        else:
            raise RuntimeError(
                f"scenario {self.scenario_id!r} settles '{node}' on a '{driver}' target, which shows no "
                "screen to wait for — declare the target with driver='playwright' or driver='maestro'"
            )
        settled = settle_screen(
            screen, exchanges, node,
            since=since or 0, requests=requests, busy=busy, states=states, expect=expect, ceiling_s=self.ceiling_s,
            origins=watched,
        )
        return self._record(settled.message, settled.passed, settled.held, expect, covers)

    def capture_text(self, key: str, locator: Any) -> str:
        """Capture a locator's text — a defect if it matches nothing on the page."""
        if locator.count() == 0:
            detail = f"capture {key!r} locator matched no elements on the page"
            self._fault(self.scenario_id, -1, "capture", "defect", detail)
            raise RuntimeError(f"qa {self.scenario_id!r}: {detail}")
        value = locator.inner_text()
        self.capture(key, value)
        return value

    def screenshot(self, name: str = "") -> Path:
        """Photograph the page, measure where it put its content, and register both."""
        path = self.dir / "screenshots" / f"{self.scenario_id}-{name or 'screenshot'}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.browser_page.screenshot(path=str(path), full_page=True)
        self._recorder.emit({"type": "artifact", "path": str(path), "kind": "screenshot"})
        self.diagnostics.measure(path)
        return path

    def device_screenshot(self, name: str = "", *, source: str = "maestro") -> Path:
        """The same thing for a phone: photograph the screen, and measure what is on it."""
        hierarchy = ostler_qa_diagnostics.harness_module("ostler_qa_hierarchy")
        path = self.dir / "screenshots" / f"{self.scenario_id}-{name or 'screenshot'}.png"
        hierarchy.screenshot(path)
        self._recorder.emit({"type": "artifact", "path": str(path), "kind": "screenshot"})
        frame, elements = hierarchy.scan(source=source)
        scan = ostler_qa_diagnostics.harness_module("ostler_qa_scan")
        regions = scan.merge_rects(elements)
        measured = {"schema": DEVICE_LAYOUT_SCHEMA, **scan.summarize(frame, regions)}
        for artifact, payload, kind in (
            (path.with_suffix(".layout.json"), measured, "layout"),
            (path.with_suffix(".regions.json"), regions, "regions"),
        ):
            artifact.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self._recorder.emit({"type": "artifact", "path": str(artifact), "kind": kind})
        return path

    def _settle(self, arrives: str) -> None:
        """Give a client-side redirect and the screen's own loads time to finish before the photograph."""
        page = self.browser_page
        pattern = re.compile(arrives)
        deadline = time.monotonic() + ARRIVAL_WAIT_S
        while pattern.fullmatch(str(page.url)) is None and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        try:
            page.wait_for_load_state("networkidle", timeout=SETTLE_WAIT_MS)
        except Exception:
            return

    @property
    def browser_page(self) -> Any:
        if self.page is None:
            raise RuntimeError(
                f"scenario {self.scenario_id!r} reaches for the browser, but its target "
                f"'{self.target.name}' declares driver '{self.target.driver}' — declare the "
                "target with driver='playwright' to get a page"
            )
        return self.page
