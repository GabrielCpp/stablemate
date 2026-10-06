"""Playwright lifecycle for a browser scenario, inside the scenario's own process."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ostler_qa_browser_state import CLIPBOARD_JS
from ostler_qa_scan import FRAME_JS, SCAN_JS, merge_rects, summarize
from playwright.sync_api import sync_playwright

DIAGNOSTICS_SCHEMA = "browser-diagnostics/2"

LAYOUT_SCHEMA = "browser-layout/1"

DIAGNOSTICS_LIMIT = 50_000

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

MAX_BODY_BYTES = 256 * 1024
MAX_BODY_BUDGET_BYTES = 8 * 1024 * 1024

MAX_CONSOLE_ARG_CHARS = 4096

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


BROWSER_ISSUED_URLS: tuple[str, ...] = ("/favicon.ico",)

ARRANGE_TIMEOUT_MS = 30_000

QUIET_MS = 500
QUIET_STEP_MS = 100
QUIET_TIMEOUT_MS = 5000

ARRANGE_METHODS = {"fill": "fill", "click": "click", "press": "press", "select": "select_option"}


def _locate(page: Any, locator: Mapping[str, str]) -> Any:
    """The element a fixture's locator names: by role and name, label, text or a book-declared selector."""
    if "role" in locator:
        found = page.get_by_role(locator["role"], name=locator["name"])
        if found.count() > 1:
            whole = page.get_by_role(locator["role"], name=locator["name"], exact=True)
            if whole.count() == 1:
                return whole
        return found
    if "label" in locator:
        return page.get_by_label(locator["label"])
    if "text" in locator:
        return page.get_by_text(locator["text"])
    return page.locator(locator["css"])


class RecordedResponse:
    """One recorded exchange, wearing the shape the verifiers were written against."""

    __slots__ = ("record",)

    def __init__(self, record: dict[str, Any]) -> None:
        self.record = record

    @property
    def status(self) -> int:
        return int(self.record.get("status") or 0)

    @property
    def url(self) -> str:
        return str(self.record.get("url", ""))

    @property
    def text(self) -> str:
        """The captured body, or "" when there was none to capture."""
        return str(self.record.get("responseBody") or "")

    def json(self) -> Any:
        """The body, parsed."""
        omitted = self.record.get("bodyOmitted")
        if omitted:
            raise LookupError(
                f"the body of {self.url} was not captured ({omitted}) — a body that was "
                f"never recorded is not an empty one"
            )
        return json.loads(self.text) if self.text else None



def path_pattern(path: str) -> re.Pattern[str]:
    """A request path as a pattern, with each `{name}` standing for one whole segment."""
    parts = re.split(r"(\{[^{}/]+\})", path)
    return re.compile("".join("[^/]+" if part.startswith("{") else re.escape(part) for part in parts if part))


class ResponseWindow:
    """The exchanges and console messages a page made after one point in a scenario — `Browser.window()`'s handle."""

    __slots__ = ("_browser", "_console", "_requests", "_since")

    def __init__(self, browser: Browser, since: int, requests: int = 0, console: int = 0) -> None:
        self._browser = browser
        self._since = since
        self._requests = requests
        self._console = console

    def response_for(self, path: str, *, method: str | None = None) -> RecordedResponse:
        """The one response on *path* (and *method*, if given) inside this window."""
        return self._browser.response_for(path, method=method, since=self._since)

    def requests_to(self, path: str, *, method: str | None = None) -> list[dict[str, Any]]:
        """Every request on *path* (and *method*, if given) inside this window, once the page has gone quiet."""
        self._browser.quiet()
        pattern = path_pattern(path)
        return [
            entry for entry in self._browser.requests()[self._requests:]
            if pattern.fullmatch(urlsplit(str(entry.get("url", ""))).path)
            and (method is None or str(entry.get("method", "")).upper() == method.upper())
        ]

    def console(self) -> list[dict[str, Any]]:
        """Every console message inside this window, once the page has gone quiet."""
        self._browser.quiet()
        return self._browser.console()[self._console:]


class Browser:
    """One browser, one context, one page, for the length of one scenario."""

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
        self.mode = str(self.recording.get("mode", "viewport"))
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
        self._by_request: dict[int, dict[str, Any]] = {}
        self._open: set[int] = set()
        self._held: list[Any] = []
        self._body_budget = MAX_BODY_BUDGET_BYTES
        self._secrets = [value for value in secrets if value]
        self._side: Any = None


    def open(self) -> Any:
        self._playwright = sync_playwright().start()
        name = str(self.target.browser or "chromium")
        browser_type = getattr(self._playwright, name, None)
        if browser_type is None:
            raise ValueError(f"unknown Playwright browser {name!r}")
        self._browser = browser_type.launch(headless=not (self.required and self.mode == "window"))
        options: dict[str, Any] = {"viewport": self.viewport}
        permissions = self.permissions()
        if permissions:
            options["permissions"] = permissions
        if self.required and self.mode == "viewport":
            self.video_dir.mkdir(parents=True, exist_ok=True)
            options["record_video_dir"] = str(self.video_dir)
            options["record_video_size"] = dict(self.viewport)
        self._context = self._browser.new_context(**options)
        self._context.add_init_script(CLIPBOARD_JS)
        self.start_offset_ms = self.clock()
        self.page = self._context.new_page()
        if name == "chromium":
            self._context.new_cdp_session(self.page).send(
                "Network.setCacheDisabled", {"cacheDisabled": True})
        self._listen(self.page)
        self._context.tracing.start(screenshots=True, snapshots=True, sources=True)
        return self.page

    def close(self, *, failed: bool) -> list[str]:
        """Finalize every artifact and return whatever the recording policy could not meet."""
        problems: list[str] = []
        if failed and self.page is not None:
            problems.extend(self._failure_screenshot())
        trace = self.qa_dir / "traces" / f"{self.scenario_id}.zip"
        trace.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._context.tracing.stop(path=str(trace))
        except Exception as exc:  # noqa: BLE001 - a lost trace must not lose the verdict
            problems.append(f"playwright trace could not be written: {exc}")
        self._context.close()
        self._browser.close()
        self._playwright.stop()
        if trace.is_file():
            self.emit({"type": "artifact", "path": str(trace), "kind": "playwright-trace"})
        problems.extend(self._register_videos())
        self._write_diagnostics()
        return problems

    def unclean(self) -> list[str]:
        """The two browser conditions no scenario is allowed to pass over."""
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
        """The permissions the context is opened with."""
        configured = self.target.permissions
        if configured is not None:
            return [str(entry) for entry in configured]
        if str(self.target.browser or "chromium") != "chromium":
            return []
        return ["clipboard-read", "clipboard-write"]

    def arrange(self, actions: Sequence[Mapping[str, Any]], *, timeout_ms: float = ARRANGE_TIMEOUT_MS) -> None:
        """Perform a fixture's browser actions on a page of this context the scenario never sees.

        Each action waits for the page the last one opened to finish loading, since a provider's
        page shows its controls before its scripts listen to them and drops a click made earlier.
        """
        if self._side is None:
            self._side = self._context.new_page()
        try:
            for action in actions:
                if "open" in action:
                    self._side.goto(str(action["open"]), timeout=timeout_ms)
                    continue
                self._side.wait_for_load_state("load", timeout=timeout_ms)
                found = _locate(self._side, action["locator"])
                method = ARRANGE_METHODS[str(action["act"])]
                values = [str(action["value"])] if "value" in action else []
                getattr(found, method)(*values, timeout=timeout_ms)
        except Exception:
            self._close_side()
            raise

    def session(self, origin: str, *, timeout_ms: float = ARRANGE_TIMEOUT_MS) -> dict[str, Any]:
        """The session the arranged page left, once it is back on *origin* and its requests have settled.

        A page that never comes back says which page it stayed on, since that page is the step that stalled.
        """
        host = urlsplit(origin).netloc
        try:
            try:
                self._side.wait_for_url(lambda url: urlsplit(url).netloc == host, timeout=timeout_ms)
            except Exception as exc:
                raise TimeoutError(f"the arranged page stayed on {self._side.url}") from exc
            self._side.wait_for_load_state("networkidle", timeout=timeout_ms)
            return dict(self._context.storage_state(indexed_db=True))
        finally:
            self._close_side()

    def restore(self, state: Mapping[str, Any]) -> None:
        """Put an earlier scenario's arranged session into this context, before the page opens the app."""
        side = self._context.new_page()
        try:
            side.goto("about:blank")
            self._context.set_storage_state(dict(state))
        finally:
            side.close()

    def _close_side(self) -> None:
        if self._side is not None:
            self._side.close()
            self._side = None


    def console_errors(self, *, ignore_urls: Sequence[str] = BROWSER_ISSUED_URLS) -> list[dict[str, Any]]:
        """Console messages at `error` level so far, minus the ones no page asked for."""
        ignored = tuple(ignore_urls)
        return [
            entry
            for entry in self._console
            if entry.get("type") == "error"
            and not any(url in str(entry.get("location", "")) for url in ignored)
        ]

    def console(self, *, level: str | None = None, contains: str | None = None) -> list[dict[str, Any]]:
        """Every console message so far, at every level, with its arguments."""
        entries = self._console
        if level is not None:
            entries = [entry for entry in entries if entry.get("type") == level]
        if contains is not None:
            entries = [entry for entry in entries if contains in str(entry.get("text", ""))]
        return list(entries)

    def requests(self, *, url_contains: str | None = None) -> list[dict[str, Any]]:
        """Every request issued, with its headers and payload."""
        if url_contains is None:
            return list(self._requests)
        return [entry for entry in self._requests if url_contains in str(entry.get("url", ""))]

    def page_errors(self) -> list[dict[str, Any]]:
        """Uncaught exceptions — a different event from the console, invisible in it."""
        return list(self._page_errors)

    def failed_requests(
        self, *, ignore: Sequence[str] = ("net::ERR_ABORTED",)
    ) -> list[dict[str, Any]]:
        """Requests that never completed, minus the ones an app aborts by design."""
        ignored = set(ignore)
        return [entry for entry in self._failed_requests if entry.get("errorText") not in ignored]

    def responses(
        self, *, status_at_least: int = 0, url_contains: str | None = None
    ) -> list[dict[str, Any]]:
        """Every response seen, with its headers and — for a text body — its content."""
        found = [entry for entry in self._responses if entry.get("status", 0) >= status_at_least]
        if url_contains is not None:
            found = [entry for entry in found if url_contains in str(entry.get("url", ""))]
        return found

    def window(self) -> ResponseWindow:
        """An observation window opening here — what a claim about the next action may read."""
        return ResponseWindow(self, len(self._responses), len(self._requests), len(self._console))

    def quiet(self, *, quiet_ms: int = QUIET_MS, timeout_ms: int = QUIET_TIMEOUT_MS) -> None:
        """Wait until no request is in flight and none has started for *quiet_ms*, or *timeout_ms* has passed."""
        if self.page is None:
            return
        waited, still, seen = 0, 0, len(self._requests)
        while waited < timeout_ms and still < quiet_ms:
            self.page.wait_for_timeout(QUIET_STEP_MS)
            waited += QUIET_STEP_MS
            if self._open or len(self._requests) != seen:
                still, seen = 0, len(self._requests)
            else:
                still += QUIET_STEP_MS

    def response_for(
        self, path: str, *, method: str | None = None, since: int = 0
    ) -> RecordedResponse:
        """The one response on *path* (and *method*, if given) since *since*."""
        window = self._responses[since:]
        found = [
            entry for entry in window
            if urlsplit(str(entry.get("url", ""))).path == path
            and (method is None or str(entry.get("method", "")).upper() == method.upper())
        ]
        if not found:
            if method is None:
                seen = sorted({urlsplit(str(e.get("url", ""))).path for e in window})
                raise LookupError(
                    f"no response on {path!r} after the action this claim is about; the page "
                    f"requested {seen!r}"
                )
            seen_pairs = sorted(
                {(str(e.get("method", "")), urlsplit(str(e.get("url", ""))).path) for e in window}
            )
            raise LookupError(
                f"no response on {method} {path!r} after the action this claim is about; "
                f"the page requested {seen_pairs!r}"
            )
        if len(found) > 1:
            what = f"{path!r}" if method is None else f"{method} {path!r}"
            raise LookupError(
                f"{len(found)} responses on {what} after the action this claim is about — "
                f"which one the check means is undetermined; statuses "
                f"{[e.get('status') for e in found]!r}"
            )
        return RecordedResponse(found[0])

    def layout(self) -> dict[str, Any]:
        """Where the page put its content, as numbers rather than pixels."""
        frame, regions = self._scan()
        return summarize(frame, regions)

    def _scan(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        return self.page.evaluate(FRAME_JS), merge_rects(self.page.evaluate(SCAN_JS))

    def measure(self, screenshot: Path) -> dict[str, Any]:
        """Write the two machine-readable records of what a screenshot photographed."""
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


    def _listen(self, page: Any) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("request", self._on_request)
        page.on("requestfailed", self._on_failed_request)
        page.on("response", self._on_response)
        page.on("requestfinished", self._on_request_finished)

    def _on_console(self, message: Any) -> None:
        """Every console message, whatever its level."""
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
        """The message's arguments as values, not as the console's rendering of them."""
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
        """An uncaught exception on the page."""
        self._page_errors.append(
            {
                "atMs": self.clock(),
                "name": str(getattr(error, "name", None) or type(error).__name__),
                "message": self._safe(str(getattr(error, "message", None) or error)),
                "stack": self._safe(str(getattr(error, "stack", "") or "")),
            }
        )

    def _on_request(self, request: Any) -> None:
        """Every request issued, whether or not anything came back."""
        record = {
            "atMs": self.clock(),
            "url": request.url,
            "method": request.method,
            "resourceType": request.resource_type,
            "requestHeaders": self._headers(getattr(request, "headers", None)),
            "requestBody": self._payload(getattr(request, "post_data", None)),
        }
        self._remember(request, record)
        self._open.add(id(request))

    def _on_failed_request(self, request: Any) -> None:
        """A request that never completed, with *why* it did not."""
        self._open.discard(id(request))
        record = self._record(request)
        record["errorText"] = request.failure or ""
        record.setdefault("bodyOmitted", "request did not complete")
        self._failed_requests.append(record)

    def _on_response(self, response: Any) -> None:
        """Every HTTP response the page received, including the ones that completed badly."""
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
        """The body and the timings, taken at the one moment they are cheap and safe."""
        self._open.discard(id(request))
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
        try:
            record["responseHeaders"] = self._headers(response.all_headers())
        except Exception:  # noqa: BLE001 - keep whatever the response event already gave
            pass
        self._capture_body(record, response)

    def _capture_body(self, record: dict[str, Any], response: Any) -> None:
        """Record the response body, or record precisely why it is not here."""
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


    def _record(self, request: Any) -> dict[str, Any]:
        """The record for this request, creating it if the `request` event was missed."""
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
        """The driver's own sentence about a missing body, kept short."""
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        return first[:200]

    def _write_diagnostics(self) -> None:
        """The console and the network, as the run's own copy of what DevTools showed."""
        for record in self._requests:
            if "responseBody" not in record:
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
