"""Wait on the page's own render and network events instead of the clock."""
from __future__ import annotations

from collections.abc import Callable

FRAMES = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())))"
STEP_MS = 100


def flush(page) -> None:
    """Return once the page has rendered two animation frames, so microtask and zero-delay work has run."""
    page.evaluate(FRAMES)


def settle(page) -> None:
    """Return once the page has no request in flight and has rendered the result."""
    page.wait_for_load_state("networkidle")
    flush(page)


def advance_until(page, done: Callable[[], bool], what: str, limit_ms: int) -> int:
    """Run the page's fake clock in short steps until `done`, failing past `limit_ms` of fake time. Needs `page.clock.install()`."""
    elapsed = 0
    flush(page)
    while not done():
        if elapsed >= limit_ms:
            raise AssertionError(f"{what} did not happen within {limit_ms} ms of page time")
        page.clock.run_for(STEP_MS)
        flush(page)
        elapsed += STEP_MS
    return elapsed


COUNT_PUSHES = """(() => {
  const Native = window.WebSocket;
  window.__pushes = 0;
  window.WebSocket = class extends Native {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", () => { window.__pushes += 1; });
    }
  };
})();"""


def pushes(page) -> int:
    """How many server pushes the page has received. The page must have been opened with `COUNT_PUSHES` as an init script."""
    return page.evaluate("() => window.__pushes")


def wait_for_push(page, since: int) -> None:
    """Return once the page has received a push after the count `since`, then once it has rendered."""
    page.wait_for_function("(since) => window.__pushes > since", arg=since)
    flush(page)


def count_pushes(page) -> None:
    """Reload an open dashboard page so it counts the pushes it receives."""
    page.add_init_script(COUNT_PUSHES)
    page.reload(wait_until="load")
    page.wait_for_selector("#runs-list .row", timeout=30000)
