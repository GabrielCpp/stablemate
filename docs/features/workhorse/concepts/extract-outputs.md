---
type: concept
slug: extract-outputs
title: _extract_outputs — parse agent JSON into declared outputs
---
# _extract_outputs — parse agent JSON into declared outputs

Turns one agent-CLI turn's raw text into the [node](../workflow-format.md#agent)'s declared
`outputs` dict. Called once per attempt by [`_invoke_and_parse`](invoke-and-parse.md#algorithm)
(step 2), which treats a raised `OutputParseError` as a same-session-retry signal, and ultimately by
[`run_agent`](run-agent.md)'s ladder, which treats an escaped `OutputParseError` as a reframe
trigger. Delegates the actual text→JSON recovery to `_parse_json_from_text`, a hardened,
strict-then-tolerant pipeline built to survive the ways a model's response breaks a naive
`json.loads` (prose around the object, multiple embedded objects, lenient syntax, truncated braces).

- code: `workhorse/workhorse/runner/agent.py::_extract_outputs`
- verify: `workhorse/tests/test_json_parse.py::test_extract_outputs_happy_path`,
  `workhorse/tests/test_json_parse.py::test_extract_outputs_no_json_raises`,
  `workhorse/tests/test_json_parse.py::test_extract_outputs_missing_key_raises`,
  `workhorse/tests/test_json_parse.py::test_extract_outputs_no_outputs_returns_empty`

## Contract

- **Input:**
  - `text: str` — the raw turn text returned by `_invoke_claude` (a completed CLI turn's result
    text; not empty — an empty result is retried as transient before this function ever runs).
  - `node: AgentNode` — supplies `node.id` (error messages) and `node.outputs: list[OutputSpec]`
    (the [output keys](../workflow-format.md#outputspec) to extract).
- **Output:** `dict[str, Any]` — one entry per `spec.key` in `node.outputs`, valued from the parsed
  JSON. `{}` when `node.outputs` is empty (a node that declares no outputs never needs to parse).
- **Raises:** `OutputParseError` (a `RuntimeError` subclass, distinct so the runner's ladder retries
  only this recoverable, re-promptable mistake and not e.g. a CLI crash) when:
  - no JSON object could be recovered from `text` at all — message: `"Node '{node.id}' declared
    outputs {wanted} but agent response contained no parseable JSON"`;
  - an object was recovered but is missing one of the declared keys — message: `"Node '{node.id}':
    expected output key '{spec.key}' not found in agent JSON"` (raised on the **first** missing key
    found, in `node.outputs` order).

## Algorithm

```
def _extract_outputs(text, node):
    if not node.outputs: return {}
    wanted = [o.key for o in node.outputs]
    parsed = _parse_json_from_text(text, wanted)
    if parsed is None: raise OutputParseError("... no parseable JSON")
    result = {}
    for spec in node.outputs:
        if spec.key not in parsed: raise OutputParseError(f"... key '{spec.key}' not found ...")
        result[spec.key] = parsed[spec.key]
    return result
```

1. **Short-circuit.** A node with no declared `outputs` returns `{}` without inspecting `text` —
   there is nothing to extract.
2. **Recover a JSON object.** `_parse_json_from_text(text, wanted)` runs the strict-then-tolerant
   pipeline below and returns the best dict it could find, or `None`.
3. **No object at all → raise.** `parsed is None` means neither pass could locate anything
   dict-shaped; this is the "no parseable JSON" error.
4. **Require every declared key.** Even a successfully-parsed object can be the *wrong* one (e.g.
   an example the model included before its real answer) or genuinely incomplete; the loop raises
   on the first `spec.key` missing rather than silently omitting it, so a partial answer trips a
   retry instead of silently defaulting fields downstream.
5. **Return the declared subset.** Only `node.outputs`' keys are copied into `result` — any extra
   keys the model's JSON happened to include are dropped, so the context merge never picks up
   unrequested state.

### `_parse_json_from_text(text, wanted_keys)` — strict-then-tolerant recovery

- code: `workhorse/workhorse/runner/agent.py::_parse_json_from_text`
- verify: `workhorse/tests/test_json_parse.py::test_strict_fenced_block`,
  `workhorse/tests/test_json_parse.py::test_prose_with_stray_brace_picks_real_object`,
  `workhorse/tests/test_json_parse.py::test_multiple_objects_prefers_one_with_wanted_keys`,
  `workhorse/tests/test_json_parse.py::test_multiple_objects_falls_back_to_last_when_none_match`,
  `workhorse/tests/test_json_parse.py::test_trailing_comma_repaired`,
  `workhorse/tests/test_json_parse.py::test_truncated_object_closed`,
  `workhorse/tests/test_json_parse.py::test_pure_prose_returns_none`

Strict is tried first and returned **unchanged, with no coercion**, so genuinely-malformed output
still trips the retry/reframe ladder even when strict parsing alone would have sufficed — the
tolerant pass only runs when strict can't yield an object carrying every wanted key.

```
wanted = set(wanted_keys or ())
strict = _parse_json_strict(text)
if strict is not None and wanted.issubset(strict):
    return strict
tolerant = _parse_json_tolerant(text, wanted)
if tolerant is not None:
    return tolerant
return strict   # best strict effort (dict missing keys, or None) for the caller's error message
```

1. **`_parse_json_strict(text)`** — stdlib-only, two attempts in order, first hit wins:
   1. A fenced block: `` ```(json)?\s*(\{.*?\})\s*``` `` (non-greedy `{.*?}` — the *first* fenced
      object), parsed with `json.loads`.
   2. A bare top-level object: the first `{` to the last `}` in the whole text (greedy `\{.*\}`,
      `re.DOTALL`), parsed with `json.loads`.
   - Either regex matching but failing `json.loads` (a `JSONDecodeError`) falls through silently to
     the next attempt, then to `None`.
2. **Strict success + has every wanted key → return it immediately**, unmodified.
3. **Otherwise fall back to `_parse_json_tolerant(text, wanted)`** — see below. Its result, if any,
   wins over the strict result (even if strict found *something*, a tolerant pass carrying the
   wanted keys is preferred).
4. **Both fail → return `strict`** (whatever `_parse_json_strict` produced — a keys-incomplete dict,
   or `None`) so `_extract_outputs` can raise the precise "no parseable JSON" vs. "key not found"
   error instead of a generic one.

### `_parse_json_tolerant(text, wanted)` — `json-repair` fallback

- code: `workhorse/workhorse/runner/agent.py::_parse_json_tolerant`

Repairs the four break modes strict parsing can't survive: prose surrounding the object, multiple
embedded objects (e.g. an example plus the real answer), lenient syntax (trailing commas, single
quotes, comments), and truncated/unclosed braces.

1. **Optional dependency.** `_repair_json` is `json_repair.repair_json` if the `json-repair` package
   is importable at module load, else `None`. If `None`, this function returns `None` immediately —
   the strict-only result stands and json-repair is simply unavailable in that environment.
2. **Repair.** `_repair_json(text, return_objects=True)` — returns a `dict` for a single recovered
   object, a `list` when the text embedded more than one, or a scalar (e.g. `''`) when nothing
   JSON-like was found. Any exception during repair is swallowed (`except Exception`) and treated as
   no result — repair is best-effort and must never itself crash a turn.
3. **Select.** `_select_object(obj, wanted)` (below) picks the best candidate dict from the repair
   output.

### `_select_object(obj, wanted)` — best-candidate picker

- code: `workhorse/workhorse/runner/agent.py::_select_object`
- verify: `workhorse/tests/test_json_parse.py::test_select_object_from_list_prefers_wanted`,
  `workhorse/tests/test_json_parse.py::test_select_object_empty_string_is_none`

```
candidates = []
def walk(o):
    if isinstance(o, dict): candidates.append(o)
    elif isinstance(o, list):
        for item in o: walk(item)
walk(obj)
if not candidates: return None
for cand in reversed(candidates):
    if wanted.issubset(cand): return cand
return candidates[-1]
```

1. **Flatten.** `walk` recurses through `obj` collecting every `dict` it finds, descending into
   `list`s (so a repair result of several embedded objects yields one candidate per object) but not
   into dict values (a dict's own nested dicts are not separately considered — only the top-level
   objects `json-repair` recovered).
2. **No candidates → `None`.** `obj` was a scalar (e.g. `json-repair`'s `''` for unparseable text).
3. **Prefer the last dict carrying every wanted key**, scanning in reverse — the real answer usually
   comes after any examples/scratch objects earlier in the response.
4. **Else fall back to the last candidate seen**, regardless of its keys — `_extract_outputs` will
   then raise the precise "key not found" error rather than "no parseable JSON" for this case.

## Related pieces

- [`_invoke_and_parse`](invoke-and-parse.md) — the caller; treats `OutputParseError` as a
  same-session-retry signal via `_retry_prompt`.
- [`run_agent`](run-agent.md) — the outer ladder; treats an `OutputParseError` that survives all of
  `_invoke_and_parse`'s same-session retries as [Layer 3](run-agent.md#the-ladder)'s reframe
  trigger.
- [`OutputSpec`](../workflow-format.md#outputspec) — the per-output declaration (`key`/`default`)
  this function reads `node.outputs` from; `default` itself is only consumed later, by
  [`run_agent`](run-agent.md#the-ladder)'s Layer 4 (`_default_outputs`), not by this function.
