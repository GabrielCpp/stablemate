from __future__ import annotations

from collections.abc import Callable

from textual.widget import Widget

from groom.tui.link import Frame


class Reconcilable:
    def __init__(self, line_key: str, data: Frame) -> None:
        self.line_key = line_key
        self.data = data

    async def update_data(self, data: Frame) -> bool:
        return False


async def reconcile(
    container: Widget,
    wanted: list[tuple[str, Frame]],
    build: Callable[[str, Frame], Widget],
) -> None:
    keys = {key for key, _ in wanted}
    existing: dict[str, Widget] = {}
    gone: list[Widget] = []
    for child in container.children:
        if isinstance(child, Reconcilable) and child.line_key in keys:
            existing[child.line_key] = child
        else:
            gone.append(child)
    for key, data in wanted:
        child = existing.get(key)
        if isinstance(child, Reconcilable) and child.data != data and not await child.update_data(data):
            gone.append(existing.pop(key))
    if gone:
        await container.remove_children(gone)
    kept = [existing[key] for key, _ in wanted if key in existing]
    if [child for child in container.children if child in kept] != kept:
        for index in range(len(kept) - 2, -1, -1):
            container.move_child(kept[index], before=kept[index + 1])
    group: list[Widget] = []
    for key, data in wanted:
        if key in existing:
            if group:
                await container.mount(*group, before=existing[key])
                group = []
        else:
            group.append(build(key, data))
    if group:
        await container.mount(*group)
