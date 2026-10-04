"""What `focusable(..., activates=)` counts as a control answering its key."""

from __future__ import annotations

from dataclasses import dataclass, field

from ostler.qa.harness_host import load_harness_module

elements = load_harness_module("ostler_qa_elements")


@dataclass
class _Page:
    """A page whose only state is whether the pressed key reached a click handler."""

    clicks_on_key: bool
    control: _Control | None = None

    @dataclass
    class _Keyboard:
        page: _Page

        def press(self, _key: str) -> None:
            control = self.page.control
            assert control is not None
            control.pressed = True

    @property
    def keyboard(self) -> _Page._Keyboard:
        return _Page._Keyboard(self)

    def evaluate(self, _script: str) -> bool:
        return self.clicks_on_key


@dataclass
class _Control:
    """A focused control: `expanded` is its `aria-expanded` before and after the key, None when it has none."""

    page: _Page
    expanded: tuple[str | None, str | None] = (None, None)
    pressed: bool = field(default=False)

    def __post_init__(self) -> None:
        self.page.control = self

    def focus(self) -> None:
        return None

    def element_handle(self) -> _Control:
        return self

    def evaluate(self, script: str) -> object:
        if "activeElement" in script:
            return True
        return self.expanded[1] if self.pressed else self.expanded[0]


def test_a_key_that_clicks_the_control_activates_it() -> None:
    reading = elements.read_focus(_Control(_Page(clicks_on_key=True)), {"activates": "Enter"})
    assert (reading.focused, reading.activated) == (True, True)


def test_a_key_that_opens_a_popup_without_a_click_activates_it() -> None:
    """A select opens its list on the keypress itself, so no click event ever fires on it."""
    control = _Control(_Page(clicks_on_key=False), expanded=("false", "true"))
    reading = elements.read_focus(control, {"activates": "Enter"})
    assert (reading.focused, reading.activated) == (True, True)


def test_a_key_that_neither_clicks_nor_opens_anything_does_not_activate() -> None:
    plain = elements.read_focus(_Control(_Page(clicks_on_key=False)), {"activates": "Enter"})
    assert plain.activated is False
    shut = _Control(_Page(clicks_on_key=False), expanded=("false", "false"))
    assert elements.read_focus(shut, {"activates": "Enter"}).activated is False
    already_open = _Control(_Page(clicks_on_key=False), expanded=("true", "true"))
    assert elements.read_focus(already_open, {"activates": "Enter"}).activated is False
