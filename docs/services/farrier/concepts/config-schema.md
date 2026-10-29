---
type: concept
slug: config-schema
title: Config schema
---
# Config schema

One typed model, `HomeConfig` in `stablemate_core`, declares every key of the [home config file](../formats/home-config.md). Each key carries a meaning, an example, a default and, where an environment variable stands in for it, the variable and which of the two wins. The loader validates the file against that model, the resolvers read the validated document, and [`farrier config reference`](../farrier-commands-init.md#config) renders the reference from the same model, so the reference cannot list a key the loader does not know or omit one it does.

The repository's [`agents.yml`](../formats/agents-yml-config.md) is the second document. `Manifest` declares every key farrier reads, and the keys the workflows and ostler read, so none of those raises a stray-key warning. [`farrier config reference --file manifest`](../farrier-commands-init.md#config) renders it. The manifest has no schema version.

- code: `farrier/farrier/_vendor/stablemate_core/schema/home.py::HomeConfig` @074a3b29bddd
- code: `farrier/farrier/_vendor/stablemate_core/schema/reference.py::render_reference` @f6b3e5af64f0
- code: `farrier/farrier/_vendor/stablemate_core/schema/reference.py::select_rows` @96cb06857a53
- code: `farrier/farrier/config_reference.py::reference_text` @145be29b7ae0
- code: `farrier/farrier/_vendor/stablemate_core/config.py::write_config_value` @e0dc8300bbc3
- code: `farrier/farrier/config_reference.py::parse_home_value` @255c4f0b809a
- code: `farrier/farrier/_vendor/stablemate_core/schema/manifest.py::Manifest` @29d985903bcc
- code: `farrier/farrier/_vendor/stablemate_core/manifest.py::load_manifest` @bdf1b65128c6
- rule: the typed schema in `stablemate_core` is the only reader of the machine config; a tool that needs a key reads it from the loaded `HomeConfig` and never parses the TOML itself
- rule: a key the schema does not declare loads anyway and is kept, and the loader logs one warning per process naming the key path and the closest declared key; a file written by a newer release therefore never stops an older tool from reading
- rule: a key the schema does not declare cannot be set, because a setting exists only once it is declared with its meaning, an example and its precedence
- rule: a value of the wrong type fails the load with an error naming the key path, except the few settings whose malformed value has always read as unset, which stay lenient
- rule: a version-1 file that cannot be lifted to the current shape fails the load with `ConfigVersionError` rather than being read in a shape the tool cannot trust; a file under a newer schema version loads with a warning and is refused only at write
- rule: the loader holds the last good document per path, keyed by the file's modification time and size, and trusts the held copy only when it was read more than two seconds after that modification time, so a rewrite that keeps the size and the time within the guard window is read again; a re-read that fails to parse or validate logs a warning naming the key path and returns the last good document, while a first load that fails raises, so an edit made mid-run never ends a run and a broken file never starts one
- rule: a write edits the file in place with a comment-preserving TOML editor, so comments, key order and keys the schema does not declare survive it; the previous file is kept as `<name>.v<N>.bak` when a write lifts it to a newer schema version
- rule: a run that names no profile resolves no model, effort, timeout scale or delegate from the file, except through the profile named after its CLI; a table left at the top level of a version-2 config is never read as a profile
- rule: unparsable TOML fails the load with `ConfigError` like a wrong type does; it no longer reads as an empty config
- rule: the raw-mapping readers are private to `stablemate_core`; a tool that needs a value reads it from `load_home_config` or from a typed resolver, so no tool parses the file or holds a second copy of its shape
- rule: the manifest is `agents.yml` at the repository root; the locator tries `agents.yml` first and then `ostler.yml`, `ostler.yaml` and `.agents.yml`, and a legacy name loads with a warning that names the rename
- rule: the manifest has no schema version; an older shape is lifted by a fold at load time, so no file is ever rewritten to read it
- rule: the loader folds `vars` into `template` with `template` winning, `workflow.github_token_env` into `workflow.githubTokenEnv`, `workflow.services` and `workflow.lint` into the top-level `services` and `lint` with the top level winning, and an `agents:` list of harness names into the table form
- rule: a manifest key no tool declares, a dead key such as `workspace`, is not declared and loads with the stray-key warning; the tables whose keys belong to the library (`template`, `repo`) never report a stray key
- rule: a manifest value of the wrong type fails the first load with an error naming the key path, and a re-read that fails keeps the last good manifest and logs the key path
- rule: farrier, the workflows and ostler read the manifest only through the loaded `Manifest`; its checks of `agents`, `localInstructions`, `scaffolds`, `hooks.manager`, `qa` and `organization` are validators on the model, so no reader parses the manifest YAML itself
- rule: writers that edit `agents.yml` keep its comments and key order; farrier edits the text in place, and the genesis workflow, the one other writer, round-trips the file with `ruamel.yaml`, which only the workflows package depends on
- rule: the coder's per-role prompt bodies live at `workflow.prompts`; a top-level `prompts` mapping is the legacy spelling, which the loader folds into `workflow.prompts` key by key with a warning, so a key only in `workflow.prompts` is kept and a key in both takes the top-level value, so the top-level `prompts` key is the farrier selection list only
- rule: `ostler.yml`, `ostler.yaml` and `.agents.yml` are legacy names of the whole manifest, not of a separate ostler file; `agents.yml` wins when both exist, and ostler reads `organization` and `qa` from whichever file the locator returns
- rule: a workflow or ostler reader stops on a manifest that fails validation with a `ConfigError` naming the key paths, because reading it as absent silently drops settings such as the GitHub token env; a coder turn's role lookup is the exception and falls back to the library prompt with a warning, because a role override only replaces a prompt the library already ships
- rule: `farrier config reference` prints a one-line index of every key by default and the full entries only for a named key and the keys under it, because the full reference of both files runs past a thousand lines and an agent looking up one key should not read every entry; `--full` keeps the whole reference for a reader who wants it
- rule: `farrier config set <key>=<value>` writes one machine-config key by its dotted path and saves only a file that validates and reads the value back as written, because a key no tool declares and a value the schema drops on load both load without error, so a setter that only parsed would report a write no tool sees; the four `set-<dir>` actions stay because they resolve a path to an absolute one and check that a library directory holds `library/`
- rule: `farrier config get <key>` prints the value a key takes after defaults, not only what the file sets, because the question an agent asks is what the tools will use
- rule: a `ConfigError` from a bad machine config or manifest reaching the top of the ostler, groom, paddock or workhorse command prints its message to stderr and exits 2 instead of a traceback; farrier prints it as `error: <message>` through its own handler
- rule: the `groom.attend` settings `mode` and `last_mode` are read in any case and lowercased, and `deny` entries are read as text
- rule: the genesis workflow writes no `workflows` key, because no tool reads it
- detail: [home config](../formats/home-config.md)
- detail: [configuration version guard](config-version-guard.md)
