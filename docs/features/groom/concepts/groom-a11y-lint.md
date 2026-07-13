---
type: concept
slug: groom-a11y-lint
title: Groom a11y lint
---
# Groom a11y lint

Groom a11y lint is the importable static HTML accessibility-linting module behind
the [groom-a11y-lint CLI](../groom-a11y-lint.md). It exposes the lint rule engine,
the parser-node and finding data shapes, and the constant sets that define which
HTML tags, attributes, input types, and roles the static checks recognize. Its
core scan reads one HTML document at a time, using only information present in the
markup, builds [Groom a11y node](../groom-a11y-node.md) records through the
[Groom a11y HTML tree parser](groom-a11y-html-tree-parser.md), and returns
structured accessibility findings in the [Groom a11y finding](../groom-a11y-finding.md)
format that the CLI renders as `PATH:LINE: CODE MESSAGE` lines. Its accessible-name rules share the
[Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md) for
the `aria-label`, `aria-labelledby`, and `title` branch before evaluating rule-specific fallbacks;
its A11Y006 button, linked-anchor, and ARIA-widget branch delegates the final control-name decision
to the [Control accessible name detector](control-accessible-name-detector.md), which combines the
explicit attribute check with the [Accessible subtree text collector](accessible-subtree-text-collector.md).
Its A11Y005 ARIA-widget branch delegates the keyboard-focusability decision to the
[Widget focusability detector](widget-focusability-detector.md). Its A11Y002 wrapped-label branch
uses the [Ancestor tag collector](ancestor-tag-collector.md) to recognize controls enclosed by a
`<label>` ancestor.

- code: groom/groom/a11y_lint.py
- verify: groom/tests/test_a11y_lint.py::test_missing_lang_flagged,
  groom/tests/test_a11y_lint.py::test_input_with_only_placeholder_flagged,
  groom/tests/test_a11y_lint.py::test_img_without_alt_flagged,
  groom/tests/test_a11y_lint.py::test_hx_post_on_div_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_without_tabindex_flagged,
  groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_oob_target_without_live_flagged,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean

## Contract

- input:
  - `text: str` — the complete HTML document or fragment to inspect.
  - `path: str` — the source label copied into every returned finding so callers can report where
    the defect came from.
- output: an ordered `list[Finding]` in the [Groom a11y finding](../groom-a11y-finding.md) format.
- scope:
  - Static markup only: HTML tags, attributes, text content, parent/child structure captured as
    [Groom a11y node](../groom-a11y-node.md) records, and source line numbers.
  - No browser layout, CSS, JavaScript event-delegation, rendered focus order, or post-HTMX-swap DOM
    state is inspected.
  - Malformed markup is tolerated enough to produce findings from the parse tree that can be built.
- ordering: findings are emitted in parser node order; multiple findings on the same element keep
  the rule evaluation order described below.
- clean result: an empty list means this static rule set found no defects in the supplied text.
- public-api:
  - `Node` is the in-memory [Groom a11y node](../groom-a11y-node.md) element record.
  - `Finding` is the returned [Groom a11y finding](../groom-a11y-finding.md) diagnostic record.
  - `lint_html` is the importable one-document scan function.
  - `main` is the executable module entry point used by the [groom-a11y-lint CLI](../groom-a11y-lint.md).
  - The module constants below are read-only rule tables for tags, attributes, roles, and input types.
- private-helper:
  - The [Explicit accessible name attribute detector](explicit-accessible-name-attribute-detector.md)
    centralizes the accepted explicit naming attributes for form controls, image inputs, and named
    controls.
  - The [Control accessible name detector](control-accessible-name-detector.md) centralizes the
    combined explicit-name-or-subtree-text predicate used by the A11Y006 button, linked-anchor, and
    ARIA-widget branch.
  - The [Accessible subtree text collector](accessible-subtree-text-collector.md) centralizes the
    fallback text calculation used by the A11Y006 control accessible-name rule after a control lacks
    its own explicit accessible-name attribute.
  - The [Widget focusability detector](widget-focusability-detector.md) centralizes the accepted
    static focusability sources for ARIA widget-role elements checked by A11Y005.
  - The [Ancestor tag collector](ancestor-tag-collector.md) centralizes parent-chain tag membership
    for the wrapped-label branch of the A11Y002 form-control-label rule.

## Fields

### field-void_tags

- type: `frozenset[str]`
- default: `{"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}`
- required: true
- code: groom/groom/a11y_lint.py::VOID_TAGS
- meaning: HTML elements that never receive a closing tag and therefore must not remain on the parser open-element stack after their start tag is recorded.

### field-native_interactive

- type: `frozenset[str]`
- default: `{"a", "button", "input", "select", "textarea", "summary"}`
- required: true
- code: groom/groom/a11y_lint.py::NATIVE_INTERACTIVE
- meaning: native HTML controls treated as keyboard-focusable and screen-reader-announced for action and focusability checks; bare anchors still require `href` before they count as focusable.

### field-action_attrs

- type: `frozenset[str]`
- default: `{"onclick", "ws-send", "hx-get", "hx-post", "hx-put", "hx-delete", "hx-patch"}`
- required: true
- code: groom/groom/a11y_lint.py::ACTION_ATTRS
- meaning: attributes that make an element an activating control for the static rule that rejects actions on non-native interactive tags.

### field-widget_roles

- type: `frozenset[str]`
- default: `{"button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "menuitemcheckbox", "menuitemradio", "option"}`
- required: true
- code: groom/groom/a11y_lint.py::WIDGET_ROLES
- meaning: ARIA widget roles that must be keyboard-focusable and must provide an accessible name when used as controls.

### field-live_roles

- type: `frozenset[str]`
- default: `{"status", "log", "alert"}`
- required: true
- code: groom/groom/a11y_lint.py::LIVE_ROLES
- meaning: ARIA roles accepted as live-region semantics for HTMX out-of-band swap targets that receive pushed updates.

### field-no_label_input_types

- type: `frozenset[str]`
- default: `{"hidden", "submit", "reset", "button", "image"}`
- required: true
- code: groom/groom/a11y_lint.py::NO_LABEL_INPUT_TYPES
- meaning: input types excluded from the associated-label rule because their accessible name is absent, not rendered, or comes from value, alt text, or explicit naming attributes instead of a `<label>`.

## Methods

### method-lint_html

- sig: `lint_html(text: str, path: str) -> list[Finding]`
- abstract: false
- code: groom/groom/a11y_lint.py::lint_html
- verify: groom/tests/test_a11y_lint.py::test_missing_lang_flagged,
  groom/tests/test_a11y_lint.py::test_lang_present_ok,
  groom/tests/test_a11y_lint.py::test_input_with_only_placeholder_flagged,
  groom/tests/test_a11y_lint.py::test_input_with_aria_label_ok,
  groom/tests/test_a11y_lint.py::test_input_with_associated_label_ok,
  groom/tests/test_a11y_lint.py::test_input_wrapped_in_label_ok,
  groom/tests/test_a11y_lint.py::test_hidden_input_not_required_to_have_label,
  groom/tests/test_a11y_lint.py::test_img_without_alt_flagged,
  groom/tests/test_a11y_lint.py::test_img_with_empty_alt_ok,
  groom/tests/test_a11y_lint.py::test_hx_post_on_div_flagged,
  groom/tests/test_a11y_lint.py::test_hx_post_on_button_ok,
  groom/tests/test_a11y_lint.py::test_ws_connect_host_not_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_without_tabindex_flagged,
  groom/tests/test_a11y_lint.py::test_role_button_with_tabindex_ok,
  groom/tests/test_a11y_lint.py::test_icon_only_button_flagged,
  groom/tests/test_a11y_lint.py::test_button_with_text_ok,
  groom/tests/test_a11y_lint.py::test_button_with_aria_label_ok,
  groom/tests/test_a11y_lint.py::test_aria_hidden_text_does_not_name_a_button,
  groom/tests/test_a11y_lint.py::test_oob_target_without_live_flagged,
  groom/tests/test_a11y_lint.py::test_oob_target_with_aria_live_ok,
  groom/tests/test_a11y_lint.py::test_oob_target_with_status_role_ok,
  groom/tests/test_a11y_lint.py::test_shipped_dashboard_is_clean
- raises: no accessibility-rule exception is part of the contract; parser-level failures are not
  converted to findings.
- algorithm:
  1. Parse the supplied HTML into [Groom a11y node](../groom-a11y-node.md) records that store each
     element's tag, normalized attributes, source line, parent, children, and direct text.
  2. Collect all explicit `<label for="...">` target ids before rule evaluation so form-control
     label checks can recognize labels that appear before or after their control.
  3. Visit every parsed element in source order and evaluate the static rules below, appending a
     finding immediately when a rule fails.
  4. Return the accumulated findings without printing, sorting, or deduplicating them.

### method-main

- sig: `main(argv: list[str] | None = None) -> int`
- abstract: false
- raises: filesystem read errors, permission errors, invalid UTF-8 input, and unexpected parser or lint failures propagate instead of being converted into formatted findings.
- code: groom/groom/a11y_lint.py::main
- does:
  - Uses the supplied argument list when `argv` is provided, otherwise uses the process arguments after the module name.
  - Converts arguments into filesystem target paths, defaulting to the package-local `templates/` directory when no paths are supplied.
  - Expands targets through the [Groom a11y HTML file selector](groom-a11y-html-file-selector.md), reads each selected HTML file as UTF-8 text, and scans it with `lint_html`.
  - Prints each finding in [Groom a11y finding](../groom-a11y-finding.md) string form.
  - Prints the final `a11y-lint: N finding(s) in M file(s)` summary after re-expanding the selected targets for the file count.
  - Returns `1` when any finding exists and `0` when the scan is clean.

## Static Rules

### A11Y001 html language

- code: A11Y001
- message: `<html> is missing a lang attribute`
- applies-to: `<html>` elements.
- fails-when: the element has no non-empty `lang` attribute.
- passes-when: `lang` exists and is not only whitespace.

### A11Y002 form-control label

- code: A11Y002
- message: `<input|textarea|select> has no associated label (a placeholder is not a label)`
- applies-to: `<input>`, `<textarea>`, and `<select>` elements except input types whose accessible
  name does not come from a label.
- fails-when: the control has no non-empty `aria-label`, `aria-labelledby`, or `title`; its `id` is
  not targeted by a `<label for="...">`; and it is not wrapped by a `<label>` ancestor.
- passes-when:
  - The control has an explicit accessible-name attribute.
  - The control has an `id` referenced by a label's `for` attribute.
  - The [Ancestor tag collector](ancestor-tag-collector.md) reports that the control is inside a
    `<label>` ancestor.
  - The input type is `hidden`, or another no-label input type handled by A11Y003/A11Y006.
- non-label: `placeholder` text never satisfies the rule.

### A11Y003 image alt text

- code: A11Y003
- message: `<img> is missing an alt attribute` or `<input type=image> is missing alt text`
- applies-to: `<img>` elements and `<input type="image">` elements.
- fails-when:
  - An `<img>` omits the `alt` attribute entirely.
  - An image input lacks both non-empty `alt` and an explicit accessible-name attribute.
- passes-when:
  - An `<img>` has an `alt` attribute, including `alt=""` for deliberately decorative images.
  - An image input has non-empty `alt`, `aria-label`, `aria-labelledby`, or `title`.

### A11Y004 action on native control

- code: A11Y004
- message: `'ACTION' on <TAG> — use a real <button>/<a> so it is keyboard-operable`
- applies-to: elements with `onclick`, `ws-send`, `hx-get`, `hx-post`, `hx-put`, `hx-delete`, or
  `hx-patch`.
- fails-when: the action attribute appears on an element that is not a native interactive element,
  `<form>`, or `<label>`.
- passes-when:
  - The action is on `<a>`, `<button>`, `<input>`, `<select>`, `<textarea>`, or `<summary>`.
  - The action is on `<form>` or `<label>`.
  - The element only hosts a non-action HTMX/websocket attribute such as `ws-connect`.

### A11Y005 widget focusability

- code: A11Y005
- message: `role=ROLE on <TAG> is not keyboard focusable (add tabindex=0)`
- applies-to: elements with widget roles `button`, `link`, `checkbox`, `radio`, `switch`, `tab`,
  `menuitem`, `menuitemcheckbox`, `menuitemradio`, or `option`.
- fails-when: the element is not focusable.
- passes-when:
  - It has `tabindex` with any value except `-1`.
  - It is a native interactive element; bare `<a>` only counts when it has `href`.
  - It has `contenteditable`.

### A11Y006 control accessible name

- code: A11Y006
- message: `<TAG> role=ROLE has no accessible name` or `<input type=TYPE> has no accessible name`
- applies-to: `<button>`, linked `<a>` controls, elements with widget roles, and submit/reset/button
  input types.
- fails-when: a submit/reset/button input has neither `value` nor explicit accessible-name attribute,
  or a button, linked anchor, or ARIA widget has no explicit accessible-name attribute and no
  accessible text from its subtree as decided by the
  [Control accessible name detector](control-accessible-name-detector.md).
- passes-when:
  - A submit/reset/button input has non-empty `value` text.
  - The control has non-empty `aria-label`, `aria-labelledby`, or `title`.
  - The control has visible text that is not under `aria-hidden="true"`.
  - A child `<img>` contributes its `alt` text.
  - A named child contributes its explicit label to the parent's accessible text calculation.
- ignored: bare `<a>` elements without `href` are not treated as controls for this rule.

### A11Y007 pushed update announcement

- code: A11Y007
- message: `hx-swap-oob target has no aria-live/role — pushed updates won't be announced`
- applies-to: elements with `hx-swap-oob`.
- fails-when: the target has neither non-empty `aria-live` nor a live-region role.
- passes-when: the target has `aria-live`, `role="status"`, `role="log"`, or `role="alert"`.

## Finding String Form

Every returned finding formats as `PATH:LINE: CODE MESSAGE` when converted to text. The `PATH` is
the caller-supplied `path`, `LINE` is the parsed element's one-based source line, `CODE` is one of
the static rule codes above, and `MESSAGE` is the rule-specific human-readable description.
