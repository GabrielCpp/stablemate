from __future__ import annotations

from rich.text import Text
from textual.widgets import OptionList
from textual.widgets.option_list import Option


def sync_options(
    listing: OptionList, items: list[tuple[str, Text]], cache: dict[str, Text], prefer: str = ""
) -> dict[str, Text]:
    ids = [key for key, _ in items]
    texts = dict(items)
    current = [str(listing.get_option_at_index(i).id) for i in range(listing.option_count)]
    if ids == current:
        for key, text in items:
            if cache.get(key) != text:
                listing.replace_option_prompt(key, text)
        return texts
    if current and ids[: len(current)] == current:
        for key, text in items[: len(current)]:
            if cache.get(key) != text:
                listing.replace_option_prompt(key, text)
        listing.add_options([Option(text, id=key) for key, text in items[len(current) :]])
        return texts
    highlighted = listing.highlighted
    keep = current[highlighted] if highlighted is not None and highlighted < len(current) else ""
    listing.clear_options()
    listing.add_options([Option(text, id=key) for key, text in items])
    if ids:
        wanted = keep if keep in ids else prefer
        listing.highlighted = ids.index(wanted) if wanted in ids else 0
    return texts
