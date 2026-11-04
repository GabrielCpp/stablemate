"""Why a run that stopped did not finish: the sentence, the failing moment and the command that continues it, read from what the run recorded."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from groom import activity, history

HEADS = {
    "failed": "{error}",
    "interrupted": "interrupted by {error}",
    "crashed": "crashed",
    "gave-up": "gave up",
}
FACTS = {"interrupted": "interrupted", "crashed": "crashed"}
MAX_REASON = 240
CRASHED = "The run stopped on an unhandled error before it could finish."


def _moment(ending: str, node: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    entries = activity._flat(items)
    if ending == "gave-up":
        return next((entry for entry in reversed(entries) if entry["kind"] in ("step", "failed") and entry.get("node") == node), None)
    return next((entry for entry in reversed(entries) if entry["kind"] == "failed"), None)


def _sentence(text: str, cut: bool = False) -> str:
    text = " ".join(text.split()).rstrip(".")
    if len(text) > MAX_REASON or cut:
        text = text[:MAX_REASON]
        text = text[: text.rfind(" ")] if " " in text and (cut or len(text) == MAX_REASON) else text
        text = text.rstrip(" ,;:-") + "…"
        return text[:1].upper() + text[1:]
    return text[:1].upper() + text[1:] + "." if text else ""


def _items(done: int | None, total: int | None) -> str:
    if not total:
        return ""
    if not done:
        return "No work item finished."
    return f"{done} of {total} work items finished." if total > 1 else "The work item finished."


def banner(run_id: str) -> dict[str, Any] | None:
    """The ending banner of a run that stopped, or None for a run that succeeded, still runs or has no recorded ending."""
    row = history.stored(run_id)
    if row is None or row["state"] != history.READY or row["ending"] not in history.STOPPED:
        return None
    ending, node = row["ending"], row["failing_node"]
    moment = _moment(ending, node, activity.timeline(run_id)["items"])
    reason = _sentence(moment.get("reason") or moment["result"], cut="reason" not in moment and len(moment["result"]) >= activity.RESULT_CHARS) if moment and ending in ("failed", "interrupted") and moment["kind"] == "failed" else ""
    if ending == "gave-up":
        work = (moment or {}).get("work") or ""
        reason = f"The run skipped {work or 'the work item'} after exhausting its retries."
    elif ending == "failed":
        reason = reason or "The run stopped on an error."
    elif ending == "interrupted":
        reason = (f"{reason} The run paused." if reason.endswith("…") else f"{reason.rstrip('.')}, and the run paused.") if reason else "The run paused."
    else:
        reason = CRASHED
    stuck = ending in history.CONTINUABLE and not row["resume_command"]
    missing = stuck and not (row["run_dir"] and Path(row["run_dir"]).is_dir())
    head = HEADS[ending].format(error=row["error_class"] or "failed")
    return {
        "ending": ending,
        "head": f"Ended at {node}: {head}" if node else f"Ended: {head}",
        "fact": f"{FACTS.get(ending) or row['error_class'] or 'failed'} at {node}" if node and ending != "gave-up" else "",
        "text": f"{reason} {_items(row['items_done'], row['items_total'])}".strip(),
        "moment": (moment.get("turn") or moment["key"]) if moment else "",
        "command": row["resume_command"] if ending in history.CONTINUABLE else "",
        "container": bool(row["resume_container"]),
        "gone": missing,
        "unrecorded": stuck and not missing,
    }
