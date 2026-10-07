"""The claim verifiers: every `verify:` kind, by the reading it takes and the judge it applies."""

from __future__ import annotations

from collections.abc import Callable

from ostler_qa_browser_state import read_clipboard, read_stored, read_url, verify_clipboard, verify_stored, verify_url
from ostler_qa_documents import read_body, read_countable, read_document, verify_count, verify_json_path, verify_omits
from ostler_qa_dom import read_attribute, read_focused, verify_attribute, verify_focused
from ostler_qa_elements import (
    read_console,
    read_control,
    read_download,
    read_focus,
    read_hidden,
    read_size,
    read_title,
    read_visibility,
    verify_actionable,
    verify_console,
    verify_download,
    verify_emitted,
    verify_focusable,
    verify_hidden,
    verify_inert,
    verify_title,
    verify_visible,
)
from ostler_qa_files import (
    Tree,
    read_absence,
    read_file,
    read_pair,
    verify_absent,
    verify_contents,
    verify_created,
    verify_keys_unchanged,
    verify_persists,
    verify_removed,
    verify_unchanged,
)
from ostler_qa_paths import JsonValue
from ostler_qa_responses import (
    read_exit,
    read_headers,
    read_response,
    read_stream,
    verify_conflict_on_stale,
    verify_exit_status,
    verify_http_status,
    verify_printed,
    verify_response_header,
)
from ostler_qa_verdicts import Args, Verdict, Verifier, json_value

__all__ = ["VERIFIERS", "JsonValue", "Tree", "Verdict", "json_value"]


def _verifier[R](read: Callable[[object, Args], R], judge: Callable[[R, Args], Verdict]) -> Verifier:
    """A verifier that parses the observation once with *read*, then judges only that reading."""

    def verify(observed: object, args: Args) -> Verdict:
        return judge(read(observed, args), args)

    return verify


VERIFIERS: dict[str, Verifier] = {
    "http_status": _verifier(read_response, verify_http_status),
    "response_header": _verifier(read_headers, verify_response_header),
    "json_path": _verifier(read_document, verify_json_path),
    "unchanged": _verifier(read_pair("unchanged"), verify_unchanged),
    "keys_unchanged": _verifier(read_pair("keys_unchanged"), verify_keys_unchanged),
    "count": _verifier(read_countable, verify_count),
    "absent": _verifier(read_absence, verify_absent),
    "created": _verifier(read_pair("created"), verify_created),
    "removed": _verifier(read_pair("removed"), verify_removed),
    "visible": _verifier(read_visibility, verify_visible),
    "actionable": _verifier(read_control("actionable"), verify_actionable),
    "inert": _verifier(read_control("inert"), verify_inert),
    "hidden": _verifier(read_hidden, verify_hidden),
    "focusable": _verifier(read_focus, verify_focusable),
    "attribute": _verifier(read_attribute, verify_attribute),
    "focused": _verifier(read_focused, verify_focused),
    "title": _verifier(read_title, verify_title),
    "console": _verifier(read_console, verify_console),
    "url": _verifier(read_url, verify_url),
    "stored": _verifier(read_stored, verify_stored),
    "clipboard": _verifier(read_clipboard, verify_clipboard),
    "downloaded": _verifier(read_download, verify_download),
    "persists": _verifier(read_pair("persists"), verify_persists),
    "emitted": _verifier(read_size, verify_emitted),
    "omits": _verifier(read_body, verify_omits),
    "exit_status": _verifier(read_exit, verify_exit_status),
    "stdout": _verifier(read_stream("stdout"), verify_printed),
    "stderr": _verifier(read_stream("stderr"), verify_printed),
    "contents": _verifier(read_file, verify_contents),
    "conflict_on_stale": _verifier(read_response, verify_conflict_on_stale),
}
