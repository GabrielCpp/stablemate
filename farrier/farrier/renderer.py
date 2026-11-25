"""The ``Renderer`` — stateful rendering of library sources into agent adapters."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, UndefinedError

from farrier._vendor.stablemate_core.harness import (
    RepoLayout,
    Surface,
    repo_harnesses,
    spec,
    with_surface,
)
from farrier._vendor.stablemate_core.skill_refs import (
    RETIRED_HELPERS,
    SkillCatalog,
    SkillEntry,
    SkillRefs,
    retired_hint,
)
from farrier.agents import REPO_SKILL_DIRS
from farrier.frontmatter import (
    first_heading,
    frontmatter_metadata,
    frontmatter_tags,
    normalize_tags,
    split_front_matter,
)
from farrier.banners import (
    asset_banner,
    home_root_banner,
    local_instruction_banner,
    root_banner,
    skill_metadata_block,
    with_banner,
)
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_CONTEXT_MANIFEST_FMT,
    LAUNCHER_ROOT_MAKEFILE,
    render_agents_mk,
)
from farrier.layers import available_names, find_in_layers
from farrier.link_rebase import rebase_links
from farrier.naming import compose_name, repo_prefix, yaml_quote
from farrier.ownership import is_generated
from farrier.prompt_render import (
    ARGUMENTS,
    ARGUMENTS_CALL,
    CODEX_NAME_ONLY,
    COMMAND_ARGUMENTS,
    SKILL_ARGUMENTS,
    command_text,
    prompt_skill_text,
    strip_arguments_placeholder,
)
from farrier.selection_errors import unknown_selection_error
from farrier.sources import (
    POLICY_ROOT,
    Asset,
    Source,
    build_lookup,
    build_policy_lookup,
    library_name,
    library_path,
    library_source_path,
    public_name,
    skill_assets,
)

LOCAL_TEXT_SOURCE = "agents.yml"


class Rendered(str):
    """A generated file's text, plus how it must be written."""

    executable: bool = False
    verbatim: bool = False
    assumed: bool = False
    sources: tuple[str, ...] = ()
    parts: tuple[tuple[str, str], ...] = ()

    def __new__(
        cls,
        text: str,
        *,
        executable: bool = False,
        verbatim: bool = False,
        assumed: bool = False,
        sources: tuple[str, ...] = (),
        parts: tuple[tuple[str, str], ...] = (),
    ):
        rendered = super().__new__(cls, text)
        rendered.executable = executable
        rendered.verbatim = verbatim
        rendered.assumed = assumed
        rendered.sources = sources
        rendered.parts = parts
        return rendered


class Symlink(str):
    """A symlink to install. Its text is the relative target it points at."""

    @property
    def target(self) -> str:
        return str(self)


Output = str


def read_asset_text(asset: Asset) -> str:
    """A bundled asset's text, with a decodable error message when it is not text."""
    try:
        return asset.path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"error: bundled asset {asset.path} is not UTF-8 text. Skill assets are "
            "rendered and diffed as text; keep binaries out of references/ and "
            "scripts/ (fetch or generate them at run time instead)."
        ) from exc


USER_HARNESS_DIRS = {
    spec.name: spec.home.dir
    for spec in with_surface(Surface.HOME_ROOT)
    if spec.home is not None
}

USER_ROOT_FILES = {
    spec.name: spec.home.root_file
    for spec in with_surface(Surface.HOME_ROOT)
    if spec.home is not None
}


TEMPLATE_TOKENS = (
    "{%",
    ARGUMENTS_CALL,
    "skill_link(",
    "skill_path(",
    "skill_command(",
    "find_by_tags(",
    "has_skill(",
    "repo.",
    "template.",
    "vars.",
    *(f"{name}(" for name in RETIRED_HELPERS),
)


def repo_layout(target: str, what: str) -> RepoLayout:
    """Where *target* writes in a repo, or a SystemExit naming *what* it cannot render."""
    try:
        layout = spec(target).repo
    except ValueError:
        layout = None
    if layout is None:
        raise SystemExit(f"Unknown {what} render target: {target}")
    return layout


def user_harness_dir(target: str) -> str:
    if target not in USER_HARNESS_DIRS:
        raise SystemExit(f"Unknown user-scope render target: {target}")
    return USER_HARNESS_DIRS[target]


class Renderer:
    def __init__(
        self,
        repo: Path,
        prefix: str,
        repo_config: dict[str, Any],
        template_values: dict[str, Any],
        skills: list[Source],
        prompts: list[Source],
        policies: list[Source] | None = None,
        scope: str = "repo",
        home_skills: dict[str, list[Source]] | None = None,
        hand_written_dirs: Sequence[str] = (),
        skill_forms: Mapping[str, str] | None = None,
    ):
        self.repo = repo
        self.skill_forms = dict(skill_forms or {})
        self.hand_written_dirs = tuple(hand_written_dirs)
        self.scope = scope
        self.regenerate = (
            "make agent-install" if scope == "repo" else "farrier install --user"
        )
        self.overwritten_by = (
            "`make agent-install` (or: farrier --repo .)"
            if scope == "repo"
            else "`farrier install --user`"
        )
        self.prefix = prefix
        self.repo_context = dict(repo_config)
        self.repo_context["name"] = repo_prefix(repo, repo_config)
        self.repo_context["prefix"] = prefix
        self.repo_context["root"] = repo.as_posix()
        self.template_values = template_values
        self.skills = skills
        self.prompts = prompts
        self.skill_lookup = build_lookup(skills)
        self.prompt_lookup = build_lookup(prompts)
        self.home_lookups = {
            target: build_lookup(sources)
            for target, sources in (home_skills or {}).items()
        }
        self.unresolved: list[str] = []
        self.policies = list(policies or [])
        self.policy_lookup = build_policy_lookup(self.policies)
        self._tags: dict[Path, list[str]] = {}
        self._catalogs: dict[str, SkillCatalog] = {}

    def dest_rel(self, output_path: Path) -> str:
        """*output_path* as the generated file names itself, for `farrier source`."""
        rel = output_path.relative_to(self.repo).as_posix()
        return f"~/{rel}" if self.scope == "user" else rel

    def skill_tags(self, source: Source) -> list[str]:
        """The `tags:` a library skill declares."""
        cached = self._tags.get(source.path)
        if cached is None:
            cached = frontmatter_tags(source.path.read_text(encoding="utf-8"))
            self._tags[source.path] = cached
        return cached

    def skill_source(self, name: str) -> Source:
        source = self.skill_lookup.get(name.replace(".", "-"))
        if source is None:
            raise SystemExit(f"Unknown selected skill reference: {name}")
        return source

    def _entry(self, source: Source, installed: str, path: Path) -> SkillEntry:
        tags = tuple(self.skill_tags(source)) if source.kind == "skill" else ()
        return SkillEntry(
            name=library_name(source), installed=installed, path=path, tags=tags
        )

    def catalog(self, target: str) -> SkillCatalog:
        """What a file rendered for *target* resolves against: this install, then home."""
        entries = [
            self._entry(
                source,
                public_name(self.prefix, source),
                self.skill_output_path(library_name(source), target),
            )
            for source in self.skills
        ]
        entries += [
            self._entry(
                source,
                public_name(self.prefix, source),
                self.prompt_output_path(library_name(source), target),
            )
            for source in self.prompts
        ]
        if self.scope == "repo":
            taken = {entry.name for entry in entries}
            for folder in self.hand_written_folders():
                aliases = [folder]
                stripped = folder.removeprefix(f"{self.prefix}-")
                if stripped != folder:
                    aliases.append(stripped)
                tags = self.hand_written_tags(folder)
                for name in aliases:
                    if name in taken:
                        continue
                    taken.add(name)
                    entries.append(
                        SkillEntry(
                            name=name,
                            installed=folder,
                            path=self.repo
                            / REPO_SKILL_DIRS[target]
                            / folder
                            / "SKILL.md",
                            tags=tags if name == aliases[0] else (),
                        )
                    )
            home = Path.home() / user_harness_dir(target) / "skills"
            entries += [
                self._entry(
                    source,
                    public_name("", source),
                    home / public_name("", source) / "SKILL.md",
                )
                for source in self.home_lookups.get(target, {}).values()
            ]
        return SkillCatalog.of(entries)

    def skill_refs(self, target: str, from_file: Path) -> SkillRefs:
        """The reference helpers for one file rendered for *target*."""
        catalog = self._catalogs.get(target)
        if catalog is None:
            catalog = self._catalogs[target] = self.catalog(target)

        def missing(name: str) -> str:
            self.unresolved.append(
                f"  - {self.dest_rel(from_file)} → {name!r} "
                f"(not in [user_library.{target}])"
            )
            return f"generated {name} skill when installed"

        return SkillRefs(
            catalog=catalog,
            harness=target,
            base=from_file.parent,
            root=self.repo,
            home=Path.home(),
            on_missing=missing,
            form=self.skill_forms.get(target),
        )

    def check_resolved(self) -> None:
        """Exit naming every skill reference found neither in this install nor at home."""
        if self.unresolved:
            raise SystemExit(
                "error: these generated files reference skills that neither this "
                "repo's selection nor the stablemate config's user library installs. "
                "Select each one in agents.yml, add it to the user library, or drop "
                "the reference from the library source:\n"
                + "\n".join(dict.fromkeys(self.unresolved))
            )

    def policy_source(self, name: str) -> Source:
        """The library file a ``policies:`` entry names, or exit."""
        key = name.replace(".", "-")
        source = self.policy_lookup.get(key)
        if source is None:
            available = sorted({library_name(s) for s in self.policies})
            catalog = (
                "Available policies: " + ", ".join(available)
                if available
                else "The library layers hold no policies at all."
            )
            raise SystemExit(f"Unknown policy reference: {name}. {catalog}")
        return source

    def prompt_source(self, name: str) -> Source:
        key = name.replace(".", "-")
        if key not in self.prompt_lookup:
            raise SystemExit(f"Unknown selected prompt reference: {name}")
        return self.prompt_lookup[key]

    def skill_output_path(self, name: str, target: str) -> Path:
        source = self.skill_source(name)
        generated = public_name(self.prefix, source)
        if self.scope == "user":
            return (
                self.repo / user_harness_dir(target) / "skills" / generated / "SKILL.md"
            )
        return self.repo / repo_layout(target, "skill").skills / generated / "SKILL.md"

    def takes_prompts(self, target: str) -> bool:
        """Whether *target* has a prompt folder in this scope."""
        if self.scope == "user":
            return target == "claude"
        layout = spec(target).repo
        return layout is not None and layout.prompts is not None

    def prompt_output_path(self, name: str, target: str) -> Path:
        """Where a prompt lands: the prompt folder, else a skill run by name."""
        source = self.prompt_source(name)
        generated = public_name(self.prefix, source)
        if not self.takes_prompts(target):
            return self.skill_dir_path(target) / generated / "SKILL.md"
        if self.scope == "user":
            return self.repo / ".claude" / "commands" / f"{generated}.md"
        layout = repo_layout(target, "prompt")
        return self.repo / (layout.prompts or "") / f"{generated}{layout.prompt_suffix}"

    def arguments_text(self, target: str) -> str:
        """What a prompt's ``$ARGUMENTS`` renders as for *target*."""
        if not self.takes_prompts(target):
            return SKILL_ARGUMENTS
        return COMMAND_ARGUMENTS.get(target, ARGUMENTS)

    def skill_dir_path(self, target: str) -> Path:
        if self.scope == "user":
            return self.repo / user_harness_dir(target) / "skills"
        if target in REPO_SKILL_DIRS:
            return self.repo / REPO_SKILL_DIRS[target]
        raise SystemExit(f"Unknown skill dir target: {target}")

    def render_templates(
        self,
        content: str,
        target: str,
        from_file: Path,
        arguments: str = ARGUMENTS,
    ) -> str:
        if not any(token in content for token in TEMPLATE_TOKENS):
            return content
        env = Environment(autoescape=False, undefined=StrictUndefined)
        template = env.from_string(content)

        def workhorse_var(name: str) -> str:
            """Emit a runtime variable reference that workhorse will fill at run time."""
            return "{{ " + name + " }}"

        repo_context: Any = (
            self.repo_context
            if self.scope == "repo"
            else StrictUndefined(
                hint="`repo.…` has no value at user scope — a user-scope skill is "
                "installed once for every project, so there is no repo to name."
            )
        )
        try:
            return template.render(
                **self.skill_refs(target, from_file).globals(),
                workhorse_var=workhorse_var,
                repo=repo_context,
                template=self.template_values,
                vars=self.template_values,
                target=target,
                arguments=arguments,
            )
        except UndefinedError as exc:
            raise SystemExit(
                f"error: {from_file.name} references a template value that is not "
                f"defined: {exc.message}{retired_hint(exc.message or '')}\n"
                "Define it under `vars:` in agents.yml, or under "
                "`[user_library.template]` for a user-scope install — or guard the "
                'reference in the library source with `| default("…")`.'
            ) from exc

    def context_manifest(self, target: str) -> dict[str, Any]:
        """Per-repo manifest consumed by workhorse at run time (see workhorse/templates.py)."""

        def rel(path: Path) -> str:
            return path.relative_to(self.repo).as_posix()

        instructions = {
            key: rel(self.skill_output_path(library_name(source), target))
            for key, source in self.skill_lookup.items()
        }
        prompts = {
            key: rel(self.prompt_output_path(library_name(source), target))
            for key, source in self.prompt_lookup.items()
            if self.takes_prompts(target)
        }
        instruction_tags = {
            key: tags
            for key, source in self.skill_lookup.items()
            if (tags := self.skill_tags(source))
        }
        repo_context = {**self.repo_context, "root": "."}
        return {
            "template": self.template_values,
            "repo": repo_context,
            "vars": self.template_values,
            "instructions": instructions,
            "instruction_tags": instruction_tags,
            "prompts": prompts,
            "used_skills": sorted(self.skill_lookup.keys()),
            "skill_dir": rel(self.skill_dir_path(target)),
        }

    def skill_description(
        self, source: Source, header: dict[str, str], body: str
    ) -> str:
        title = first_heading(body, public_name(self.prefix, source))
        apply_to = header.get("applyTo")
        if header.get("description"):
            return header["description"]
        if apply_to:
            return f"Use for {self.prefix} repository work involving {title}. Applies to {apply_to}."
        return f"Use for {self.prefix} repository work involving {title}."

    def rendered_source(
        self, source: Source, target: str, output_path: Path
    ) -> tuple[dict[str, str], str]:
        """*source*'s front matter and body with the target's templates filled in."""
        header, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        header = {
            key: self.render_templates(value, target, output_path)
            for key, value in header.items()
        }
        arguments = ARGUMENTS
        if source.kind == "prompt":
            body = body.replace(ARGUMENTS, ARGUMENTS_CALL)
            arguments = self.arguments_text(target)
        return header, self.render_templates(
            body, target, output_path, arguments
        ).strip()

    def generated_skill(self, source: Source, target: str, output_path: Path) -> str:
        header, body = self.rendered_source(source, target, output_path)
        name = public_name(self.prefix, source)
        description = self.skill_description(source, header, body)
        dest_rel = self.dest_rel(output_path)
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {yaml_quote(description)}\n"
            f"{skill_metadata_block(source, dest_rel, self.skill_tags(source), self.regenerate)}"
            "---\n"
            "\n"
            f"{body}\n"
        )

    def generated_assets(
        self, source: Source, target: str, skill_path: Path
    ) -> dict[Path, Rendered]:
        """The files bundled with *source*, keyed by where they install."""
        if skill_path.name != "SKILL.md":
            raise SystemExit(
                f"Cannot render bundled assets into the flat {target!r} layout "
                f"({skill_path.name}) — skill assets need a per-skill directory."
            )
        outputs: dict[Path, Rendered] = {}
        for asset in skill_assets(source):
            output_path = skill_path.parent / asset.rel
            text = read_asset_text(asset)
            if asset.is_script or asset.path.suffix != ".md":
                outputs[output_path] = Rendered(
                    text, executable=asset.is_script, verbatim=True
                )
                continue
            dest_rel = self.dest_rel(output_path)
            body = self.render_templates(text, target, output_path).strip()
            outputs[output_path] = Rendered(
                asset_banner(asset, dest_rel, self.overwritten_by) + body + "\n"
            )
        return outputs

    def skill_folder_names(
        self, source_dir: Path, outputs: Mapping[Path, str]
    ) -> list[str]:
        """The skill folders *source_dir* holds after this run: rendered ones and hand-written ones."""
        names = {
            path.relative_to(source_dir).parts[0]
            for path in outputs
            if source_dir in path.parents
        }
        if source_dir.is_dir():
            names.update(
                entry.name
                for entry in source_dir.iterdir()
                if entry.is_dir()
                and not entry.is_symlink()
                and (entry / "SKILL.md").is_file()
                and not is_generated(entry / "SKILL.md")
            )
        return sorted(names)

    def link_skills(
        self, links: Mapping[str, str], outputs: Mapping[Path, str]
    ) -> dict[Path, Symlink]:
        """A relative symlink in each linked harness's skills dir to every folder of its source's."""
        symlinks: dict[Path, Symlink] = {}
        for linked, source in links.items():
            source_dir = self.skill_dir_path(source)
            linked_dir = self.skill_dir_path(linked)
            for name in self.skill_folder_names(source_dir, outputs):
                target = os.path.relpath(source_dir / name, linked_dir)
                symlinks[linked_dir / name] = Symlink(target.replace(os.sep, "/"))
        return symlinks

    def check_roots(self, roots: set[str]) -> None:
        """Fail on any selected root that names no file in the library."""
        unknown_roots = sorted(
            root
            for root in roots
            if find_in_layers("library", "roots", f"{root}.md") is None
        )
        if unknown_roots:
            raise SystemExit(
                unknown_selection_error(
                    "roots",
                    unknown_roots,
                    available_names("library", "roots", suffix=".md"),
                    extra=(
                        "A repo's roots render only into the copilot adapter, but the "
                        "name is validated whether or not copilot is enabled — otherwise "
                        "a bad declaration stays dormant until someone switches copilot on."
                    ),
                )
            )

    def home_root(self, root: str, target: str) -> dict[Path, str]:
        """The harness's always-on instruction file in the home, rendered from *root*."""
        self.check_roots({root})
        root_hit = find_in_layers("library", "roots", f"{root}.md")
        assert root_hit is not None
        _root_layer, root_path = root_hit
        output_path = self.repo / USER_ROOT_FILES[target]
        content = self.render_templates(
            root_path.read_text(encoding="utf-8"), target, output_path
        )
        source_rel = library_path(root_path, f"roots/{root}.md")
        return {output_path: with_banner(content, home_root_banner(source_rel))}

    def render(
        self,
        agents: Mapping[str, bool],
        roots: set[str],
        links: Mapping[str, str] | None = None,
    ) -> dict[Path, str]:
        links = links or {}
        outputs: dict[Path, str] = {}

        rendered_folders: set[Path] = set()
        prompt_folders: set[Path] = set()

        def render_skills(target: str) -> None:
            """Every selected skill into *target*, each with its bundled assets."""
            if target in links:
                return
            folder = self.skill_dir_path(target)
            if folder in rendered_folders:
                return
            rendered_folders.add(folder)
            for source in self.skills:
                output_path = self.skill_output_path(library_name(source), target)
                outputs[output_path] = self.generated_skill(source, target, output_path)
                outputs.update(self.generated_assets(source, target, output_path))

        def render_prompts(target: str) -> None:
            """Every selected prompt into *target*: a command, else a skill run by name."""
            if self.takes_prompts(target):
                for source in self.prompts:
                    output_path = self.prompt_output_path(library_name(source), target)
                    outputs[output_path] = command_text(
                        self, source, target, output_path
                    )
                return
            folder = self.skill_dir_path(target)
            if folder in prompt_folders:
                return
            prompt_folders.add(folder)
            reaches_codex = folder == self.skill_dir_path("codex")
            for source in self.prompts:
                output_path = self.prompt_output_path(library_name(source), target)
                outputs[output_path] = prompt_skill_text(
                    self, source, target, output_path
                )
                if reaches_codex:
                    outputs[output_path.parent / "agents" / "openai.yaml"] = Rendered(
                        CODEX_NAME_ONLY, verbatim=True
                    )

        if agents.get("copilot"):
            render_skills("copilot")
            render_prompts("copilot")

            for root in roots:
                root_hit = find_in_layers("library", "roots", f"{root}.md")
                if root_hit is not None:
                    _root_layer, root_path = root_hit
                    source_rel = library_path(root_path, f"roots/{root}.md")
                    for output_path in [
                        self.repo / ".github" / "copilot-instructions.md",
                        self.repo / ".github" / "agents" / "copilot-instructions.md",
                    ]:
                        content = self.render_templates(
                            root_path.read_text(encoding="utf-8"),
                            "copilot",
                            output_path,
                        )
                        dest_rel = output_path.relative_to(self.repo).as_posix()
                        outputs[output_path] = with_banner(
                            content, root_banner(source_rel, dest_rel)
                        )

        if agents.get("codex"):
            render_skills("codex")
            render_prompts("codex")

        if agents.get("antigravity"):
            render_skills("antigravity")
            render_prompts("antigravity")

        if agents.get("pi"):
            render_skills("pi")
            render_prompts("pi")

        if agents.get("claude"):
            render_skills("claude")
            render_prompts("claude")

        self.check_roots(roots)

        if self.scope == "user":
            return outputs

        outputs[self.repo / LAUNCHER_AGENTS_MK] = render_agents_mk()

        enabled_assistants = [
            harness.name for harness in repo_harnesses() if agents.get(harness.name)
        ]
        manifest_target = enabled_assistants[0] if enabled_assistants else "claude"
        for assistant in enabled_assistants:
            outputs[self.repo / LAUNCHER_CONTEXT_MANIFEST_FMT.format(assistant)] = (
                json.dumps(self.context_manifest(assistant), indent=2, sort_keys=True)
                + "\n"
            )
        outputs[self.repo / LAUNCHER_CONTEXT_MANIFEST] = (
            json.dumps(self.context_manifest(manifest_target), indent=2, sort_keys=True)
            + "\n"
        )

        root_makefile = self.repo / LAUNCHER_ROOT_MAKEFILE
        if not root_makefile.exists():
            outputs[root_makefile] = (
                "# Thin entrypoint — includes the generated agent launcher.\n"
                "# Generated by farrier because this repo had\n"
                "# no root Makefile. Safe to extend with your own targets; the\n"
                "# installer will not overwrite a Makefile once it exists.\n"
                f"-include {LAUNCHER_AGENTS_MK}\n"
            )

        return outputs

    def hand_written_tags(self, folder: str) -> tuple[str, ...]:
        """The tags a hand-written skill folder declares in `metadata.tags`, else in `tags`."""
        for rel_dir in self.hand_written_dirs:
            path = self.repo / rel_dir / folder / "SKILL.md"
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                declared = frontmatter_metadata(text).get("tags")
                return tuple(
                    normalize_tags(declared)
                    if declared is not None
                    else frontmatter_tags(text)
                )
        return ()

    def hand_written_folders(self) -> list[str]:
        """Names of the hand-written skill folders in the repo's real skills directories."""
        found: dict[str, None] = {}
        for rel_dir in self.hand_written_dirs:
            root = self.repo / rel_dir
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                skill = child / "SKILL.md"
                if skill.is_file() and not is_generated(skill):
                    found[child.name] = None
        return list(found)

    def hand_written_skill(self, name: str) -> Source | None:
        """The hand-written skill folder in the repo that *name* denotes, or None."""
        folder = name.replace(".", "-")
        for rel_dir in self.hand_written_dirs:
            for candidate in dict.fromkeys((folder, compose_name(self.prefix, folder))):
                rel = f"{rel_dir}/{candidate}/SKILL.md"
                path = self.repo / rel
                if path.is_file():
                    return Source(
                        kind="skill", path=path, rel=rel, id=candidate, local=True
                    )
        return None

    def instruction_skill(self, name: str) -> Source:
        """The skill a localInstructions entry names: a selected library skill, else a hand-written folder."""
        source = self.skill_lookup.get(name.replace(".", "-"))
        if source is not None:
            return source
        source = self.hand_written_skill(name)
        if source is None:
            raise SystemExit(
                f"Unknown selected skill reference: {name} (no selected library "
                "skill and no hand-written skill folder of that name)"
            )
        return source

    def instruction_sources(
        self,
        skill_names: list[str],
        prompt_names: list[str] | None = None,
        policy_names: list[str] | None = None,
    ) -> list[Source]:
        """The files one localInstructions mapping aggregates, in order."""
        return (
            [self.policy_source(name) for name in policy_names or []]
            + [self.instruction_skill(name) for name in skill_names]
            + [self.prompt_source(name) for name in prompt_names or []]
        )

    def policy_bundles(self, names: Sequence[str]) -> dict[Path, Rendered]:
        """Each named policy that bundles scripts, installed under ``.agents/policies``."""
        outputs: dict[Path, Rendered] = {}
        for source in dict.fromkeys(self.policy_source(name) for name in names):
            scripts = [asset for asset in skill_assets(source) if asset.is_script]
            if not scripts:
                continue
            folder = self.repo / POLICY_ROOT / library_name(source)
            head = folder / "POLICY.md"
            _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
            banner = root_banner(library_source_path(source), self.dest_rel(head))
            outputs[head] = Rendered(banner + body.strip() + "\n")
            for asset in scripts:
                outputs[folder / asset.rel] = Rendered(
                    read_asset_text(asset), executable=True, verbatim=True
                )
        return outputs

    def instruction_part(self, source: Source, target: str, output_path: Path) -> str:
        """One source's body as it lands in a generated AGENTS.md."""
        _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        if source.kind == "prompt":
            body = strip_arguments_placeholder(body)
        rendered = self.render_templates(body, target, output_path).strip()
        if source.local:
            rendered = rebase_links(rendered, source.path.parent, output_path.parent)
        return rendered

    def render_local_instruction(
        self,
        skill_names: list[str],
        target: str,
        output_path: Path,
        include_readme: bool = True,
        prompt_names: list[str] | None = None,
        policy_names: list[str] | None = None,
        text: str = "",
    ) -> str:
        """The aggregated AGENTS.md for one localInstructions mapping."""
        parts: list[tuple[str, str]] = []
        for source in self.instruction_sources(skill_names, prompt_names, policy_names):
            part = self.instruction_part(source, target, output_path)
            if part:
                parts.append((library_source_path(source), part))
        local_text = self.render_templates(text, target, output_path).strip()
        if local_text:
            parts.append((LOCAL_TEXT_SOURCE, local_text))
        rendered = "\n\n---\n\n".join(part for _, part in parts)

        readme = output_path.parent / "README.md"
        if include_readme and readme.exists():
            readme_body = self.render_templates(
                readme.read_text(encoding="utf-8"), target, output_path
            )
            rendered = f"{rendered}\n\n## Local README\n\n{readme_body.strip()}\n"
        return Rendered(
            rendered,
            assumed=True,
            sources=tuple(rel for rel, _ in parts),
            parts=tuple(parts),
        )

    def render_claude_pointer(
        self,
        skill_names: list[str],
        output_path: Path,
        prompt_names: list[str] | None = None,
        readme_import: bool = False,
        policy_names: list[str] | None = None,
    ) -> str:
        """The CLAUDE.md that points Claude at the AGENTS.md beside it."""
        sources = self.instruction_sources(skill_names, prompt_names, policy_names)
        dest_rel = output_path.relative_to(self.repo).as_posix()
        banner = local_instruction_banner(sources, dest_rel)
        readme = "\n@README.md\n" if readme_import else ""
        return Rendered(
            f"{banner}@AGENTS.md\n{readme}",
            sources=tuple(library_source_path(source) for source in sources),
        )
