"""Playwright lifecycle for a browser scenario, inside the scenario's own process.

Imported by `ostler_qa` only when a plan declares a `playwright` target, because playwright
is a dependency of the *project's* interpreter and of browser plans only — importing it at
module scope would make every command-only plan need it installed. There is no fallback
anywhere below: a browser target whose interpreter has no playwright is an error.

What lives here is everything that needs the page object: launch, context, tracing, the
diagnostics listeners, the failure screenshot. What stays in ostler is everything that
needs the run: xvfb and ffmpeg around this process, `ffprobe` verification of a recording
against the target's declared dimensions, and registration of every file named below. The
split is by which side owns the thing, not by which is easier — a diagnostics listener
cannot see the page from ostler, and a recording policy cannot see the run from here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

#: Stamped into every diagnostics file so a
#: plan reading one written by an older driver can tell, instead of asserting against a
#: shape that has since changed and reading the mismatch as a product defect.
DIAGNOSTICS_SCHEMA = "browser-diagnostics/1"

#: How many console/request/response records are kept in the file. The counts are kept in
#: full alongside them, so an assertion on volume survives the truncation.
DIAGNOSTICS_LIMIT = 500

DEFAULT_VIEWPORT = {"width": 1440, "height": 900}


class Browser:
    """One browser, one context, one page, for the length of one scenario.

    A scenario per process is what deletes `SharedPlaywright`: the driver used to lend one
    Playwright to every browser target because they shared a process, and the lending was
    the only reason the lifetime was hard.
    """

    def __init__(
        self,
        target: Any,
        *,
        qa_dir: Path,
        scenario_id: str,
        clock: Any,
        emit: Any,
    ) -> None:
        self.target = target
        self.qa_dir = qa_dir
        self.scenario_id = scenario_id
        self.clock = clock
        self.emit = emit
        self.recording: dict[str, Any] = dict(target.recording or {"required": True})
        self.viewport: dict[str, Any] = dict(target.viewport or DEFAULT_VIEWPORT)
        self.mode = str(self.recording.get("mode", "window"))
        self.required = bool(self.recording.get("required", True))
        self.video_dir = qa_dir / "videos" / scenario_id
        self.page: Any = None
        self.start_offset_ms = 0
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._console_errors: list[str] = []
        self._console: list[dict[str, Any]] = []
        self._page_errors: list[dict[str, Any]] = []
        self._requests: list[dict[str, Any]] = []
        self._failed_requests: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []

    # -- lifecycle -----------------------------------------------------------------------

    def open(self) -> Any:
        self._playwright = sync_playwright().start()
        name = str(self.target.browser or "chromium")
        browser_type = getattr(self._playwright, name, None)
        if browser_type is None:
            raise ValueError(f"unknown Playwright browser {name!r}")
        # Headed only for window recording, which is ostler's ffmpeg grabbing the X display
        # this process was handed. Every other mode is headless.
        self._browser = browser_type.launch(headless=not (self.required and self.mode == "window"))
        options: dict[str, Any] = {"viewport": self.viewport}
        permissions = self.permissions()
        if permissions:
            options["permissions"] = permissions
        if self.required and self.mode == "viewport":
            self.video_dir.mkdir(parents=True, exist_ok=True)
            options["record_video_dir"] = str(self.video_dir)
        self._context = self._browser.new_context(**options)
        self.start_offset_ms = self.clock()
        self.page = self._context.new_page()
        self._listen(self.page)
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        return self.page

    def close(self, *, failed: bool) -> list[str]:
        """Finalize every artifact and return whatever the recording policy could not meet.

        Returns problems rather than raising them: this runs after the scenario, and an
        exception here would replace the scenario's own verdict — the thing the reader
        actually needs — with a complaint about a video file.
        """
        problems: list[str] = []
        if failed and self.page is not None:
            problems.extend(self._failure_screenshot())
        trace = self.qa_dir / "traces" / f"{self.scenario_id}.zip"
        trace.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._context.tracing.stop(path=str(trace))
        except Exception as exc:  # noqa: BLE001 - a lost trace must not lose the verdict
            problems.append(f"playwright trace could not be written: {exc}")
        # Closing the context is what finalizes a viewport recording, so the video files
        # below do not exist until this line has run.
        self._context.close()
        self._browser.close()
        self._playwright.stop()
        if trace.is_file():
            self.emit({"type": "artifact", "path": str(trace), "kind": "playwright-trace"})
        problems.extend(self._register_videos())
        self._write_diagnostics()
        return problems

    def permissions(self) -> list[str]:
        """The permissions the context is opened with.

        A fresh context grants nothing, and Chromium answers an ungranted permission query
        by *denying* it rather than prompting — there is no UI to prompt into. So
        `navigator.clipboard.writeText()` rejects with `NotAllowedError` on a page a human
        would see it succeed on, an app that catches that renders its failure branch with
        no console error and no failed request, and the run's evidence points at the
        product instead of at the harness. Clipboard access is therefore the default.

        `permissions=` on the target replaces the default outright — including with `[]`,
        for a plan whose whole point is the denied branch. The default is Chromium-only
        because the permission names are: Firefox and WebKit reject them as unknown.
        """
        configured = self.target.permissions
        if configured is not None:
            return [str(entry) for entry in configured]
        if str(self.target.browser or "chromium") != "chromium":
            return []
        return ["clipboard-read", "clipboard-write"]

    # -- what a scenario may assert on ----------------------------------------------------
    #
    # The diagnostics *file* is written by `close`, after the scenario has already returned
    # its verdict, so it can only be read by the post-run audit. A plan is nonetheless held
    # to "an unexpected 5xx or console error cannot pass unnoticed", and that demand needs an
    # expression the scenario itself can assert on — otherwise it arrives as a review finding
    # no author can act on. These four are that expression: the same records the file gets,
    # readable while the page is still open.

    def console_errors(self) -> list[dict[str, Any]]:
        """Console messages at `error` level so far."""
        return [entry for entry in self._console if entry.get("type") == "error"]

    def page_errors(self) -> list[dict[str, Any]]:
        """Uncaught exceptions — a different event from the console, invisible in it."""
        return list(self._page_errors)

    def failed_requests(
        self, *, ignore: Sequence[str] = ("net::ERR_ABORTED",)
    ) -> list[dict[str, Any]]:
        """Requests that never completed, minus the ones an app aborts by design.

        Excluding by *reason* rather than by count is the difference between tolerating a
        navigation the app cancelled and tolerating a refused connection: `len(...) <= 1`
        goes green on the second one too.
        """
        ignored = set(ignore)
        return [entry for entry in self._failed_requests if entry.get("errorText") not in ignored]

    def responses(self, *, status_at_least: int = 0) -> list[dict[str, Any]]:
        """Every response seen, optionally only those at or above a status."""
        return [entry for entry in self._responses if entry.get("status", 0) >= status_at_least]

    # -- diagnostics ---------------------------------------------------------------------

    def _listen(self, page: Any) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("request", self._on_request)
        page.on("requestfailed", self._on_failed_request)
        page.on("response", self._on_response)

    def _on_console(self, message: Any) -> None:
        """Every console message, whatever its level.

        Only `type == "error"` was ever kept, which threw away the half of the console that
        explains an error: the warning that preceded it, the app's own trace of the request
        it was about to make, the React key/hydration warnings that are levelled `warn` and
        are the actual defect.
        """
        if message.type == "error":
            self._console_errors.append(message.text)
        location = message.location or {}
        where = str(location.get("url", ""))
        if where:
            where = f"{where}:{location.get('lineNumber', 0)}:{location.get('columnNumber', 0)}"
        self._console.append(
            {"atMs": self.clock(), "type": message.type, "text": message.text, "location": where}
        )

    def _on_page_error(self, error: Any) -> None:
        """An uncaught exception on the page.

        `pageerror` is a different event from `console`: an exception nothing catches
        reaches it, and reaches the console only as a side effect the driver was not
        guaranteed to see.
        """
        self._page_errors.append(
            {"atMs": self.clock(), "name": type(error).__name__, "message": str(error)}
        )

    def _on_request(self, request: Any) -> None:
        """Every request issued, whether or not anything came back.

        `responses` covers what completed and `failedRequests` what failed; a request still
        in flight when the scenario ends is in neither — which is the exact shape of a hung
        endpoint. Correlate by `url` and `atMs`.
        """
        self._requests.append(
            {
                "atMs": self.clock(),
                "url": request.url,
                "method": request.method,
                "resourceType": request.resource_type,
            }
        )

    def _on_failed_request(self, request: Any) -> None:
        """A request that never completed, with *why* it did not.

        `requestfailed` does not mean the network broke. An app cancelling its own in-flight
        fetch — an effect cleanup aborting on unmount, a navigation superseding a load —
        fires it too, with `net::ERR_ABORTED`. Without `errorText` those are
        indistinguishable from `net::ERR_CONNECTION_REFUSED`, and a plan gating on the
        count goes permanently red on a benign self-cancel.
        """
        self._failed_requests.append(
            {
                "atMs": self.clock(),
                "url": request.url,
                "method": request.method,
                "errorText": request.failure or "",
            }
        )

    def _on_response(self, response: Any) -> None:
        """Every HTTP response the page received, including the ones that completed badly.

        `requestfailed` fires only for a request that never completed, so a completed 500
        used to be invisible — and a plan asserting "no response is 500 or higher" was
        asserting against a key nothing wrote, which `jq` reads as an empty stream and
        passes.
        """
        self._responses.append(
            {
                "atMs": self.clock(),
                "url": response.url,
                "status": response.status,
                "method": response.request.method,
            }
        )

    def _write_diagnostics(self) -> None:
        path = self.qa_dir / "traces" / f"{self.scenario_id}-diagnostics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": DIAGNOSTICS_SCHEMA,
                    "consoleErrors": self._console_errors,
                    "console": self._console[:DIAGNOSTICS_LIMIT],
                    "consoleCount": len(self._console),
                    "pageErrors": self._page_errors,
                    "requests": self._requests[:DIAGNOSTICS_LIMIT],
                    "requestCount": len(self._requests),
                    "failedRequests": self._failed_requests,
                    "responses": self._responses[:DIAGNOSTICS_LIMIT],
                    "responseCount": len(self._responses),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.emit({"type": "artifact", "path": str(path), "kind": "browser-diagnostics"})

    # -- artifacts -----------------------------------------------------------------------

    def _failure_screenshot(self) -> list[str]:
        path = self.qa_dir / "screenshots" / f"{self.scenario_id}-failure.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception as exc:  # noqa: BLE001 - a page that died cannot be photographed
            return [f"failure screenshot could not be taken: {exc}"]
        self.emit({"type": "artifact", "path": str(path), "kind": "failure-screenshot"})
        return []

    def _register_videos(self) -> list[str]:
        if not self.video_dir.is_dir():
            return []
        found = 0
        for video in sorted(self.video_dir.glob("*")):
            if not video.is_file() or not video.stat().st_size:
                continue
            found += 1
            self.emit(
                {
                    "type": "artifact",
                    "path": str(video),
                    "kind": "video",
                    # ostler measures the file with ffprobe and holds it to the target's
                    # declared dimensions; the offsets are the part only this side knows.
                    "metadata": {
                        "mode": "viewport",
                        "actionStartOffsetMs": self.start_offset_ms,
                        "actionEndOffsetMs": self.clock(),
                    },
                }
            )
        if self.required and self.mode == "viewport" and not found:
            return ["required Playwright viewport recording was not finalized"]
        return []
