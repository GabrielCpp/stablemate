"""The ``Renderer`` — stateful rendering of library sources into agent adapters.

Holds the selected skills/prompts and per-repo context, and renders each into the
Codex/Claude/Copilot file layouts, stamping provenance as it goes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined

from farrier.frontmatter import (
    first_heading,
    front_matter_end,
    frontmatter_tags,
    normalize_tags,
    split_front_matter,
)
from farrier.launcher import (
    LAUNCHER_AGENTS_MK,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_CONTEXT_MANIFEST_FMT,
    LAUNCHER_ROOT_MAKEFILE,
    render_agents_mk,
)
from farrier.layers import available_names, find_in_layers
from farrier.naming import relative_reference, repo_prefix, yaml_quote
from farrier.selection_errors import unknown_selection_error
from farrier.sources import (
    Asset,
    Source,
    build_lookup,
    build_policy_lookup,
    library_path,
    library_source_path,
    public_id,
    public_name,
    skill_assets,
)


class Rendered(str):
    """A generated file's text, plus how it must be written.

    The output map is ``path -> text`` everywhere in farrier, and a bundled script is
    still text — it differs only in needing the executable bit and in being copied
    byte-for-byte rather than reformatted. Carrying those two bits on a ``str``
    subclass keeps every existing consumer (comparisons, ``.startswith``, the
    ``--check`` diff) working unchanged, and lets the writer branch where it matters.

    ``sources`` and ``parts`` carry provenance for the files that cannot stamp it into
    themselves. A generated skill names its origin in ``metadata.source`` and needs
    neither; an aggregated AGENTS.md deliberately carries no banner at all, so the only
    thing that knows which library files it was joined from is the renderer that joined
    them. ``parts`` keeps each source's rendered text beside its path, which is what lets
    ``--check`` say *which half* of a two-source aggregate somebody edited.
    """

    executable: bool = False
    verbatim: bool = False
    sources: tuple[str, ...] = ()
    parts: tuple[tuple[str, str], ...] = ()

    def __new__(
        cls,
        text: str,
        *,
        executable: bool = False,
        verbatim: bool = False,
        sources: tuple[str, ...] = (),
        parts: tuple[tuple[str, str], ...] = (),
    ):
        rendered = super().__new__(cls, text)
        rendered.executable = executable
        rendered.verbatim = verbatim
        rendered.sources = sources
        rendered.parts = parts
        return rendered


# A generated skill/command is a *copy* of a library source. Without a marker, an
# agent editing it "fixes" the copy — losing the change on the next `make
# agent-install`. We stamp the single source of truth into a `metadata` front-matter
# field so the edit lands in the library instead. Skills carry it natively (openskill
# format: openskill.sh/docs/creators/skill-format); Claude commands carry the same
# block — the slash-command parser (and claude-code-acp) ignores keys it does not
# recognise, so `metadata` is inert to the agent. Codex/copilot prompts are left
# untouched; aggregated Claude instruction files get an HTML-comment banner instead
# (see local_instruction_banner).
def skill_metadata_block(source: Source, dest_rel: str, tags: list[str] | None = None) -> str:
    """The `metadata:` block stamping a generated skill/command with its source.

    *tags* are the library source's own `tags:`, carried through so the installed copy
    still says what it is *for* — a reader of the generated file sees the same query
    keys `find_by_tags` matches on. They ride inside `metadata:` rather than as a
    top-level key because the front matter of a generated skill is rebuilt from a
    fixed set of keys the harnesses recognise, and `metadata:` is the one already
    agreed to be ours.

    *dest_rel* is the generated file's repo-root-relative path — it makes the
    `resolve:` field a copy-pasteable command that turns the (machine-independent,
    library-anchored) `source:` back into this machine's absolute editable path via
    ``farrier source`` (which reuses the same library resolution as install). The
    header stays portable: no absolute path is baked in, so it is stable across
    machines and under ``--check``.

    Returns the YAML lines (newline-terminated) to splice into the front matter.
    """
    do_not_edit = (
        "generated — run the `resolve` command below for this machine's editable "
        "source path, edit that, then `make agent-install` to regenerate"
    )
    tag_line = f"  tags: [{', '.join(tags)}]\n" if tags else ""
    return (
        "metadata:\n"
        "  generated_by: farrier\n"
        f"  source: {library_source_path(source)}\n"
        f"  resolve: {yaml_quote(f'farrier source {dest_rel}')}\n"
        f"  do_not_edit: {yaml_quote(do_not_edit)}\n"
        f"{tag_line}"
    )


# Aggregated instruction files (localInstructions → CLAUDE.md) cannot carry YAML
# front matter — Claude injects them into context verbatim, so a `metadata:` block
# would read as instructions. Provenance rides in a block-level HTML comment
# instead: Claude strips those before *context injection*, but anyone (human or
# agent) opening the file to edit it sees the comment raw — exactly the audience
# that must be redirected to the library source. Only the claude target gets it;
# other agents do not strip comments.
def local_instruction_banner(sources: list[Source], dest_rel: str) -> str:
    """The DO-NOT-EDIT comment prepended to generated Claude instruction files.

    *dest_rel* is the generated file's repo-root-relative path — like
    skill_metadata_block's `resolve:` field, it makes the banner's resolve line a
    copy-pasteable ``farrier source`` command that turns the library-anchored
    source paths into this machine's absolute editable paths, keeping the banner
    itself portable and stable under ``--check``.
    """
    source_lines = "\n".join(f"  {library_source_path(s)}" for s in sources)
    return (
        "<!--\n"
        "DO NOT EDIT — generated by farrier from the agent library.\n"
        "Edits here are overwritten by `make agent-install` (or: farrier --repo .).\n"
        "Edit the library source(s) instead, then regenerate:\n"
        f"{source_lines}\n"
        f"Editable paths on this machine: `farrier source {dest_rel}`\n"
        "Skill→path mapping: agents.yml → localInstructions\n"
        "-->\n\n"
    )


def asset_banner(asset: Asset, dest_rel: str) -> str:
    """The DO-NOT-EDIT comment prepended to a generated markdown reference.

    A bundled reference is a copy of a library file exactly as a SKILL.md is, and gets
    the same redirect-edits-to-the-library treatment — but it cannot use
    ``skill_metadata_block``: a reference has no front matter of its own, and inventing
    one would change how the file reads to whoever opens it. The HTML comment carries
    the same provenance in the shape ``banner_sources`` already parses, so
    ``farrier source`` resolves a reference like anything else farrier generates. It
    names the *reference's* own library path, not its skill's: the file an editor has
    open is the file they need to be sent to.

    Scripts get no banner: a comment leader that is correct in sh and Python is wrong
    in the next language, and a script's value is that it runs byte-for-byte as written.
    """
    return (
        "<!--\n"
        "DO NOT EDIT — generated by farrier from the agent library.\n"
        "Edits here are overwritten by `make agent-install` (or: farrier --repo .).\n"
        "Edit the library source instead, then regenerate:\n"
        f"  {library_path(asset.path, asset.rel)}\n"
        f"Editable path on this machine: `farrier source {dest_rel}`\n"
        "-->\n\n"
    )


def root_banner(source_rel: str, dest_rel: str) -> str:
    """The DO-NOT-EDIT comment prepended to a generated root instruction file.

    ``.github/copilot-instructions.md`` is a verbatim render of a library root, and
    copilot reads it as plain prose — there is no front matter to stamp it in, so the
    provenance rides in the same HTML comment the aggregated instruction files use.
    Without it the file carries no mark at all, and ownership — which is read off the
    file rather than off its path — would take farrier's own output for somebody's
    hand-written instructions and refuse to install over it.
    """
    return (
        "<!--\n"
        "DO NOT EDIT \u2014 generated by farrier from the agent library.\n"
        "Edits here are overwritten by `make agent-install` (or: farrier --repo .).\n"
        "Edit the library source instead, then regenerate:\n"
        f"  {source_rel}\n"
        f"Editable path on this machine: `farrier source {dest_rel}`\n"
        "-->\n\n"
    )


def with_banner(text: str, banner: str) -> str:
    """*text* with *banner* spliced in after its front matter, or at the very top.

    A root source is prose and normally has no fence, but a banner pushed above one
    would silently demote it to body text — so the split is parsed, not assumed.
    """
    at = front_matter_end(text)
    if at == 0:
        return banner + text
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rest = "\n".join(lines[at:]).removeprefix("\n")
    return "\n".join(lines[:at]) + "\n" + banner + rest


def read_asset_text(asset: Asset) -> str:
    """A bundled asset's text, with a decodable error message when it is not text.

    The output pipeline is a ``path -> text`` map end to end (rendering, ``--check``
    diffing, writing), so a binary asset cannot ride through it. Failing here names the
    offending file; letting it reach ``read_text`` raises a UnicodeDecodeError that
    names only the codec.
    """
    try:
        return asset.path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            f"error: bundled asset {asset.path} is not UTF-8 text. Skill assets are "
            "rendered and diffed as text; keep binaries out of references/ and "
            "scripts/ (fetch or generate them at run time instead)."
        ) from exc


def strip_arguments_placeholder(body: str) -> str:
    """Drop a command's ``$ARGUMENTS`` line when its body is aggregated instead.

    The placeholder is substituted by the slash-command invocation and by nothing
    else, so a prompt folded into an always-loaded instruction file would carry a
    bare ``$ARGUMENTS`` into every session — read by the agent as text, not as the
    hole it is. Only a line that is exactly the placeholder is removed; one used
    inline (``run X on $ARGUMENTS``) is left alone, since deleting the line around
    it would take a sentence with it.
    """
    lines = [line for line in body.splitlines() if line.strip() != "$ARGUMENTS"]
    return "\n".join(lines)


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
    ):
        self.repo = repo
        self.prefix = prefix
        self.repo_context = dict(repo_config)
        # Assigned, not `setdefault`: both are derived from the directory now, and a
        # `repo.name` left over in someone's agents.yml must not shadow the name the
        # rest of the toolchain (the workflow kit, the run record, a `.code-workspace`
        # folder entry) reads off the checkout itself.
        self.repo_context["name"] = repo_prefix(repo)
        self.repo_context["prefix"] = prefix
        self.repo_context["root"] = repo.as_posix()
        self.template_values = template_values
        self.skills = skills
        self.prompts = prompts
        self.skill_lookup = build_lookup(skills, prefix)
        self.prompt_lookup = build_lookup(prompts, prefix)
        # Every policy in the library, not a selected subset: a policy has no top-level
        # selection key, because binding one into a localInstructions mapping is the only
        # thing that brings it into a repo at all. `policy_lookup` is read by
        # `instruction_sources` and by nothing else — see `policy_source`.
        self.policies = list(policies or [])
        self.policy_lookup = build_policy_lookup(self.policies)
        self._tags: dict[Path, list[str]] = {}

    def skill_tags(self, source: Source) -> list[str]:
        """The `tags:` a library skill declares. Cached — one read per source file.

        A tag is what lets a prompt ask for a *capability* ("this repo's web testing
        conventions") rather than enumerate the skills that might provide one. The
        enumeration is the thing being replaced: a prompt listing `react-router-qa`,
        `flutter-testing`, `go-testing` is naming today's stacks, and a repo whose
        stack the workflow has never met gets nothing.
        """
        cached = self._tags.get(source.path)
        if cached is None:
            cached = frontmatter_tags(source.path.read_text(encoding="utf-8"))
            self._tags[source.path] = cached
        return cached

    def skills_with_tags(self, tags: list[str]) -> list[Source]:
        """The selected skills carrying **all** of *tags*, in library order.

        AND, not OR: ``('web', 'tests')`` means the skills that are both, so a
        second word narrows the query rather than widening it. An empty *tags*
        matches nothing — an unconstrained query would otherwise answer with the
        repo's entire installed library.
        """
        wanted = set(tags)
        if not wanted:
            return []
        return [s for s in self.skills if wanted <= set(self.skill_tags(s))]

    def skill_source(self, name: str) -> Source:
        source = self.optional_skill_source(name)
        if source is None:
            raise SystemExit(f"Unknown selected skill reference: {name}")
        return source

    def optional_skill_source(self, name: str) -> Source | None:
        key = name.replace(".", "-")
        source = self.skill_lookup.get(key)
        if source is None and self.prefix and not key.startswith(f"{self.prefix}-"):
            # A repo-prefixed overlay skill (e.g. acme-developer) stays
            # addressable by its generic name ("developer") so shared workflow
            # prompts can reference the repo's overlay without knowing the repo.
            source = self.skill_lookup.get(f"{self.prefix}-{key}")
        return source

    def policy_source(self, name: str) -> Source:
        """The library file a ``policies:`` entry names, or exit.

        No prefix fallback and no optional variant, unlike skills and prompts: a policy
        is reachable only from a localInstructions mapping, so there is no template
        helper that has to degrade gracefully when one is absent. A name that resolves
        to nothing is a config typo, and the file it was meant to put in every turn's
        context would otherwise just be missing from it.
        """
        key = name.replace(".", "-")
        source = self.policy_lookup.get(key)
        if source is None:
            available = sorted({public_id(s) for s in self.policies})
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

    def optional_prompt_source(self, name: str) -> Source | None:
        return self.prompt_lookup.get(name.replace(".", "-"))

    def skill_output_path(self, name: str, target: str) -> Path:
        source = self.skill_source(name)
        generated = public_name(self.prefix, source)
        if target == "copilot":
            return self.repo / ".github" / "skills" / generated / "SKILL.md"
        if target == "codex":
            return self.repo / ".agents" / "skills" / generated / "SKILL.md"
        if target == "claude":
            return self.repo / ".claude" / "skills" / generated / "SKILL.md"
        raise SystemExit(f"Unknown skill render target: {target}")

    def prompt_output_path(self, name: str, target: str) -> Path:
        source = self.prompt_source(name)
        generated = public_name(self.prefix, source)
        if target == "copilot":
            return self.repo / ".github" / "prompts" / f"{generated}.prompt.md"
        if target == "codex":
            return self.repo / ".agents" / "prompts" / f"{generated}.prompt.md"
        if target == "claude":
            return self.repo / ".claude" / "commands" / f"{generated}.md"
        raise SystemExit(f"Unknown prompt render target: {target}")

    def skill_dir_path(self, target: str) -> Path:
        if target == "copilot":
            return self.repo / ".github" / "skills"
        if target == "codex":
            return self.repo / ".agents" / "skills"
        if target == "claude":
            return self.repo / ".claude" / "skills"
        raise SystemExit(f"Unknown skill dir target: {target}")

    def render_templates(self, content: str, target: str, from_file: Path) -> str:
        # Rendering is skipped for content that names no helper — most library files are
        # plain markdown and paying Jinja for them means every `{{ }}` in a code sample
        # becomes a syntax error. `{%` has to open the gate too: it is how an author says
        # "this IS a template", and `{% raw %}` in particular is the *only* way to protect
        # a literal `{{ }}`. Skipping a file that uses it would leak the tags into the
        # output verbatim — the opposite of what the author asked for.
        if not any(
            token in content
            for token in [
                "{%",
                "instruction_file(",
                "instruction_ref(",
                "skill_file(",
                "prompt_file(",
                "prompt_ref(",
                "find_by_tags(",
                "skill_dir(",
                "isUsingInstruction(",
                "repo.",
                "template.",
                "vars.",
            ]
        ):
            return content
        env = Environment(autoescape=False, undefined=StrictUndefined)
        template = env.from_string(content)

        def instruction_ref(name: str) -> str:
            if self.optional_skill_source(name):
                return relative_reference(
                    from_file, self.skill_output_path(name, target)
                )
            return f"generated {name} instruction file when installed"

        def prompt_ref(name: str) -> str:
            if self.optional_prompt_source(name):
                return relative_reference(
                    from_file, self.prompt_output_path(name, target)
                )
            return f"generated {name} prompt when installed"

        def skill_file(name: str) -> str:
            if self.optional_skill_source(name):
                return relative_reference(
                    from_file, self.skill_output_path(name, target)
                )
            return f"generated {name} skill when installed"

        def prompt_file_fn(name: str) -> str:
            if self.optional_prompt_source(name):
                return relative_reference(
                    from_file, self.prompt_output_path(name, target)
                )
            return f"generated {name} prompt when installed"

        def is_using_instruction(instruction_name: str) -> bool:
            """Check if this project has a specific instruction selected."""
            return self.optional_skill_source(instruction_name) is not None

        def find_by_tags(*tags: str) -> str:
            """The installed skills tagged with all of *tags*, as a reference list.

            The install-time half of workhorse's Jinja global of the same name, and it
            must render the same shape — backticked paths, comma-joined, empty when
            nothing matches — so a library source reads identically whether farrier
            rendered it into a repo or workhorse rendered it from the library.
            """
            wanted = normalize_tags(list(tags))
            refs = sorted(
                relative_reference(
                    from_file, self.skill_output_path(source.id, target)
                )
                for source in self.skills_with_tags(wanted)
            )
            return ", ".join(f"`{ref}`" for ref in refs)

        def workhorse_var(name: str) -> str:
            """Emit a runtime variable reference that workhorse will fill at run time.
            Usage in templates: {{ workhorse_var('plan_path') }}
            Output in installed file: {{ plan_path }}"""
            return "{{ " + name + " }}"

        return template.render(
            instruction_file=lambda name: (
                relative_reference(
                    from_file, self.skill_output_path(name, target)
                )
                if self.optional_skill_source(name)
                else f"generated {name} instruction file when installed"
            ),
            instruction_ref=instruction_ref,
            skill_file=skill_file,
            prompt_file=prompt_file_fn,
            prompt_ref=prompt_ref,
            skill_dir=lambda: relative_reference(
                from_file, self.skill_dir_path(target)
            ),
            isUsingInstruction=is_using_instruction,
            find_by_tags=find_by_tags,
            workhorse_var=workhorse_var,
            repo=self.repo_context,
            template=self.template_values,
            vars=self.template_values,
            target=target,
        )

    def context_manifest(self, target: str) -> dict[str, Any]:
        """Per-repo manifest consumed by workhorse at run time (see workhorse/templates.py).

        Workflows now run **directly from the library** — they are never copied or
        rendered into a repo. This manifest captures exactly what the install-time
        template helpers used to resolve (``instruction_ref``/``isUsingInstruction``/
        ``template.*``/``skill_dir``), so the library-resident prompts render at run
        time. All paths are **repo-root-relative** because the agent runs with its
        working directory at the repo root (``AGENT_REPO_DIR``).
        """
        def rel(path: Path) -> str:
            return path.relative_to(self.repo).as_posix()

        instructions = {
            key: rel(self.skill_output_path(source.id, target))
            for key, source in self.skill_lookup.items()
        }
        prompts = {
            key: rel(self.prompt_output_path(source.id, target))
            for key, source in self.prompt_lookup.items()
        }
        # Keyed by the same alias names as `instructions`, so a tag query resolves a
        # matched name through the same lookup a `instruction_ref` would. Untagged
        # skills are simply absent: a name with no tags can never match a query, and
        # writing `[]` for each of a skill's several aliases would triple the file
        # to say nothing.
        instruction_tags = {
            key: tags
            for key, source in self.skill_lookup.items()
            if (tags := self.skill_tags(source))
        }
        # The manifest is a committed adapter consumed at run time with the working
        # directory AT the repo root, so pin repo.root to "." — keeping the install
        # machine's absolute path out of version control (avoids cross-machine drift).
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

    def generated_skill(self, source: Source, target: str, output_path: Path) -> str:
        header, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        header = {
            key: self.render_templates(value, target, output_path)
            for key, value in header.items()
        }
        body = self.render_templates(body, target, output_path).strip()
        name = public_name(self.prefix, source)
        description = self.skill_description(source, header, body)
        dest_rel = output_path.relative_to(self.repo).as_posix()
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {yaml_quote(description)}\n"
            f"{skill_metadata_block(source, dest_rel, self.skill_tags(source))}"
            "---\n"
            "\n"
            f"{body}\n"
        )

    def generated_assets(
        self, source: Source, target: str, skill_path: Path
    ) -> dict[Path, Rendered]:
        """The files bundled with *source*, keyed by where they install.

        Each lands beside the generated SKILL.md at the same relative path it has in the
        library (``references/api.md`` → ``<skill>/references/api.md``), which is what
        lets a library author link one with the path they see on disk and have it
        resolve identically under every adapter.

        Markdown references are rendered like a skill body — the same ``instruction_file``
        / ``repo.*`` helpers, resolved from the *reference's* own location so relative
        links point where they should. Everything else is copied through untouched:
        a script or a JSON fixture means whatever its bytes say, and a stray ``{{`` in
        one is far more likely to be its own syntax than a farrier template.
        """
        if skill_path.name != "SKILL.md":
            # Assets are addressed relative to their skill's directory. A flat adapter
            # layout has no such directory, so every skill's assets would land in one
            # shared folder and the last one rendered would win.
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
            dest_rel = output_path.relative_to(self.repo).as_posix()
            body = self.render_templates(text, target, output_path).strip()
            outputs[output_path] = Rendered(asset_banner(asset, dest_rel) + body + "\n")
        return outputs

    def command_description(
        self, source: Source, header: dict[str, str], body: str
    ) -> str:
        """The `description` for a generated Claude command's front matter.

        Prefer an explicit library `description:`; otherwise fall back to the body's
        first heading (what shows in claude-code-acp's slash-command menu). This is
        the prompt analogue of ``skill_description``.
        """
        if header.get("description"):
            return header["description"]
        return first_heading(body, public_name(self.prefix, source))

    def generated_command(self, source: Source, target: str, output_path: Path) -> str:
        """Render a library prompt into a Claude slash command WITH front matter.

        Without a `description` in the front matter, claude-code-acp has nothing to
        advertise over ACP and the command never appears in Zed's autocomplete. So,
        like ``generated_skill``, we emit a header carrying the slash-command keys the
        parser recognises (description / argument-hint / model / allowed-tools) plus
        the same `metadata:` provenance block skills get. Farrier-internal keys
        (`agent`, `name`) are intentionally dropped: the command name comes from the
        filename, and `agent` only selected the backend at render time.
        """
        header, body = split_front_matter(source.path.read_text(encoding="utf-8"))
        header = {
            key: self.render_templates(value, target, output_path)
            for key, value in header.items()
        }
        body = self.render_templates(body, target, output_path).strip()
        lines = [
            "---",
            f"description: {yaml_quote(self.command_description(source, header, body))}",
        ]
        # Pass through the optional slash-command keys when the library author set
        # them (accepting both kebab and camelCase spellings in the source).
        for key, aliases in (
            ("argument-hint", ("argument-hint", "argumentHint")),
            ("model", ("model",)),
            ("allowed-tools", ("allowed-tools", "allowedTools")),
        ):
            value = next((header[a] for a in aliases if header.get(a)), None)
            if value:
                lines.append(f"{key}: {yaml_quote(value)}")
        dest_rel = output_path.relative_to(self.repo).as_posix()
        lines.append(
            skill_metadata_block(source, dest_rel, self.skill_tags(source)).rstrip("\n")
        )
        lines.append("---")
        return "\n".join(lines) + "\n\n" + f"{body}\n"

    def render(
        self,
        agents: dict[str, bool],
        roots: set[str],
    ) -> dict[Path, str]:
        outputs: dict[Path, str] = {}

        def render_skills(target: str) -> None:
            """Every selected skill into *target*, each with its bundled assets."""
            for source in self.skills:
                output_path = self.skill_output_path(source.id, target)
                outputs[output_path] = self.generated_skill(source, target, output_path)
                outputs.update(self.generated_assets(source, target, output_path))

        if agents.get("copilot"):
            render_skills("copilot")

            for source in self.prompts:
                output_path = self.prompt_output_path(source.id, "copilot")
                content = self.render_templates(
                    source.path.read_text(encoding="utf-8"), "copilot", output_path
                )
                outputs[output_path] = content

            for root in roots:
                # Presence was validated up front (see the roots check below), so a miss
                # here cannot happen silently; keep the guard for the tests-built Renderer.
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
            for source in self.prompts:
                output_path = self.prompt_output_path(source.id, "codex")
                content = self.render_templates(
                    source.path.read_text(encoding="utf-8"), "codex", output_path
                )
                outputs[output_path] = content

        if agents.get("claude"):
            render_skills("claude")
            for source in self.prompts:
                output_path = self.prompt_output_path(source.id, "claude")
                outputs[output_path] = self.generated_command(
                    source, "claude", output_path
                )

        # Roots render only into the copilot adapter, so an
        # unknown one used to be skipped in silence — and on a repo with copilot disabled it
        # was never even looked at. Validate unconditionally: the declaration is wrong
        # regardless of which assistants happen to be enabled, and finding that out only
        # after switching assistants on is the kind of delayed surprise this check exists
        # to prevent.
        unknown_roots = sorted(
            root for root in roots
            if find_in_layers("library", "roots", f"{root}.md") is None
        )
        if unknown_roots:
            raise SystemExit(
                unknown_selection_error(
                    "roots",
                    unknown_roots,
                    available_names("library", "roots", suffix=".md"),
                    extra=(
                        "Roots render only into the copilot adapter, but the name is "
                        "validated whether or not copilot is enabled — otherwise a bad "
                        "declaration stays dormant until someone switches copilot on."
                    ),
                )
            )

        # The launcher (.agents/agents.mk) is generated for EVERY repo: its
        # agent-install/agent-check targets are what keep the adapters current, and
        # a root Makefile can then include it unconditionally.
        outputs[self.repo / LAUNCHER_AGENTS_MK] = render_agents_mk()

        # The per-repo context manifest maps instruction_ref -> the adapter paths
        # rendered above, so it is emitted for every install: a workflow run reads
        # it to resolve skills against THIS repo, and it is farrier's output whether
        # or not any workflow is installed here.
        #
        # Emit one manifest per ENABLED assistant so a run can target the matching
        # adapters (instruction_ref -> .claude/skills, .github/skills, …). AGENT_CLI
        # selects which at run time (workhorse auto-detects from AGENT_REPO_DIR).
        enabled_assistants = [t for t in ("claude", "codex", "copilot") if agents.get(t)]
        # The primary (first enabled) assistant also backs the generic manifest,
        # for back-compat and workhorse's AGENT_CLI-agnostic auto-detect default.
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

        # Only emit a thin root Makefile when the repo has none — never clobber a
        # user-authored Makefile. When one already exists, the generated launcher
        # is wired into it instead via ensure_makefile_include() at install time
        # (an idempotent include block), so its agent targets are reachable either
        # way.
        root_makefile = self.repo / LAUNCHER_ROOT_MAKEFILE
        if not root_makefile.exists():
            outputs[root_makefile] = (
                "# Thin entrypoint — includes the generated agent launcher.\n"
                "# Generated by farrier because this repo had\n"
                "# no root Makefile. Safe to extend with your own targets; the\n"
                "# installer will not overwrite a Makefile once it exists.\n"
                f"include {LAUNCHER_AGENTS_MK}\n"
            )

        return outputs

    def instruction_sources(
        self,
        skill_names: list[str],
        prompt_names: list[str] | None = None,
        policy_names: list[str] | None = None,
    ) -> list[Source]:
        """The library files one localInstructions mapping aggregates, in order.

        Policies, then skills, then prompts — standing rules before the procedures that
        run under them. The argument order is the historical one (skills first) so the
        callers that predate policies keep working; the *return* order is the aggregation
        order, and it is defined here alone so the rendered file and the provenance the
        pointer carries cannot disagree about it.
        """
        return (
            [self.policy_source(name) for name in policy_names or []]
            + [self.skill_source(name) for name in skill_names]
            + [self.prompt_source(name) for name in prompt_names or []]
        )

    def render_local_instruction(
        self,
        skill_names: list[str],
        target: str,
        output_path: Path,
        include_readme: bool = True,
        prompt_names: list[str] | None = None,
        policy_names: list[str] | None = None,
    ) -> str:
        """The aggregated AGENTS.md for one localInstructions mapping.

        Policies first, then skills, then prompts — each body stripped of its
        front matter and joined by a `---` rule. A prompt is included for the
        repos that want a procedure always in context rather than invoked as a
        slash command; it is the same library file the command renders from, so
        neither copy drifts. A prompt's `$ARGUMENTS` placeholder is dropped on
        the way in: nothing substitutes it outside a slash-command invocation,
        so aggregated it is a literal dollar sign in every session's context.

        The file carries no provenance banner at all. Every harness reads
        AGENTS.md, and only Claude strips block-level HTML comments before
        loading — so a "generated, do not edit" line here is not installer
        trivia the others merely pay for, it is an *instruction* sitting in an
        always-loaded rules file, where an agent can just as easily read it as
        governing the repo it is about to edit. The banner lives in the CLAUDE.md
        pointer instead — `render_claude_pointer` — and `farrier source
        AGENTS.md` answers the same question from either file.
        """
        parts: list[tuple[str, str]] = []
        for source in self.instruction_sources(skill_names, prompt_names, policy_names):
            _, body = split_front_matter(source.path.read_text(encoding="utf-8"))
            if source.kind == "prompt":
                body = strip_arguments_placeholder(body)
            part = self.render_templates(body, target, output_path).strip()
            if part:
                parts.append((library_source_path(source), part))
        rendered = "\n\n---\n\n".join(part for _, part in parts)

        readme = output_path.parent / "README.md"
        if include_readme and readme.exists():
            readme_body = self.render_templates(
                readme.read_text(encoding="utf-8"), target, output_path
            )
            rendered = f"{rendered}\n\n## Local README\n\n{readme_body.strip()}\n"
        # The provenance travels with the text because this file, alone among the
        # generated ones, carries none of its own — see Rendered.
        return Rendered(
            rendered,
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
        """The CLAUDE.md that points Claude at the AGENTS.md beside it.

        Claude Code loads CLAUDE.md, every other harness loads AGENTS.md, and one
        aggregated body should not be written twice — so this file is a two-line
        `@` import of the real one. The provenance banner rides here because
        Claude strips block-level HTML comments before loading, making it free
        exactly where it is read, and because this is the file whose whole
        content is machine-written and worth a warning.

        `readme_import` pulls the sibling README in by reference instead of by
        copy; the caller passes it only when Claude is the sole adapter, since
        otherwise the README body is already inside the AGENTS.md this imports.
        """
        sources = self.instruction_sources(skill_names, prompt_names, policy_names)
        dest_rel = output_path.relative_to(self.repo).as_posix()
        banner = local_instruction_banner(sources, dest_rel)
        readme = "\n@README.md\n" if readme_import else ""
        # No `parts`: the body is two lines of pointer, so there is nothing to attribute
        # a drift to beyond the source list the banner already carries.
        return Rendered(
            f"{banner}@AGENTS.md\n{readme}",
            sources=tuple(library_source_path(source) for source in sources),
        )
