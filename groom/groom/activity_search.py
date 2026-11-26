from __future__ import annotations

from typing import Any

from groom import flows, store
from groom.activity import LiveRows, TurnNotFound, TurnUnreadable, _archived, _attempts, _read_turn


class SearchFailed(RuntimeError):
    pass


SEARCH_QUERY_CHARS = 200
SEARCH_LINE_CHARS = 160


def _hit_line(text: str, needle: str) -> str:
    lowered = text.lower()
    at = lowered.find(needle)
    if at < 0:
        return ""
    start = max(0, at - SEARCH_LINE_CHARS // 4)
    return " ".join(text[start : start + SEARCH_LINE_CHARS].split())


def _entry_lines(entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for one in entries:
        if one["kind"] == "message":
            lines.extend(one["text"].splitlines())
        else:
            lines.append(one.get("summary") or "")
            lines.extend((one.get("result") or "").splitlines())
    return lines


def search(run_id: str, query: str, live: LiveRows | None = None, pending: bool = False) -> dict[str, Any]:
    """The turns of this run, and only this run, whose transcript says `query`, each with the first matching line. A turn that cannot be read fails the whole search."""
    needle = " ".join(query.split())[:SEARCH_QUERY_CHARS].lower()
    if not needle:
        return {"run_id": run_id, "query": "", "matches": []}
    matches: list[dict[str, str]] = []
    spans = store.run_turn_spans(run_id)
    archived = _archived(run_id)
    attempted = _attempts(spans, archived)
    placed = flows.span_passes(spans)
    slugs = list(attempted) + [slug for slug, held in (live or {}).items() if slug not in attempted and held]
    for slug in slugs:
        try:
            read = _read_turn(run_id, slug, live, pending, spans, archived, attempted, placed)
        except TurnNotFound:
            continue
        except TurnUnreadable as exc:
            raise SearchFailed(slug) from exc
        for line in _entry_lines(read["entries"]):
            found = _hit_line(line, needle)
            if found:
                matches.append({"key": slug, "line": found})
                break
    return {"run_id": run_id, "query": needle, "matches": matches}
