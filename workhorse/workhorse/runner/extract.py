"""Recovering the node's declared outputs from an agent's free-form answer."""

from __future__ import annotations

import json
from typing import Any

from workhorse.runner.failure import OutputParseError
from workhorse.runner.spec import AgentNode

from json_repair import repair_json


def extract_outputs(text: str, node: AgentNode) -> dict[str, Any]:
    if not node.outputs:
        return {}

    wanted = [o.key for o in node.outputs]
    parsed = parse_json_from_text(text, wanted)
    if parsed is None:
        raise OutputParseError(
            f"Node '{node.id}' declared outputs {wanted} "
            f"but agent response contained no parseable JSON"
        )

    result: dict[str, Any] = {}
    for spec in node.outputs:
        if spec.key not in parsed:
            raise OutputParseError(
                f"Node '{node.id}': expected output key '{spec.key}' not found in agent JSON"
            )
        result[spec.key] = parsed[spec.key]
    return result


def parse_json_from_text(text: str, wanted_keys: list[str] | None = None) -> dict | None:
    """Extract the node's JSON object from an agent response.

    Strict first: a well-formed fenced or bare JSON object that already carries
    the declared output keys is parsed with the stdlib and returned unchanged —
    no coercion, so genuinely-malformed output still trips the retry/reframe
    ladder when strict parsing would have been enough.

    An answer that puts the declared keys one level down — ``{"code_review_result":
    {"status": …}}`` — is read through the envelope rather than rejected. Agents wrap
    for a living: a prompt whose example shows the enclosing name, a model narrating
    "here is the code_review_result", and a node whose declared keys were once the
    envelope's name all produce it. The keys asked for are still all there, in one
    object, so refusing costs an entire turn's work to be told again — the run that
    prompted this threw away 134 seconds of a finished code review and re-asked for a
    reply it had already been given. Nothing here knows what any envelope is called;
    the rule is only "the object carrying every declared key, wherever it sits".

    Only when strict parsing fails to yield such an object do we fall back to the
    tolerant ``json-repair`` pass, which fixes trailing commas, single quotes,
    comments, and truncated/unclosed braces, and can return several candidate objects
    when the response embeds more than one (an example plus the real answer, say) — in
    which case we again prefer the object that carries the declared output keys.
    """
    wanted = set(wanted_keys or ())
    objects = _json_objects(text)
    for obj in objects:
        unwrapped = _unwrap(obj, wanted)
        if unwrapped is not None:
            return unwrapped

    tolerant = _parse_json_tolerant(text, wanted)
    if tolerant is not None:
        return tolerant

    # Best strict effort (a dict missing some keys, or None) so the caller can
    # raise the precise "key not found" / "no parseable JSON" error.
    return objects[0] if objects else None


def _unwrap(obj: dict, wanted: set[str]) -> dict | None:
    """``obj`` itself if it carries every wanted key, else the nested object that does.

    Breadth-first, so the shallowest match wins: a `findings` list of objects that each
    happen to carry a `status` must not outrank the envelope's own payload. Returns None
    when nothing carries the full set, which is what keeps a genuinely-incomplete answer
    on the retry ladder instead of quietly promoting some fragment of it.

    With nothing wanted (a node declaring no outputs, or a caller that just wants "the
    JSON") the top object is the answer — every dict trivially contains the empty set,
    so a descent would be arbitrary.
    """
    if not wanted or wanted.issubset(obj):
        return obj
    queue = [v for v in obj.values() if isinstance(v, dict)]
    while queue:
        nxt: list[dict] = []
        for cand in queue:
            if wanted.issubset(cand):
                return cand
            nxt.extend(v for v in cand.values() if isinstance(v, dict))
        queue = nxt
    return None


def _json_objects(text: str) -> list[dict]:
    """Every syntactically-complete JSON object embedded in *text*, in source order.

    Stdlib-only, and a real parse: `json.JSONDecoder().raw_decode` is asked to decode at
    each `{` and reports where the object it found ends. That is what makes fenced blocks
    need no fence-matching of their own — the block's content is simply the next complete
    object — and what fixes the two ways the pair of regexes here used to miss:

    * ``re.search(r"\\{.*\\}", DOTALL)`` spans the *first* brace to the *last* one, so an
      answer that closed with prose containing a `}`, or held an example object as well as
      the real one, parsed as neither;
    * the fenced-block pattern required the object to be the block's whole content, and a
      `}` in a string could end the non-greedy match early.

    Only outermost objects are returned: once one decodes, the scan resumes past its end,
    so `_unwrap` decides which nested object answers rather than the scan order.
    """
    decoder = json.JSONDecoder()
    found: list[dict] = []
    idx = 0
    while (idx := text.find("{", idx)) != -1:
        try:
            obj, end = decoder.raw_decode(text, idx)
        except ValueError:
            idx += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
            idx = end
        else:
            idx += 1
    return found


def _parse_json_tolerant(text: str, wanted: set[str]) -> dict | None:
    """Repair-and-extract via ``json-repair``, preferring the object with the
    wanted keys. Returns None if no dict could be recovered."""
    try:
        obj = repair_json(text, return_objects=True)
    except Exception:  # noqa: BLE001 — repair is best-effort; never let it crash a run
        return None
    return _select_object(obj, wanted)


def _select_object(obj: Any, wanted: set[str]) -> dict | None:
    """Pick the best dict from json-repair output.

    json-repair returns a dict for a single object, a list when the response
    embedded several, and ``''`` / other scalars when nothing JSON-like was
    found. Prefer the last dict (the final answer usually comes last) that
    carries every wanted key — looking through an envelope as :func:`_unwrap`
    does, since a wrapped answer is as wrapped after repair as before it — else
    the last dict seen; else None.
    """
    candidates: list[dict] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            candidates.append(o)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(obj)
    if not candidates:
        return None
    for cand in reversed(candidates):
        found = _unwrap(cand, wanted)
        if found is not None:
            return found
    return candidates[-1]
