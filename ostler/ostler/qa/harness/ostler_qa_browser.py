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

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ostler_qa_scan import FRAME_JS, SCAN_JS, merge_rects, summarize
from playwright.sync_api import sync_playwright

#: Stamped into every diagnostics file so a
#: plan reading one written by an older driver can tell, instead of asserting against a
#: shape that has since changed and reading the mismatch as a product defect.
#:
#: `/2` is the first schema that carries what the DevTools panels show rather than a
#: summary of it: request and response headers, request payloads, response bodies, timings,
#: and each console message's structured arguments.
DIAGNOSTICS_SCHEMA = "browser-diagnostics/2"

#: Stamped into every layout file, for the same reason: it is read by the audit, and an
#: audit that cannot tell a shape change from a product change reports the first as the second.
LAYOUT_SCHEMA = "browser-layout/1"

#: How many console/request/response records are kept in the file. Set where no real run
#: reaches it, because the file *is* the network and console record — the previous 500 cut
#: a busy SPA off partway through its own startup, and a reader cannot tell a page that
#: made 500 requests from one that made 12,000. When it does bite it says so, in a
#: `truncated` block naming what was dropped; the counts stay exact either way.
DIAGNOSTICS_LIMIT = 50_000

#: Response bodies are kept whole for these content types and fingerprinted-only for the
#: rest. The line is drawn at "can a person read the diff" rather than at size: a 2 MB
#: bundle is worth keeping and a 4 KB PNG is not, because the PNG proves nothing a
#: sha256 and a byte count do not.
TEXT_BODY_TYPES = (
    "text/",
    "application/json",
    "application/javascript",
    "application/x-javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/x-www-form-urlencoded",
    "application/ndjson",
    "application/graphql",
    "+json",
    "+xml",
)

#: The cap on one recorded body, and on all of them together. Past either the record keeps
#: the size and the digest and says which cap it hit — an assertion on a body that was
#: never captured must fail loudly rather than read a missing key as an empty response.
MAX_BODY_BYTES = 256 * 1024
MAX_BODY_BUDGET_BYTES = 8 * 1024 * 1024

#: The longest a single console argument is rendered to. Console arguments are whole
#: objects — a Redux store logged once is megabytes — and the argument exists to say what
#: the app thought it had, which survives truncation.
MAX_CONSOLE_ARG_CHARS = 4096

#: Header values masked to a length even when no secret declares them. A bearer token in
#: `authorization` is a credential whether or not the plan declared it as one, and QA
#: evidence is read, archived and attached to reviews. The header *name* stays, because
#: "the request carried an Authorization header" is a thing plans assert.
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
    }
)

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
        secrets: Sequence[str] = (),
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
        # One record per request, mutated in place as the response and then the body
        # arrive. `_responses` and `_failed_requests` hold *the same dicts*, not copies:
        # a plan that finds a 500 in `responses()` reads its body off the record it already
        # has, and the two views cannot drift into disagreeing about one request.
        self._requests: list[dict[str, Any]] = []
        self._failed_requests: list[dict[str, Any]] = []
        self._responses: list[dict[str, Any]] = []
        # Keyed by `id(request)` and pinning the request objects in `_held`, rather than
        # keyed by the objects themselves: identity is the only correlation Playwright
        # offers — two requests to one URL are two records — and keying on the object
        # assumes the driver never gives its Request an `__eq__`, which is not ours to
        # assume. Holding the reference is what makes the id safe to reuse as a key.
        self._by_request: dict[int, dict[str, Any]] = {}
        self._held: list[Any] = []
        self._body_budget = MAX_BODY_BUDGET_BYTES
        #: Values redacted out of every header, payload and body before it is recorded —
        #: the run's declared secrets, resolved by the runner, which is the only side that
        #: can resolve them.
        self._secrets = [value for value in secrets if value]

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
        problems.extend(self._unclean())
        return problems

    def _unclean(self) -> list[str]:
        """The two browser conditions no scenario is allowed to pass over.

        A plan's own clean-gate is hand-written, and the corpus has one that reads console
        errors, failed requests and 5xx responses and forgets `page_errors()` — so an
        uncaught exception in the app under test rode out under a green verdict. A gate a
        plan writes is a gate a plan can write four fifths of, and reviewing the fifth was
        a person's job once per plan, forever.

        Only these two are automatic. An uncaught page exception and a 5xx are never a
        thing a scenario *meant* to provoke — a scenario proving an error branch provokes a
        4xx. Console errors and cancelled requests stay assertable rather than fatal,
        because an app legitimately logs at error level and legitimately abandons an
        in-flight request on navigation.
        """
        problems: list[str] = []
        if self._page_errors:
            first = self._page_errors[0].get("message") or self._page_errors[0]
            problems.append(
                f"{len(self._page_errors)} uncaught page error(s) in the browser, first: {first}"
            )
        server_errors = [entry for entry in self._responses if int(entry.get("status") or 0) >= 500]
        if server_errors:
            first = server_errors[0]
            problems.append(
                f"{len(server_errors)} response(s) of status 500 or higher, first: "
                f"{first.get('method')} {first.get('url')} -> {first.get('status')}"
            )
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
    # no author can act on. These are that expression: the same records the file gets,
    # readable while the page is still open — headers, payloads, bodies and console
    # arguments included, so an assertion about what the app said or received is written
    # against the record rather than against a screenshot of its consequences.

    def console_errors(self) -> list[dict[str, Any]]:
        """Console messages at `error` level so far."""
        return [entry for entry in self._console if entry.get("type") == "error"]

    def console(self, *, level: str | None = None, contains: str | None = None) -> list[dict[str, Any]]:
        """Every console message so far, at every level, with its arguments.

        The whole console, because the message that explains a failure is routinely not an
        error: a `warn` about a duplicate key, an `info` the app logs before the request it
        is about to get wrong. `level` filters by `type` as Playwright spells it
        (`log`, `debug`, `info`, `warning`, `error`); `contains` filters on the rendered
        text.
        """
        entries = self._console
        if level is not None:
            entries = [entry for entry in entries if entry.get("type") == level]
        if contains is not None:
            entries = [entry for entry in entries if contains in str(entry.get("text", ""))]
        return list(entries)

    def requests(self, *, url_contains: str | None = None) -> list[dict[str, Any]]:
        """Every request issued, with its headers and payload.

        Includes requests that are still in flight and requests that failed — a record with
        no `status` is one nothing came back for, which is what a hung endpoint looks like
        from here.
        """
        if url_contains is None:
            return list(self._requests)
        return [entry for entry in self._requests if url_contains in str(entry.get("url", ""))]

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

    def responses(
        self, *, status_at_least: int = 0, url_contains: str | None = None
    ) -> list[dict[str, Any]]:
        """Every response seen, with its headers and — for a text body — its content.

        A record carries `responseBody` when the body was captured, and `bodyOmitted`
        saying why when it was not: a redirect has none, a binary body is fingerprinted
        rather than kept, and past the scenario's body budget the record keeps the size and
        the digest. Read `bodyOmitted` before asserting on absence — a body that was never
        captured is not an empty one.
        """
        found = [entry for entry in self._responses if entry.get("status", 0) >= status_at_least]
        if url_contains is not None:
            found = [entry for entry in found if url_contains in str(entry.get("url", ""))]
        return found

    def layout(self) -> dict[str, Any]:
        """Where the page put its content, as numbers rather than pixels.

        The scan is `ostler vet`'s, run against the page this scenario is driving. It exists
        because a screenshot is evidence only a human can read: every assertion a browser plan
        makes addresses the accessibility tree, and an element is in that tree whether it is
        laid out across the page or crushed into a 200px column against the right margin. A
        scenario that proves the right link is on the page therefore passes over a page no
        user could use, and nothing downstream could see the difference.
        """
        frame, regions = self._scan()
        return summarize(frame, regions)

    def _scan(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return self.page.evaluate(FRAME_JS), merge_rects(self.page.evaluate(SCAN_JS))

    def measure(self, screenshot: Path) -> dict[str, Any]:
        """Write the two machine-readable records of what a screenshot photographed.

        `<name>.layout.json` is the digest a reader (or the independent audit) holds at once:
        the window, the laid-out document, and each structural region as a share of the
        window. `<name>.regions.json` is the same scan undigested, in the shape `ostler vet
        --regions` replays — every merged region, structural or not. One scan, two readers:
        the audit needs a page it can judge, and `vet` needs the whole census to register a
        documented component against.
        """
        frame, regions = self._scan()
        measured = {"schema": LAYOUT_SCHEMA, **summarize(frame, regions)}
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        for path, payload, kind in (
            (screenshot.with_suffix(".layout.json"), measured, "layout"),
            (screenshot.with_suffix(".regions.json"), regions, "regions"),
        ):
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            self.emit({"type": "artifact", "path": str(path), "kind": kind})
        return measured

    # -- diagnostics ---------------------------------------------------------------------

    def _listen(self, page: Any) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("request", self._on_request)
        page.on("requestfailed", self._on_failed_request)
        page.on("response", self._on_response)
        page.on("requestfinished", self._on_request_finished)

    def _on_console(self, message: Any) -> None:
        """Every console message, whatever its level.

        Only `type == "error"` was ever kept, which threw away the half of the console that
        explains an error: the warning that preceded it, the app's own trace of the request
        it was about to make, the React key/hydration warnings that are levelled `warn` and
        are the actual defect.
        """
        if message.type == "error":
            self._console_errors.append(self._safe(message.text))
        location = message.location or {}
        where = str(location.get("url", ""))
        if where:
            where = f"{where}:{location.get('lineNumber', 0)}:{location.get('columnNumber', 0)}"
        self._console.append(
            {
                "atMs": self.clock(),
                "type": message.type,
                "text": self._safe(message.text),
                "location": where,
                "args": self._console_args(message),
            }
        )

    def _console_args(self, message: Any) -> list[Any]:
        """The message's arguments as values, not as the console's rendering of them.

        `message.text` is what DevTools *prints*: `console.log("state", store)` becomes
        `state {items: Array(3), …}`, and the object the app was complaining about is gone
        — an ellipsis where the assertion needed the third item. The handles are still live
        at this moment, so this is the only place the values can be taken.
        """
        args: list[Any] = []
        for handle in getattr(message, "args", None) or []:
            try:
                args.append(self._shrink(handle.json_value()))
            except Exception as exc:  # noqa: BLE001 - a DOM node or a cycle is not JSON
                args.append({"unserializable": type(exc).__name__})
        return args

    def _shrink(self, value: Any) -> Any:
        """A console argument, capped, with the cap declared rather than implied."""
        if isinstance(value, str):
            safe = self._safe(value)
            if len(safe) > MAX_CONSOLE_ARG_CHARS:
                return {"truncated": True, "chars": len(safe), "head": safe[:MAX_CONSOLE_ARG_CHARS]}
            return safe
        if isinstance(value, dict):
            return {str(key): self._shrink(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._shrink(item) for item in value]
        return value

    def _on_page_error(self, error: Any) -> None:
        """An uncaught exception on the page.

        `pageerror` is a different event from `console`: an exception nothing catches
        reaches it, and reaches the console only as a side effect the driver was not
        guaranteed to see.
        """
        self._page_errors.append(
            {
                "atMs": self.clock(),
                "name": str(getattr(error, "name", None) or type(error).__name__),
                "message": self._safe(str(getattr(error, "message", None) or error)),
                # The frame that threw. Without it a message like "undefined is not a
                # function" names no file, and triage starts by reproducing the run.
                "stack": self._safe(str(getattr(error, "stack", "") or "")),
            }
        )

    def _on_request(self, request: Any) -> None:
        """Every request issued, whether or not anything came back.

        `responses` covers what completed and `failedRequests` what failed; a request still
        in flight when the scenario ends is in neither — which is the exact shape of a hung
        endpoint. Correlate by `url` and `atMs`.
        """
        record = {
            "atMs": self.clock(),
            "url": request.url,
            "method": request.method,
            "resourceType": request.resource_type,
            "requestHeaders": self._headers(getattr(request, "headers", None)),
            "requestBody": self._payload(getattr(request, "post_data", None)),
        }
        self._remember(request, record)

    def _on_failed_request(self, request: Any) -> None:
        """A request that never completed, with *why* it did not.

        `requestfailed` does not mean the network broke. An app cancelling its own in-flight
        fetch — an effect cleanup aborting on unmount, a navigation superseding a load —
        fires it too, with `net::ERR_ABORTED`. Without `errorText` those are
        indistinguishable from `net::ERR_CONNECTION_REFUSED`, and a plan gating on the
        count goes permanently red on a benign self-cancel.
        """
        record = self._record(request)
        record["errorText"] = request.failure or ""
        # A request that never completed has no body to have kept, and says so rather than
        # leaving the reader to infer an empty response from an absent key.
        record.setdefault("bodyOmitted", "request did not complete")
        self._failed_requests.append(record)

    def _on_response(self, response: Any) -> None:
        """Every HTTP response the page received, including the ones that completed badly.

        `requestfailed` fires only for a request that never completed, so a completed 500
        used to be invisible — and a plan asserting "no response is 500 or higher" was
        asserting against a key nothing wrote — which a stream-oriented lookup reads as an
        empty stream and passes.
        """
        record = self._record(response.request)
        record.update(
            {
                "atMs": self.clock(),
                "status": response.status,
                "statusText": str(getattr(response, "status_text", "") or ""),
                "responseHeaders": self._headers(getattr(response, "headers", None)),
            }
        )
        self._responses.append(record)

    def _on_request_finished(self, request: Any) -> None:
        """The body and the timings, taken at the one moment they are cheap and safe.

        Not in `_on_response`: `Response.body()` blocks until the response has finished
        loading, and a scenario that opens an `EventSource` or a long poll would block the
        event dispatcher there for as long as the stream stays open — a harness hang
        reported as a product timeout. `requestfinished` fires only once loading is done, so
        the body is already buffered; a stream that never finishes simply never gets one,
        which is the truthful record of a request still in flight.
        """
        record = self._record(request)
        timing = getattr(request, "timing", None)
        if isinstance(timing, dict) and timing.get("responseEnd", -1) >= 0:
            record["durationMs"] = round(float(timing["responseEnd"]), 3)
        response = None
        try:
            response = request.response()
        except Exception as exc:  # noqa: BLE001 - a torn-down page loses its responses
            record["bodyOmitted"] = f"unavailable: {exc}"
        if response is None:
            record.setdefault("bodyOmitted", "no response object")
            return
        # `all_headers()` is the raw set, including the `set-cookie` Chromium keeps out of
        # `headers`; it costs a protocol round-trip, which is affordable here and was not in
        # the `response` handler.
        try:
            record["responseHeaders"] = self._headers(response.all_headers())
        except Exception:  # noqa: BLE001 - keep whatever the response event already gave
            pass
        self._capture_body(record, response)

    def _capture_body(self, record: dict[str, Any], response: Any) -> None:
        """Record the response body, or record precisely why it is not here.

        Every path writes something. A missing `responseBody` key with no `bodyOmitted`
        beside it is indistinguishable from an empty body to the plan reading it, and an
        assertion that "the error payload never mentions the raw SQL" passes vacuously
        against a body nobody captured.
        """
        try:
            raw = response.body()
        except Exception as exc:  # noqa: BLE001 - redirects and aborted loads have no body
            record["bodyOmitted"] = self._why(exc)
            return
        record["responseBodyBytes"] = len(raw)
        record["responseBodySha256"] = hashlib.sha256(raw).hexdigest()
        content_type = str(record.get("responseHeaders", {}).get("content-type", ""))
        if not self._is_text(content_type):
            record["bodyOmitted"] = "binary"
            return
        if self._body_budget <= 0:
            record["bodyOmitted"] = "scenario body budget exhausted"
            return
        keep = min(len(raw), MAX_BODY_BYTES, self._body_budget)
        self._body_budget -= keep
        if keep < len(raw):
            record["responseBodyTruncated"] = True
        record["responseBody"] = self._safe(raw[:keep].decode("utf-8", errors="replace"))

    # -- recording helpers ----------------------------------------------------------------

    def _record(self, request: Any) -> dict[str, Any]:
        """The record for this request, creating it if the `request` event was missed.

        A redirect leg, a service-worker fetch or a request already in flight when the
        listeners attached can reach a later event first. Creating on demand keeps that
        request in the network record instead of dropping it.
        """
        record = self._by_request.get(id(request))
        if record is None:
            record = {
                "atMs": self.clock(),
                "url": request.url,
                "method": request.method,
                "resourceType": getattr(request, "resource_type", ""),
                "requestHeaders": self._headers(getattr(request, "headers", None)),
                "requestBody": self._payload(getattr(request, "post_data", None)),
            }
            self._remember(request, record)
        return record

    def _remember(self, request: Any, record: dict[str, Any]) -> None:
        self._requests.append(record)
        self._by_request[id(request)] = record
        self._held.append(request)

    def _headers(self, headers: Any) -> dict[str, str]:
        """Headers, lowercased, with credential values masked to their length."""
        recorded: dict[str, str] = {}
        for name, value in dict(headers or {}).items():
            key = str(name).lower()
            if key in SENSITIVE_HEADERS:
                recorded[key] = f"[REDACTED {len(str(value))} chars]"
            else:
                recorded[key] = self._safe(str(value))
        return recorded

    def _payload(self, body: Any) -> str | None:
        if body is None:
            return None
        text = self._safe(str(body))
        if len(text) > MAX_BODY_BYTES:
            return text[:MAX_BODY_BYTES]
        return text

    def _safe(self, text: str) -> str:
        for value in self._secrets:
            text = text.replace(value, "[REDACTED]")
        return text

    @staticmethod
    def _is_text(content_type: str) -> bool:
        lowered = content_type.lower()
        return any(marker in lowered for marker in TEXT_BODY_TYPES)

    @staticmethod
    def _why(exc: Exception) -> str:
        """The driver's own sentence about a missing body, kept short.

        Playwright says "Response body is unavailable for redirect responses"; a reader who
        gets `bodyOmitted: "redirect"` instead has to go and find out what the harness meant
        by it.
        """
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        return first[:200]

    def _write_diagnostics(self) -> None:
        """The console and the network, as the run's own copy of what DevTools showed.

        Written whole. The post-run reader — a person, the story assessment, the
        independent audit — has no browser to open and no session to re-drive, so anything
        this file summarizes away is gone: the payload the app posted, the error body the UI
        rendered as "something went wrong", the header that was missing. What is capped is
        capped out loud, in `truncated`.
        """
        for record in self._requests:
            if "responseBody" not in record:
                # Written at close because in-flight is a legitimate state *during* the
                # scenario and a permanent one after it: a request with no body and no
                # reason would otherwise read as an empty response to everything downstream.
                record.setdefault("bodyOmitted", "still in flight when the scenario ended")
        path = self.qa_dir / "traces" / f"{self.scenario_id}-diagnostics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
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
            "bodyBudgetBytes": MAX_BODY_BUDGET_BYTES,
            "bodyBudgetRemainingBytes": max(self._body_budget, 0),
        }
        truncated = {
            name: {"kept": DIAGNOSTICS_LIMIT, "of": total}
            for name, total in (
                ("console", len(self._console)),
                ("requests", len(self._requests)),
                ("responses", len(self._responses)),
            )
            if total > DIAGNOSTICS_LIMIT
        }
        if truncated:
            payload["truncated"] = truncated
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
        try:
            self.measure(path)
        except Exception as exc:  # noqa: BLE001 - the image is the evidence; this explains it
            return [f"failure layout could not be measured: {exc}"]
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
