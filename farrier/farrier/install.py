#!/usr/bin/env python3
"""farrier — render the agent prompt library into a repository.

Compatibility facade. The implementation was split by capability into cohesive
modules (see each for detail):

  - ``config``     — home-config TOML persistence
  - ``layers``     — base/overlay discovery and the resolution stack
  - ``git``        — repo remote/branch queries
  - ``naming``     — pure name/id transforms
  - ``frontmatter``— YAML front-matter and metadata parsing
  - ``sources``    — the ``Source`` record, loading, selection, packs
  - ``launcher``   — ``.agents/`` launcher generation
  - ``workflows``  — workflow meta, dependency extraction, file headers
  - ``renderer``   — the ``Renderer`` class
  - ``outputs``    — full-render orchestration and repo mutations
  - ``scaffolds``  — ``farrier scaffold`` definitions and fetching
  - ``cli``        — argument parsing and command dispatch

This module re-exports the historical public API so ``farrier.install:main`` (the
console-script entry point) and ``from farrier.install import ...`` keep resolving.
New code should import from the capability modules directly.
"""

from __future__ import annotations

from farrier.cli import (
    find_agents_config,
    main,
    mapped_instruction_sources,
)
from stablemate_core.config import (
    config_path,
    read_config,
    resolve_stablemate_dir,
    write_base_dir,
    write_library_dir,
    write_stablemate_dir,
)
from farrier.frontmatter import (
    banner_sources,
    first_heading,
    frontmatter_metadata,
    mapping_skill_names,
    read_yaml,
    split_front_matter,
)
from farrier.git import get_default_branch, get_git_remote
from farrier.launcher import (
    DEFAULT_AGENTS_DIR,
    DEFAULT_STABLEMATE_DIR,
    LAUNCHER_AGENTS_MK,
    LAUNCHER_COMPOSE,
    LAUNCHER_CONTEXT_MANIFEST,
    LAUNCHER_CONTEXT_MANIFEST_FMT,
    LAUNCHER_ROOT_MAKEFILE,
    render_agents_mk,
    render_local_compose,
)
from farrier.layers import (
    BASE_DIR_ENV,
    BASE_LAYER_NAME,
    LAYERS,
    Layer,
    base_library_dir,
    find_in_layers,
    is_library_dir,
    layer_dirs,
    resolve_library_dir,
    searched_layers,
    set_layers,
)
from farrier.naming import (
    kebab,
    normalize_pattern,
    relative_reference,
    source_id,
    strip_known_suffix,
    yaml_quote,
)
from farrier.outputs import (
    AGENTS_GITIGNORE_BLOCK,
    MAKEFILE_INCLUDE_END,
    MAKEFILE_INCLUDE_MARKER,
    TARGET_DIRS,
    check_outputs,
    ensure_agents_gitignore,
    ensure_gitignore_entry,
    ensure_makefile_include,
    install_outputs,
    normalize_agents,
    remove_targets,
    render_expected,
    write_text,
)
from farrier.renderer import (
    Renderer,
    local_instruction_banner,
    skill_metadata_block,
)
from farrier.scaffolds import (
    SCAFFOLD_TREE_FILE_KEYS,
    available_scaffold_ids,
    fetch_scaffold_url,
    flatten_scaffold_tree,
    load_scaffold_defs,
    parse_param_overrides,
    resolve_scaffold_params,
    substitute_scaffold_path,
)
from farrier.sources import (
    Source,
    build_lookup,
    collect_selection,
    library_source_path,
    load_layered_sources,
    load_pack,
    load_sources,
    matches,
    public_id,
    public_name,
    parse_scaffold_ids,
    selected_sources,
)
from farrier.workflows import (
    WORKFLOW_SKIP_PARTS,
    collect_template_values,
    extract_workflow_dependencies,
    resolve_workflow_meta,
    should_skip_workflow_file,
)

__all__ = [
    "AGENTS_GITIGNORE_BLOCK",
    "BASE_DIR_ENV",
    "BASE_LAYER_NAME",
    "config_path",
    "DEFAULT_AGENTS_DIR",
    "DEFAULT_STABLEMATE_DIR",
    "LAUNCHER_AGENTS_MK",
    "LAUNCHER_COMPOSE",
    "LAUNCHER_CONTEXT_MANIFEST",
    "LAUNCHER_CONTEXT_MANIFEST_FMT",
    "LAUNCHER_ROOT_MAKEFILE",
    "LAYERS",
    "Layer",
    "MAKEFILE_INCLUDE_END",
    "MAKEFILE_INCLUDE_MARKER",
    "Renderer",
    "SCAFFOLD_TREE_FILE_KEYS",
    "Source",
    "TARGET_DIRS",
    "WORKFLOW_SKIP_PARTS",
    "available_scaffold_ids",
    "banner_sources",
    "base_library_dir",
    "build_lookup",
    "check_outputs",
    "collect_selection",
    "collect_template_values",
    "ensure_agents_gitignore",
    "ensure_gitignore_entry",
    "ensure_makefile_include",
    "extract_workflow_dependencies",
    "fetch_scaffold_url",
    "find_agents_config",
    "find_in_layers",
    "first_heading",
    "flatten_scaffold_tree",
    "frontmatter_metadata",
    "get_default_branch",
    "get_git_remote",
    "install_outputs",
    "is_library_dir",
    "kebab",
    "layer_dirs",
    "library_source_path",
    "load_layered_sources",
    "load_pack",
    "load_scaffold_defs",
    "load_sources",
    "local_instruction_banner",
    "main",
    "mapped_instruction_sources",
    "mapping_skill_names",
    "matches",
    "normalize_agents",
    "normalize_pattern",
    "parse_param_overrides",
    "parse_scaffold_ids",
    "public_id",
    "public_name",
    "read_config",
    "read_yaml",
    "relative_reference",
    "remove_targets",
    "render_agents_mk",
    "render_expected",
    "render_local_compose",
    "resolve_library_dir",
    "resolve_scaffold_params",
    "resolve_stablemate_dir",
    "resolve_workflow_meta",
    "searched_layers",
    "selected_sources",
    "set_layers",
    "should_skip_workflow_file",
    "skill_metadata_block",
    "source_id",
    "split_front_matter",
    "strip_known_suffix",
    "substitute_scaffold_path",
    "write_base_dir",
    "write_library_dir",
    "write_stablemate_dir",
    "write_text",
    "yaml_quote",
]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
