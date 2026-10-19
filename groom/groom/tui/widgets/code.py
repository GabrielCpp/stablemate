from __future__ import annotations

from collections import OrderedDict
from typing import ClassVar

from rich.syntax import Syntax
from rich.text import Text
from textual.binding import Binding, BindingType
from textual.geometry import Size
from textual.scroll_view import ScrollView
from textual.strip import Strip

STRIP_CACHE_ROWS = 256
TAB_SIZE = 4
THEME = "monokai"


def highlight_lines(code: str, lexer: str) -> list[Text]:
    pygments_lexer = Syntax(code, lexer).lexer
    theme = Syntax.get_theme(THEME)
    tokens = pygments_lexer.get_tokens(code) if pygments_lexer is not None else [(None, code)]
    lines: list[Text] = []
    current = Text(no_wrap=True)
    for token_type, value in tokens:
        style = theme.get_style_for_token(token_type) if token_type is not None else None
        for at, part in enumerate(value.split("\n")):
            if at:
                lines.append(current)
                current = Text(no_wrap=True)
            if part:
                current.append(part, style)
    if current.plain:
        lines.append(current)
    for line in lines:
        if "\t" in line.plain:
            line.expand_tabs(TAB_SIZE)
    return lines


class CodeView(ScrollView):
    DEFAULT_CSS = """
    CodeView { height: auto; max-height: 75vh; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "scroll_up", "Up", show=False),
        Binding("down", "scroll_down", "Down", show=False),
        Binding("left", "scroll_left", "Left", show=False),
        Binding("right", "scroll_right", "Right", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
    ]
    can_focus = True

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self.lines: list[Text] = []
        self._strips: OrderedDict[int, Strip] = OrderedDict()

    @property
    def plain(self) -> str:
        return "\n".join(line.plain for line in self.lines)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def set_lines(self, lines: list[Text]) -> None:
        self.lines = lines
        self._strips.clear()
        width = max((line.cell_len for line in lines), default=0)
        self.virtual_size = Size(width, len(lines))
        self.scroll_to(0, 0, animate=False, immediate=True)
        self.refresh(layout=True)

    def strip_for(self, row: int) -> Strip:
        strip = self._strips.get(row)
        if strip is None:
            strip = Strip(self.lines[row].render(self.app.console, end="")).simplify()
            self._strips[row] = strip
            if len(self._strips) > STRIP_CACHE_ROWS:
                self._strips.popitem(last=False)
        else:
            self._strips.move_to_end(row)
        return strip

    def render_line(self, y: int) -> Strip:
        row = self.scroll_offset.y + y
        width = self.size.width
        if row >= len(self.lines):
            return Strip.blank(width)
        left = self.scroll_offset.x
        return self.strip_for(row).crop_extend(left, left + width, self.rich_style)
