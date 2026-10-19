from __future__ import annotations

from dataclasses import dataclass, field

from groom.tui.link import Frame

LINE_CAP = 3000


@dataclass(frozen=True)
class DiffFile:
    path: str
    added: int
    deleted: int
    text: str


@dataclass
class PathNode:
    name: str
    path: str = ""
    is_file: bool = False
    children: list[PathNode] = field(default_factory=list)


def repo_items(groups: list[Frame], query: str) -> list[Frame]:
    needle = query.strip().lower()
    items: list[Frame] = []
    for group in groups:
        for entry in group.get("repos") or []:
            label = str(entry.get("label") or "")
            if needle and needle not in label.lower():
                continue
            items.append({
                "container": group.get("container"),
                "repo": entry.get("repo") or "",
                "label": label,
                "state": group.get("state"),
                "type": group.get("type"),
            })
    return items


def default_repo(groups: list[Frame], run_id: str, run_name: str) -> Frame:
    for item in repo_items(groups, ""):
        if item["container"] == run_id:
            return {"container": item["container"], "repo": item["repo"], "label": item["label"]}
    return {"container": run_id, "repo": "", "label": run_name}


def _header_path(header: str) -> str:
    rest = header.removeprefix("diff --git ")
    size = (len(rest) - 5) // 2
    if size > 0 and rest.startswith("a/") and rest[2:2 + size] == rest[-size:]:
        return rest[-size:]
    return rest.rpartition(" b/")[2]


def _named(line: str, marker: str) -> str:
    name = line.removeprefix(marker).split("\t")[0]
    return name[2:] if name[:2] in ("a/", "b/") else name


def _diff_file(lines: list[str]) -> DiffFile:
    path = _header_path(lines[0]) if lines[0].startswith("diff --git ") else ""
    old = new = renamed = ""
    added = deleted = 0
    in_hunk = False
    for line in lines[1:]:
        if in_hunk:
            added += line.startswith("+")
            deleted += line.startswith("-")
        elif line.startswith("@@"):
            in_hunk = True
        elif line.startswith("rename to "):
            renamed = line.removeprefix("rename to ")
        elif line.startswith("--- "):
            old = _named(line, "--- ")
        elif line.startswith("+++ "):
            new = _named(line, "+++ ")
    if renamed:
        path = renamed
    elif new and new != "/dev/null":
        path = new
    elif old and old != "/dev/null":
        path = old
    return DiffFile(path, added, deleted, "\n".join(lines).rstrip("\n"))


def split_diff(text: str) -> list[DiffFile]:
    chunks: list[list[str]] = []
    for line in text.split("\n"):
        if line.startswith("diff --git "):
            chunks.append([line])
        elif chunks:
            chunks[-1].append(line)
    if not chunks and text.strip():
        chunks.append(text.split("\n"))
    return [_diff_file(chunk) for chunk in chunks]


def path_tree(paths: list[str]) -> list[PathNode]:
    root = PathNode("")
    folders: dict[tuple[str, ...], PathNode] = {(): root}
    for path in paths:
        parts = tuple(part for part in path.split("/") if part)
        if not parts:
            continue
        for depth in range(1, len(parts)):
            key = parts[:depth]
            if key not in folders:
                node = PathNode(parts[depth - 1])
                folders[key] = node
                folders[key[:-1]].children.append(node)
        folders[parts[:-1]].children.append(PathNode(parts[-1], path, True))
    for node in folders.values():
        node.children.sort(key=lambda n: (n.is_file, n.name.casefold(), n.name))
    return root.children


def capped(text: str, limit: int = LINE_CAP) -> tuple[str, int]:
    lines = text.splitlines()
    return "\n".join(lines[:limit]), len(lines)


def cap_note(total: int, limit: int = LINE_CAP) -> str:
    return f"Showing the first {limit} of {total} lines." if total > limit else ""
