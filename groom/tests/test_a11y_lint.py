"""Tests for groom.a11y_lint: the dependency-free static a11y linter for the HTML templates.

Each rule is checked positive (fires on the fault) and negative (silent on the accessible form),
plus the load-bearing contract that the shipped dashboard.html stays within the linter's bar for
everything except the two known, tracked unlabeled inputs.

Run: uv run pytest tests/test_a11y_lint.py
"""
from __future__ import annotations

from pathlib import Path

from groom import a11y_lint


def codes(html: str) -> set[str]:
    return {f.code for f in a11y_lint.lint_html(html, "t.html")}


def _doc(body: str, lang: str = ' lang="en"') -> str:
    return f"<!doctype html>\n<html{lang}>\n<head><title>t</title></head>\n<body>{body}</body>\n</html>"


# ---- A11Y001 html lang ----
def test_missing_lang_flagged():
    assert "A11Y001" in codes(_doc("<p>hi</p>", lang=""))


def test_lang_present_ok():
    assert "A11Y001" not in codes(_doc("<p>hi</p>"))


# ---- A11Y002 input label ----
def test_input_with_only_placeholder_flagged():
    assert "A11Y002" in codes(_doc('<input type="text" placeholder="Filter…">'))


def test_input_with_aria_label_ok():
    assert "A11Y002" not in codes(_doc('<input type="text" aria-label="Filter repos">'))


def test_input_with_associated_label_ok():
    assert "A11Y002" not in codes(_doc('<label for="q">Filter</label><input id="q" type="text">'))


def test_input_wrapped_in_label_ok():
    assert "A11Y002" not in codes(_doc("<label>Filter <input type=text></label>"))


def test_hidden_input_not_required_to_have_label():
    assert "A11Y002" not in codes(_doc('<input type="hidden" name="csrf">'))


# ---- A11Y003 img alt ----
def test_img_without_alt_flagged():
    assert "A11Y003" in codes(_doc('<img src="x.png">'))


def test_img_with_empty_alt_ok():
    # alt="" declares the image decorative — that is a valid, deliberate choice.
    assert "A11Y003" not in codes(_doc('<img src="x.png" alt="">'))


# ---- A11Y004 action on non-interactive tag ----
def test_hx_post_on_div_flagged():
    assert "A11Y004" in codes(_doc('<div hx-post="/answer">Send</div>'))


def test_hx_post_on_button_ok():
    assert "A11Y004" not in codes(_doc('<button hx-post="/answer">Send</button>'))


def test_ws_connect_host_not_flagged():
    # ws-connect marks the socket host, not a control — only ws-send is an action.
    assert "A11Y004" not in codes(_doc('<div hx-ext="ws" ws-connect="/ws"><p>x</p></div>'))


# ---- A11Y005 widget role not focusable ----
def test_role_button_without_tabindex_flagged():
    assert "A11Y005" in codes(_doc('<div role="button" aria-label="Close">x</div>'))


def test_role_button_with_tabindex_ok():
    assert "A11Y005" not in codes(_doc('<div role="button" tabindex="0" aria-label="Close">x</div>'))


# ---- A11Y006 accessible name ----
def test_icon_only_button_flagged():
    assert "A11Y006" in codes(_doc('<button><svg></svg></button>'))


def test_button_with_text_ok():
    assert "A11Y006" not in codes(_doc("<button>Send answer</button>"))


def test_button_with_aria_label_ok():
    assert "A11Y006" not in codes(_doc('<button aria-label="Send"><svg></svg></button>'))


def test_aria_hidden_text_does_not_name_a_button():
    assert "A11Y006" in codes(_doc('<button><span aria-hidden="true">×</span></button>'))


# ---- A11Y007 oob live region ----
def test_oob_target_without_live_flagged():
    assert "A11Y007" in codes(_doc('<div id="inbox" hx-swap-oob="true">…</div>'))


def test_oob_target_with_aria_live_ok():
    assert "A11Y007" not in codes(_doc('<div id="inbox" hx-swap-oob="true" aria-live="polite">…</div>'))


def test_oob_target_with_status_role_ok():
    assert "A11Y007" not in codes(_doc('<div id="log" hx-swap-oob="true" role="log">…</div>'))


# ---- shipped template contract ----
def test_shipped_dashboard_is_clean():
    # The shipped template is the linter's own baseline — it must stay at zero findings so the
    # gate is meaningful. If this fails, a real a11y regression landed in dashboard.html.
    tpl = Path(a11y_lint.__file__).parent / "templates" / "dashboard.html"
    findings = a11y_lint.lint_html(tpl.read_text(encoding="utf-8"), str(tpl))
    assert findings == [], "\n".join(str(f) for f in findings)
