# Changelog

## [8.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v7.0.0...farrier-v8.0.0) (2026-11-27)


### ⚠ BREAKING CHANGES

* **farrier:** agents.<harness>.skills_from is refused on every harness but claude, and claude may only name codex, antigravity or pi. Write codex: true and claude: {skills_from: codex} instead.

### Features

* **base-library:** ship the groom MCP record ([a30a004](https://github.com/GabrielCpp/stablemate/commit/a30a004b6549db3b31cb17e55a99cd54121b5f1e))
* **core:** add the per-user farrier state dir helper ([16bcf6f](https://github.com/GabrielCpp/stablemate/commit/16bcf6fc23f33bd614222e0e7d9e793bdc3915b5))
* **core:** expand environment variables in home config paths ([5060f82](https://github.com/GabrielCpp/stablemate/commit/5060f824957d2b65240548686dc3fbf7898573af))
* **farrier:** build an Antigravity plugin with every stablemate tool ([37d3bb1](https://github.com/GabrielCpp/stablemate/commit/37d3bb1dd9ef1b34b6d6c73bb91b14d49c40c3c5))
* **farrier:** drive Antigravity from the plugin's workhorse launchers ([228b3af](https://github.com/GabrielCpp/stablemate/commit/228b3af4a65569f172d36b4d3d10e70c268dc181))
* **farrier:** land codex repo prompts as name-only skills ([4b9f044](https://github.com/GabrielCpp/stablemate/commit/4b9f044bb92af8fa696416abe158b6734c12d647))
* **farrier:** land prompts as name-only skills where no prompt folder ([1cfc1fb](https://github.com/GabrielCpp/stablemate/commit/1cfc1fb66a55856e87f7dbd58a76d55275fdc4e1))
* **farrier:** link only claude skills, to .agents/skills ([339e627](https://github.com/GabrielCpp/stablemate/commit/339e6274401fe51048f412d03f3b871b01787a69))
* **farrier:** print where the home config lives with config path ([2f3b33b](https://github.com/GabrielCpp/stablemate/commit/2f3b33b2782d02bd6a47b42d5001e4bf7d8b732a))
* **workhorse:** run workflow turns on Antigravity ([64e2094](https://github.com/GabrielCpp/stablemate/commit/64e2094c76d9dcc5810fc0c954180367175b9f90))


### Bug Fixes

* **base-library:** link ostler-book references from the skill page ([f2b4009](https://github.com/GabrielCpp/stablemate/commit/f2b40099f498608a97a48b316eaae9dec3ff69be))
* **farrier:** give Antigravity agents its own tools and delegation ([2a493e4](https://github.com/GabrielCpp/stablemate/commit/2a493e4d42826b91d297f682b0224df8aaf678d6))
* **farrier:** leave dot files and folders out of a guard install ([3441e44](https://github.com/GabrielCpp/stablemate/commit/3441e4479516be3a33abbda30bd4225ca381ea34))
* **farrier:** make guards bite in Antigravity ([0c9a48c](https://github.com/GabrielCpp/stablemate/commit/0c9a48cb056149da9277cf60bfb238191c86f58d))
* **farrier:** name the stablemate config in user library errors ([a1dfb69](https://github.com/GabrielCpp/stablemate/commit/a1dfb691729c089590e0611d0177309d5058ea6f))
* **farrier:** restamp the vendored base-library digest ([5916429](https://github.com/GabrielCpp/stablemate/commit/59164290a5f93394edf47d87a18cbd57140a6bed))
* **farrier:** stamp the library copy with the worked example in it ([08756c1](https://github.com/GabrielCpp/stablemate/commit/08756c11c2af9fa7b8048a203df65f8fb51d8cca))
* **farrier:** stop config get claiming an unset key has no default ([5007150](https://github.com/GabrielCpp/stablemate/commit/5007150c7b10c04c0699bf5a2c70ad3102c82786))


### Code Refactoring

* **base-library:** split three skills under agy's 24 KB read ([e979125](https://github.com/GabrielCpp/stablemate/commit/e97912599d3e8c27a30c63bc2e4eaf02897b3f70))
* **farrier:** bring home_guards back under its length ceiling ([22dffcc](https://github.com/GabrielCpp/stablemate/commit/22dffcc10491faca27a1e934862c7ea0e342b1ee))
* **farrier:** keep generated machine state out of .agents ([350f01f](https://github.com/GabrielCpp/stablemate/commit/350f01f7f24c71510a01cbc02c66977c72d8ce55))
* **farrier:** leave the Antigravity plugin to the library ([32ca058](https://github.com/GabrielCpp/stablemate/commit/32ca058b4770ca53fca0d191e7ed70a52a2e127d))
* **farrier:** stop writing the agents-context manifests ([7769eb1](https://github.com/GabrielCpp/stablemate/commit/7769eb1cd896acd9babc6bb404d1992b584417db))
* **workhorse:** read the render context from agents.yml ([5d9a397](https://github.com/GabrielCpp/stablemate/commit/5d9a397817e87492e0ae957c1eee77332db0ef58))

## [7.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v6.1.0...farrier-v7.0.0) (2026-11-25)


### ⚠ BREAKING CHANGES

* **workhorse:** workhorse no longer runs turns through cline. A profile or dispatch that names it is refused.

### Features

* **core:** add the harness registry and tie each harness table to it ([5659cdf](https://github.com/GabrielCpp/stablemate/commit/5659cdf6812b3bf37db18321866e40f5c01c93ed))
* **farrier:** add antigravity as a render-only harness ([96cff2c](https://github.com/GabrielCpp/stablemate/commit/96cff2c4974bb1c353f4e266825161a842b3dd56))
* **farrier:** render a shared skill folder once per harness group ([bd90259](https://github.com/GabrielCpp/stablemate/commit/bd902591a43f77604e272a007575fcc7e0efd9c5))
* **workhorse:** add pi as a harness and backend ([73ee80c](https://github.com/GabrielCpp/stablemate/commit/73ee80c9aa2e1dc1d7f7bd864d919a6c1a8af20d))
* **workhorse:** derive backends from the registry, load opencode dirs ([be5476d](https://github.com/GabrielCpp/stablemate/commit/be5476dc851bfc5ab39bebe4eaf36b14ddf8b6bc))
* **workhorse:** retire the cline backend ([12f2df4](https://github.com/GabrielCpp/stablemate/commit/12f2df4040c5ff777778bfc4fb5cfa0b5fb80f85))


### Code Refactoring

* **core:** split value coercers and QA tables out of the schema ([4958775](https://github.com/GabrielCpp/stablemate/commit/49587753f991deeaa53371ac93ff6bed1d829982))
* **farrier:** derive harness lists and paths from the registry ([5649bed](https://github.com/GabrielCpp/stablemate/commit/5649bedd0f505c58b0e67ad619108ba02de8d20c))
* **farrier:** split mcp servers, install scopes and banners out ([d9c6e58](https://github.com/GabrielCpp/stablemate/commit/d9c6e58549907e0e8c2bdd36f5b81409d6cb86dd))

## [6.1.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v6.0.0...farrier-v6.1.0) (2026-11-25)


### Features

* **core:** add a portable pid_alive and pid_start_token ([27131bf](https://github.com/GabrielCpp/stablemate/commit/27131bf10221a51c60eea6a78d978a91aabb0a65))


### Bug Fixes

* **core:** find a book when the artifacts dir is a linked worktree ([3c341dd](https://github.com/GabrielCpp/stablemate/commit/3c341dd8944fbe0c31e469256b3acb0cc5650835))
* **farrier:** ignore bytecode caches in owned script directories ([44b973a](https://github.com/GabrielCpp/stablemate/commit/44b973a2a4bc92a73dedcb158043de151346f037))
* **farrier:** stamp the current base-library digest ([4c36ff5](https://github.com/GabrielCpp/stablemate/commit/4c36ff5c74015fc0b1e0591a364e112893593b68))
* **workflows:** keep a timed tool in the run's process group ([88d2ec0](https://github.com/GabrielCpp/stablemate/commit/88d2ec02dde4c756bc3726d8f268c77100f6cd59))


### Code Refactoring

* **base-library:** move the commit skill into the method family ([358fd2e](https://github.com/GabrielCpp/stablemate/commit/358fd2eb534a1b27871667462d25d722b3362011))

## [6.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v5.0.0...farrier-v6.0.0) (2026-11-24)


### ⚠ BREAKING CHANGES

* **core:** QaTool, QaTable.tools and HomeConfig.qa_tools are removed from the schema.

### Features

* **base-library:** limit the clone check to given paths in range mode ([603a8ea](https://github.com/GabrielCpp/stablemate/commit/603a8ea6deb44f9f9ab78a457b63fb2d6b8353a0))
* **core:** let a power tier name its compaction window ([0e06e1d](https://github.com/GabrielCpp/stablemate/commit/0e06e1de7fc328a2c4dea65918bffc250995ec99))
* **core:** name the folder of a repository's service books ([1796703](https://github.com/GabrielCpp/stablemate/commit/1796703bf800844e3d0b2b36fb20e08f0f04b80c))
* **core:** open and land a book branch in the artifacts repository ([5a7a818](https://github.com/GabrielCpp/stablemate/commit/5a7a818447780f8d6b9202c6461333cb253d4c7f))
* **core:** resolve the book home from agents.yml and the artifacts repo ([b94c7f9](https://github.com/GabrielCpp/stablemate/commit/b94c7f9609aa52312206f58bc651c73ca791cef4))
* **farrier:** bring copilot's home to parity with claude ([d430058](https://github.com/GabrielCpp/stablemate/commit/d43005845cc51e437515c38194e14874c5d2a711))
* **farrier:** bundle the flaky-shape table with the library ([8a21b66](https://github.com/GabrielCpp/stablemate/commit/8a21b660bba5a46d446b01e54b6b8dac772363b4))
* **farrier:** give a helper agent its own MCP servers ([e19a2e1](https://github.com/GabrielCpp/stablemate/commit/e19a2e19581ac63d416d06b42042de3376d7c4d9))
* **farrier:** let an agent call the tools of a session server ([fd5249e](https://github.com/GabrielCpp/stablemate/commit/fd5249e29a9294b6a78e32d12390581f79a357ca))
* **farrier:** let an agent record grant built-in tools on claude ([b71dc27](https://github.com/GabrielCpp/stablemate/commit/b71dc27de09fcb6c1459de093be4fb639409ab42))
* **farrier:** merge codex settings into its config.toml ([27a338d](https://github.com/GabrielCpp/stablemate/commit/27a338d06bdec3c315bcf1ed31e1519cd577d493))
* **farrier:** merge library settings files into ~/.claude/settings.json ([3e134f1](https://github.com/GabrielCpp/stablemate/commit/3e134f1d44ab0833e39cd5305b3d909cdc03aaae))
* **farrier:** run a guard when the agent ends its turn ([7946a23](https://github.com/GabrielCpp/stablemate/commit/7946a2340168cd0746eb719a218d5d4cc7213efb))
* **farrier:** ship the base library inside the farrier wheel ([9c71dba](https://github.com/GabrielCpp/stablemate/commit/9c71dba3f1a202a3c5fd470c82305e56f4461e6d))
* **ostler:** let a stack's secrets file name the code repository ([ad95b9a](https://github.com/GabrielCpp/stablemate/commit/ad95b9ad92a33631611ad60ee883b78c18a89142))
* **ostler:** read product, team and company books beside services ([a5ae8fe](https://github.com/GabrielCpp/stablemate/commit/a5ae8fe2f81ec551a0c6dfe62f1889411ba18f34))
* **ostler:** search business pages beside the service books ([660e488](https://github.com/GabrielCpp/stablemate/commit/660e488a7185c5ffbefae1e528a9d193b6474008))


### Bug Fixes

* **core:** let a test forget remembered warnings and cached reads ([1bfe2c5](https://github.com/GabrielCpp/stablemate/commit/1bfe2c5557c5968cdbe793c6d9e8615e7b9f47e4))
* **farrier:** resolve the hook cache dir when the hook runs ([55c3d5d](https://github.com/GabrielCpp/stablemate/commit/55c3d5d931d02ed50f8c938fded2e5c2fdf9d54f))
* **farrier:** skip the sync check outside a git work tree ([c15b22c](https://github.com/GabrielCpp/stablemate/commit/c15b22c26ac2994cd3b25fa5c20ead90f97d4be5))
* **ostler:** load only the stacks of the repositories a command knows ([1b17877](https://github.com/GabrielCpp/stablemate/commit/1b178777c4a351836c7eb0fce03bd58015fffe27))
* **ostler:** name a stack copy after its code repository ([3c65e8f](https://github.com/GabrielCpp/stablemate/commit/3c65e8ff84bc5acac6ac84f30d80d0d067761a68))
* **ostler:** read a repo secrets file from the main checkout ([c0d06fa](https://github.com/GabrielCpp/stablemate/commit/c0d06fa834c89a54956a023bccc45f6f0cf25023))
* **ostler:** read the code checkout when a book's root is its own tree ([49afcac](https://github.com/GabrielCpp/stablemate/commit/49afcac60219eb0e8d3fa4843deb27619831d605))
* **ostler:** say what shows that a book of an outside system still holds ([facdc45](https://github.com/GabrielCpp/stablemate/commit/facdc4543f3a1ad6b7aaa4e3fccd7c7ad27e0178))


### Performance Improvements

* keep a folder's repository identity while its git layout holds ([0a31568](https://github.com/GabrielCpp/stablemate/commit/0a31568c543351e4b2b2be60b33ca686a3835fa2))


### Code Refactoring

* **core:** drop config.book_home for books.book_home ([5086eb5](https://github.com/GabrielCpp/stablemate/commit/5086eb5268247be2ab8ee7eefe9675ef62d9f0f7))
* **core:** drop the qa tools keys from both config schemas ([bd68e8c](https://github.com/GabrielCpp/stablemate/commit/bd68e8c9f4826cc155bf7c2bb31d7b81ad1a9c93))
* move the commit-and-push policy into the repo group ([ffdecbc](https://github.com/GabrielCpp/stablemate/commit/ffdecbc7c815ee6d8b88f06bc9d6f488562f9b8f))

## [5.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v4.0.0...farrier-v5.0.0) (2026-10-29)


### ⚠ BREAKING CHANGES

* **core:** exporting STABLEMATE_WORKSPACE no longer selects the artifacts dir as the docs home. List the repository in a [workspaces] entry of the home config instead.

### Features

* **core:** ignore the untracked artifacts shelves by name ([969c315](https://github.com/GabrielCpp/stablemate/commit/969c31556490dd78f770ab44b676765a76ec328c))
* **core:** name the member of the repository holding a folder ([d7042f8](https://github.com/GabrielCpp/stablemate/commit/d7042f81453365a270d5bcd99ff667d12fa73258))
* **core:** resolve the docs home from repository membership ([de05367](https://github.com/GabrielCpp/stablemate/commit/de053673063ba3ce1d1d7d4ce14daf8d92f69483))
* **farrier:** export the shared cache dir to skill hooks ([b53f4ba](https://github.com/GabrielCpp/stablemate/commit/b53f4ba45f629d603b570e9360c9d16c1b7d6583))

## [4.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v3.1.0...farrier-v4.0.0) (2026-10-26)


### ⚠ BREAKING CHANGES

* agents.yml workspace is not read and farrier doctor reports it. base_branch moves under repo.
* .code-workspace files and AGENT_PARAM_WORKSPACE_FILE are no longer read. The docs_path input is gone too.

### Features

* **core:** add a per-user artifacts folder to the home config ([16b7924](https://github.com/GabrielCpp/stablemate/commit/16b79242f1168941efce7548da756021a7fe4e1d))
* **core:** add the paddock_dir home config key ([b00ab00](https://github.com/GabrielCpp/stablemate/commit/b00ab00b98d8cd841219b5c05f1b246f41ffd45c))
* **core:** ignore every session-owned folder in the artifacts repo ([ba13779](https://github.com/GabrielCpp/stablemate/commit/ba137791e26418211a72d07201e72e7161fc2960))
* **farrier:** add eject and let one harness link another's skills ([9d4b14f](https://github.com/GabrielCpp/stablemate/commit/9d4b14f4050231e46c01ce64f60602baa1d69991))
* name multi-repo workspaces in the home config ([bf14ddd](https://github.com/GabrielCpp/stablemate/commit/bf14dddaa308cae4c697e4ba7418e36eced12e62))


### Bug Fixes

* **farrier:** keep a repo install out of the harness homes ([e5644c8](https://github.com/GabrielCpp/stablemate/commit/e5644c88e611031f585145cc3472973df2b393be))
* **workhorse:** render a confined turn's prompt from the skills it loads ([4c08080](https://github.com/GabrielCpp/stablemate/commit/4c0808024b561f009360ca51c076f42e833f41fc))


### Code Refactoring

* declare each service's path under services ([508d927](https://github.com/GabrielCpp/stablemate/commit/508d927e40691d1fcfbc0e3cca385ed681a5dc9e))

## [3.1.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v3.0.0...farrier-v3.1.0) (2026-10-15)


### Features

* **core:** resolve a profile's subagent delegates ([e23e098](https://github.com/GabrielCpp/stablemate/commit/e23e0985759e2f934e1e27b4606b770b7a52b08b))
* **farrier:** fetch the base library at farrier's release tag ([a28fa96](https://github.com/GabrielCpp/stablemate/commit/a28fa969e3fb41c53a46152cf0c1234e0a351b54))
* **farrier:** let agents.yml name the repo a checkout installs under ([739fa26](https://github.com/GabrielCpp/stablemate/commit/739fa26a361d1bc0558141a98f8d7170c508c834))
* **farrier:** offer to install the user library from init ([ecd6d19](https://github.com/GabrielCpp/stablemate/commit/ecd6d1993d3e30bb284e28226265c8b9bc3a001a))
* **farrier:** seed no packs in init and propose a user library ([c13851d](https://github.com/GabrielCpp/stablemate/commit/c13851dfdf8909d00dd050952993297da5c25bb7))


### Bug Fixes

* **farrier:** keep a group's AGENTS.md and CLAUDE.md out of its skills ([e86f0d2](https://github.com/GabrielCpp/stablemate/commit/e86f0d20c5fc5d7f8cbc0c476de287f332eb50a3))
* **farrier:** keep make working in a clone without agents.mk ([d9a96da](https://github.com/GabrielCpp/stablemate/commit/d9a96da1e6be2c886b11fc8842c7c766e1c3c744))
* **farrier:** let a sweep race another install of the same tree ([9cc9c2e](https://github.com/GabrielCpp/stablemate/commit/9cc9c2ef446cc95b95e0e9aac386b9152d373300))
* **farrier:** read unset library paths quietly in agents.mk ([5e0e3da](https://github.com/GabrielCpp/stablemate/commit/5e0e3da1d455ba27a39ec8fc6651dea6587da65a))

## [3.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v2.1.0...farrier-v3.0.0) (2026-09-11)


### ⚠ BREAKING CHANGES

* **farrier:** bare `farrier hooks` no longer defaults to install; use `farrier hooks install` explicitly.
* **core:** bump stablemate config schema to v2

### Features

* **core:** let a power tier scale every wall-clock budget ([50b5081](https://github.com/GabrielCpp/stablemate/commit/50b5081d3930a22e0cae23ed2c989eb56af71d3c))
* **core:** persist a nested config table, and groom's attend settings ([3c51cca](https://github.com/GabrielCpp/stablemate/commit/3c51cca625bf29d50092cbb1cbd2a7399bec8cb3))
* **farrier:** add hooks install/list verbs with dry-run support ([e8b3ed3](https://github.com/GabrielCpp/stablemate/commit/e8b3ed3882c3446e49f1340fd5c3311de7865cfa))
* **farrier:** delete only files tagged generated_by: farrier ([518154e](https://github.com/GabrielCpp/stablemate/commit/518154eb0e718135a3121e4038972b242b978cb5))
* **farrier:** hold skills to the open agent skills spec ([d41bcf1](https://github.com/GabrielCpp/stablemate/commit/d41bcf13debedcaa022fa0d3bcd7b9fd6d77cc90))
* **farrier:** install skills into the harness home directory ([811f71d](https://github.com/GabrielCpp/stablemate/commit/811f71dcecd69c14abe473a5287288059ab43604))
* **farrier:** read the library from the CLI ([846fc81](https://github.com/GabrielCpp/stablemate/commit/846fc81a49d1462477a747f8b483d41678fe6b8a))
* **farrier:** seed a new agents.yml with the base library's two packs ([f33cae3](https://github.com/GabrielCpp/stablemate/commit/f33cae3f9115ae90c55d65ec90fa0f87d2c4a37e))
* **workhorse:** run a measurement detached under a bounded supervisor ([3c0cb8c](https://github.com/GabrielCpp/stablemate/commit/3c0cb8c64e535353a1a6dfae83b04598f2c2e2b0))


### Bug Fixes

* **farrier:** let the aggregated AGENTS.md be regenerated ([5cf584c](https://github.com/GabrielCpp/stablemate/commit/5cf584ca00613914d74aacec66c4b4e6f1d56834))
* **farrier:** stop the generated launcher taking over the help target ([aa2161f](https://github.com/GabrielCpp/stablemate/commit/aa2161f5755c9c762914e949fbe489d36583c24d))
* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))


### Performance Improvements

* consolidate package test startups ([10a5bf8](https://github.com/GabrielCpp/stablemate/commit/10a5bf88d1dee595514222eba8262ed712e3ba36))


### Code Refactoring

* **core:** bump stablemate config schema to v2 ([586d593](https://github.com/GabrielCpp/stablemate/commit/586d593134aad89d14d4f21f748a8c83ae6b4ad8))
* **core:** move the clock port into shared plumbing ([fa5a4f5](https://github.com/GabrielCpp/stablemate/commit/fa5a4f5a7323f0740ee775c6b6f40c8da8f6e64a))
* **farrier:** drop per-skill copilot instruction files ([50e2677](https://github.com/GabrielCpp/stablemate/commit/50e2677100809b5d3a56601a306eb897878ef704))
* **farrier:** guard the front-matter token's line map ([dc6a378](https://github.com/GabrielCpp/stablemate/commit/dc6a3780a13da611569ea8a8b3373c445747ebe9))
* **farrier:** name installed skills by their library group ([170b38a](https://github.com/GabrielCpp/stablemate/commit/170b38a59611a3ad35fb2444790c055a7440d2a4))

## [2.1.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v2.0.0...farrier-v2.1.0) (2026-08-14)


### Features

* **core:** read the fallback agent cli from the shared config ([8cc0836](https://github.com/GabrielCpp/stablemate/commit/8cc0836a7888b6c5942eaf36b5cb950a19148dff))


### Bug Fixes

* **farrier:** point setup errors at farrier init and the pack catalog ([6162372](https://github.com/GabrielCpp/stablemate/commit/61623720eaf4b214f34438efa8db855b6518dca9))

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v1.5.2...farrier-v2.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* installed skill names change for every repo that selects the `stablemate` pack — `<repo>-stablemate-ostler` becomes `<repo>-ostler`. An agents.yml selecting `stablemate/stablemate-ostler` by hand, a `localInstructions` entry, or a prompt naming an old skill has to be updated; farrier reports the miss with a suggestion rather than installing nothing. In the stablemate repo most installed names are unchanged, because the derived prefix restores them: `ostler` installs as `stablemate-ostler` exactly as before. The two that do move here are `stablemate-coder-workflow` -> `stablemate-workhorse-coder-workflow` and `stablemate-documentation` -> `stablemate-ostler-documentation`.
* `agents.yml` `repo.name` / `repo.prefix` no longer set the install prefix. A repo that used either to install under a name other than its directory's renders its skills under different filenames after this change; rename the directory to keep them. Repos whose prefix already matched their directory name — which the installer defaulted to — are unaffected.

### Features

* derive a repo's name from its directory, never from agents.yml ([884b2e4](https://github.com/GabrielCpp/stablemate/commit/884b2e4294055adbf9c51613e4620dd4339e01e4))
* **farrier:** add `library --check` to catch front matter that silently fails ([023b28d](https://github.com/GabrielCpp/stablemate/commit/023b28d807aa71c312bb0d9dba4480669e562a40))
* **farrier:** add init, and show the verbs for a bare invocation ([181a15d](https://github.com/GabrielCpp/stablemate/commit/181a15d44381981a0995e7ee820ab891aaf17817))
* **farrier:** discover runnable workflows from pipx, at make time ([b0b259e](https://github.com/GabrielCpp/stablemate/commit/b0b259e61afe0d18bfd98ea8511695b2dfed4f60))
* **farrier:** fetch and update the base library on install ([005f6dc](https://github.com/GabrielCpp/stablemate/commit/005f6dcd7a16b6650b4be17b8993fe8fd1eccc16))
* **farrier:** launch one container per run, with its own run id ([d4a0f87](https://github.com/GabrielCpp/stablemate/commit/d4a0f879b1ae899f42c8f128acbe36e818799238))
* **farrier:** let localInstructions aggregate prompts and name its file ([0bcd940](https://github.com/GabrielCpp/stablemate/commit/0bcd940e689a8af351ac74e92faa15cf4921c91b))
* **workflows:** give each run its own worktree of one host repo ([1e6c065](https://github.com/GabrielCpp/stablemate/commit/1e6c06541e919e03b9592dbfefecf921ad13d489))
* **workhorse:** keep container output host-usable, and let it log in ([b2432ea](https://github.com/GabrielCpp/stablemate/commit/b2432ea4045b6f67686452106f4c5b1a4e591296))
* **workhorse:** replace the aider backend with cline ([7cdf30e](https://github.com/GabrielCpp/stablemate/commit/7cdf30e44563d7af497ee0d341f77d205e989b0b))


### Bug Fixes

* **farrier:** catch a tag YAML resolves as something other than a string ([7cf8386](https://github.com/GabrielCpp/stablemate/commit/7cf8386638410605d88f77fa011accb94e428999))
* **farrier:** commit the codex adapters, and drop the redundant leading slash ([aab5964](https://github.com/GabrielCpp/stablemate/commit/aab596486560c9cf670f0d2f095947e9ddbcfce3))
* **farrier:** drop $ARGUMENTS from a prompt aggregated into instructions ([6805272](https://github.com/GabrielCpp/stablemate/commit/6805272ecb9db0d0c669c31882906e5c0c4d4fc5))
* **farrier:** drop the do-not-edit marker from the aggregated AGENTS.md ([cbd5527](https://github.com/GabrielCpp/stablemate/commit/cbd55270bd2534fd6aa679a9e18312e3c65c6b71))
* **farrier:** honor {% raw %} in skill files that name no helper ([5f1b39d](https://github.com/GabrielCpp/stablemate/commit/5f1b39dd480fa8c6bd9880e208c38eda83a8d4ba))
* **farrier:** stop naming the private library repo in generated output ([631386f](https://github.com/GabrielCpp/stablemate/commit/631386f5dd839e3444854d16d586587f339c6931))


### Code Refactoring

* **farrier:** aggregate local instructions into AGENTS.md ([0da2789](https://github.com/GabrielCpp/stablemate/commit/0da2789064f5de0fc8cd152b6937ffb0d726b8e6))
* name base-library skills after their tool, not after stablemate ([2244a42](https://github.com/GabrielCpp/stablemate/commit/2244a420cfc0c837331f5e4b798dd784093d52c7))

## [1.5.2](https://github.com/GabrielCpp/stablemate/compare/farrier-v1.5.1...farrier-v1.5.2) (2026-08-02)


### Code Refactoring

* vendor stablemate-core into workhorse and farrier ([0bef8ff](https://github.com/GabrielCpp/stablemate/commit/0bef8ff23771bc11992d9f33ae790604359d2804))
