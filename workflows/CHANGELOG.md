# Changelog

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v0.2.0...workhorse-workflows-v1.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **workflows:** treat every backlog bullet as intake
* remove legacy gap and knowledge doc types
* installed skill names change for every repo that selects the `stablemate` pack — `<repo>-stablemate-ostler` becomes `<repo>-ostler`. An agents.yml selecting `stablemate/stablemate-ostler` by hand, a `localInstructions` entry, or a prompt naming an old skill has to be updated; farrier reports the miss with a suggestion rather than installing nothing. In the stablemate repo most installed names are unchanged, because the derived prefix restores them: `ostler` installs as `stablemate-ostler` exactly as before. The two that do move here are `stablemate-coder-workflow` -> `stablemate-workhorse-coder-workflow` and `stablemate-documentation` -> `stablemate-ostler-documentation`.
* `agents.yml` `repo.name` / `repo.prefix` no longer set the install prefix. A repo that used either to install under a name other than its directory's renders its skills under different filenames after this change; rename the directory to keep them. Repos whose prefix already matched their directory name — which the installer defaulted to — are unaffected.

### Features

* derive a repo's name from its directory, never from agents.yml ([884b2e4](https://github.com/GabrielCpp/stablemate/commit/884b2e4294055adbf9c51613e4620dd4339e01e4))
* **workflows:** add a bank verdict and program-scoped research budget ([4ea2b3b](https://github.com/GabrielCpp/stablemate/commit/4ea2b3b51552b2dee64111b455e87d4e0d39df2a))
* **workflows:** add checkpointed plan implementation flow ([3e76810](https://github.com/GabrielCpp/stablemate/commit/3e76810bdec754a9011a49ea070df1c8c6c90b5f))
* **workflows:** add stage-plan flow to run a plan phase by phase ([260d0d1](https://github.com/GabrielCpp/stablemate/commit/260d0d101c67160cddaa6531eda7ac14e29272dc))
* **workflows:** classify what a rework pass bought ([ff5e2a6](https://github.com/GabrielCpp/stablemate/commit/ff5e2a6307d97b20fd01584a37b3d271f140e332))
* **workflows:** decide the author's mockup, audit and give-up from data ([1aade41](https://github.com/GabrielCpp/stablemate/commit/1aade41189fe103b67383e9ae40f7ca8c88d11dc))
* **workflows:** give each run its own worktree of one host repo ([1e6c065](https://github.com/GabrielCpp/stablemate/commit/1e6c06541e919e03b9592dbfefecf921ad13d489))
* **workflows:** give the docs grounding gate countable failures ([69371b1](https://github.com/GabrielCpp/stablemate/commit/69371b1857840cdefbcb16a97081b8822bb153d2))
* **workflows:** let the author prompts find stacks by tag, not by name ([f787e9f](https://github.com/GabrielCpp/stablemate/commit/f787e9f9c7e8422cdccf5e4a81deb27649d9cb60))
* **workflows:** raise the research verdict turns to the smart tier ([f7ca965](https://github.com/GabrielCpp/stablemate/commit/f7ca96564f8f0051480a4b8c46229a829365be3f))
* **workflows:** reconcile epic edits across authored scope ([85e94d3](https://github.com/GabrielCpp/stablemate/commit/85e94d3fb5ba3985de9aa54f8759b6cff10a90ba))
* **workflows:** record each QA gate's verdict on the loop ([ec75b19](https://github.com/GabrielCpp/stablemate/commit/ec75b1936985a32bdbadedfc394c893cc3bd13e1))
* **workflows:** report docs gate verdicts and loop progress ([44be37a](https://github.com/GabrielCpp/stablemate/commit/44be37a00f695b6c1ca83f69974c3f4cf0d77070))
* **workflows:** report the coder's rework budgets as span dimensions ([d91d02e](https://github.com/GabrielCpp/stablemate/commit/d91d02e82c93f66b3ad0f52fd2772e8756b65f9a))
* **workflows:** review the plan candidate before completing ([8860e5c](https://github.com/GabrielCpp/stablemate/commit/8860e5c473d016f0992cf15bee2ed8d44bcf2508))
* **workflows:** treat every backlog bullet as intake ([bacf5f2](https://github.com/GabrielCpp/stablemate/commit/bacf5f2de5dcb14fd68f04388acaec2d7638bfb7))
* **workhorse:** let a workflow mark its infrastructure nodes ([1f9ca28](https://github.com/GabrielCpp/stablemate/commit/1f9ca28f09cdcf4376857b3f88865a479080077e))


### Bug Fixes

* verify sibling packages before release ([a70c99a](https://github.com/GabrielCpp/stablemate/commit/a70c99abaddd9c195932a9da506519f473c42833))
* **workflows:** accept a ~-marked code: ref as grounding a deletion ([8baed1e](https://github.com/GabrielCpp/stablemate/commit/8baed1e643e2ecf6c0e8363ddd8477bdb9ddf638))
* **workflows:** accumulate the documented nodes across rework laps ([deb2fc2](https://github.com/GabrielCpp/stablemate/commit/deb2fc2d09990e3a83bdc56d3e9433e613249bf5))
* **workflows:** bound ineffective recovery cycles ([cfe9b6e](https://github.com/GabrielCpp/stablemate/commit/cfe9b6edd4096d38ca584de29185b0ac1bd4bba1))
* **workflows:** bound the doc and qa-plan reviewers to the story delta ([edb46f5](https://github.com/GabrielCpp/stablemate/commit/edb46f5d82310b7f06481c3987bac2fd47cddc11))
* **workflows:** bound the product of the stacked qa-plan budgets ([f773983](https://github.com/GabrielCpp/stablemate/commit/f773983174f1b91ccce301e344fa3b483786d3d0))
* **workflows:** carry every plan-review refusal into the next qa plan ([6466e7a](https://github.com/GabrielCpp/stablemate/commit/6466e7ac3e9b44edef58e1c9e97e05904fe917ff))
* **workflows:** carry structured documentation findings ([91a8d46](https://github.com/GabrielCpp/stablemate/commit/91a8d46cb18659918025127a5ef35f8dd135768f))
* **workflows:** claim an epic branch by state, not by renaming it aside ([0a0eba8](https://github.com/GabrielCpp/stablemate/commit/0a0eba84d039c596261d68a76d9a446436db4a51))
* **workflows:** drop QA-plan findings the plan author may not act on ([41a27bf](https://github.com/GabrielCpp/stablemate/commit/41a27bfeadda6be558ff8c008337df5b599edc2c))
* **workflows:** drop the ~ deletion marker from the docs gate ([3a24f01](https://github.com/GabrielCpp/stablemate/commit/3a24f0150dacdd26f875c57a1c1ca08a4c4b2e8e))
* **workflows:** end the QA-plan review treadmill ([651eb4e](https://github.com/GabrielCpp/stablemate/commit/651eb4ee5c34334490744a4081610a20172a7364))
* **workflows:** ground a nested symbol by the unit that encloses it ([fe95cbf](https://github.com/GabrielCpp/stablemate/commit/fe95cbf552b653bfeb5f9ce736e09077163ec6be))
* **workflows:** hand the docs author its grounding worklist up front ([e033591](https://github.com/GabrielCpp/stablemate/commit/e0335914524ea2cfbd69df13d2d91881e1d826bb))
* **workflows:** keep an unconverged doc review from killing the run ([4ac41e2](https://github.com/GabrielCpp/stablemate/commit/4ac41e2520d519afffbf165a3529981dc8873d2e))
* **workflows:** let planning pass a story that is already planned ([ee7459e](https://github.com/GabrielCpp/stablemate/commit/ee7459ef15eab502414205c6e610ab0e72e1f54f))
* **workflows:** let stories define in-scope behavior ([b2f98da](https://github.com/GabrielCpp/stablemate/commit/b2f98dad381ca35664f7a3323a746c84940923e6))
* **workflows:** render resolved paths in author prompts ([5a7906d](https://github.com/GabrielCpp/stablemate/commit/5a7906d01f14ef4f7d69ddcf82b4f47caf59c2e9))
* **workflows:** require the cline-capable engine ([c20ea56](https://github.com/GabrielCpp/stablemate/commit/c20ea568dce75cecc14561928b223821cc749534))
* **workflows:** retier the research turns that decide what gets banked ([6316cb4](https://github.com/GabrielCpp/stablemate/commit/6316cb47c71926b8c0f229715b7bf0b5ab7a97d5))
* **workflows:** reviewer must not reject the ~ deletion marker ([c3bc0de](https://github.com/GabrielCpp/stablemate/commit/c3bc0de3f9352a725f2005db99a5505af099f21d))
* **workflows:** route QA findings to the gate that can repair them ([e4b1b1c](https://github.com/GabrielCpp/stablemate/commit/e4b1b1c2eff4755a847d31d79f1cd756afdd2514))
* **workflows:** stop a story heading's label doubling in its subject ([a5ce953](https://github.com/GabrielCpp/stablemate/commit/a5ce95370c60ee57217b435b191a62c2604b45e1))
* **workflows:** stop author from creating feature inventories ([9caacc6](https://github.com/GabrielCpp/stablemate/commit/9caacc653a818a4e0707c38f43ffd0c3b10ada98))
* **workflows:** stop format-checking agent-authored ids ([314fa4a](https://github.com/GabrielCpp/stablemate/commit/314fa4aeaf050da9bc231bf192f4c82d5e870289))
* **workflows:** stop reading a refused commit as an empty one ([d1a1d38](https://github.com/GabrielCpp/stablemate/commit/d1a1d381ca5086db7614fcab974fe75b44264d0e))
* **workflows:** stop schema typos starving the QA-plan reviewer ([2b29b47](https://github.com/GabrielCpp/stablemate/commit/2b29b47d717a8604eec32f5a65730e813935cab9))
* **workflows:** stop the zero-diff guard killing re-verified stories ([9870d9f](https://github.com/GabrielCpp/stablemate/commit/9870d9f8eec2195d406520b1e24f3a2c35663c2c))
* **workflows:** tell the plan reviewer who owns the qa stack ([a445200](https://github.com/GabrielCpp/stablemate/commit/a445200ff864f3122165c5f2491ffd5cc6f2fc7c))
* **workflows:** type the QA give-up doc so it stops blocking stories ([10030f3](https://github.com/GabrielCpp/stablemate/commit/10030f397a82dd413ca6201d4757dc84374de924))
* **workflows:** warn qa-plan authoring off known bad locator patterns ([1f54db2](https://github.com/GabrielCpp/stablemate/commit/1f54db227a470f37c1c8b5876b461011035ade30))


### Performance Improvements

* **workflows:** avoid redundant author review turns ([5db7c37](https://github.com/GabrielCpp/stablemate/commit/5db7c3702f51809ec55ee0db040488fb8b6aa8f4))
* **workflows:** bound total QA plan repairs ([541f646](https://github.com/GabrielCpp/stablemate/commit/541f646a40ddcd370b874666e2067b262a7cfbb3))
* **workflows:** recheck docs only after mutations ([8bdbd78](https://github.com/GabrielCpp/stablemate/commit/8bdbd78942fef762aae917929be9fe9ee2f26585))


### Code Refactoring

* move the scriptutil helpers from workhorse into workflows' kit ([1360d56](https://github.com/GabrielCpp/stablemate/commit/1360d5610c7e89e0dd5cb44f7d48f92fb8fb8170))
* name base-library skills after their tool, not after stablemate ([2244a42](https://github.com/GabrielCpp/stablemate/commit/2244a420cfc0c837331f5e4b798dd784093d52c7))
* remove legacy gap and knowledge doc types ([0dfb566](https://github.com/GabrielCpp/stablemate/commit/0dfb566862e77dfbf05f812c6cfbb82e02692021))
* **workflows:** make the aggregate gate primitives reusable ([400e66d](https://github.com/GabrielCpp/stablemate/commit/400e66d2546eae284c59577190e33225da71040d))
* **workflows:** make the qa-plan review a finding contract ([88e38ba](https://github.com/GabrielCpp/stablemate/commit/88e38ba7c777a3798890f6e52f3a07e0f35fcc24))
* **workflows:** repair the cited parts instead of re-authoring ([3816b78](https://github.com/GabrielCpp/stablemate/commit/3816b78f7b8d9304edc57e3e9596c5424a617073))
* **workflows:** tier every research turn, not most of them ([7ea23b7](https://github.com/GabrielCpp/stablemate/commit/7ea23b70aa38db06ca0c8c8806ed5f36e77740ed))
* **workhorse:** drop the unused scriptutil helpers ([c850681](https://github.com/GabrielCpp/stablemate/commit/c850681191140241e1661de735403e1fbc1a6346))
* **workhorse:** supervise the container from Python, not shell ([6de875f](https://github.com/GabrielCpp/stablemate/commit/6de875f4ed47803201c1aedb2a9de676b15f110b))

## [0.2.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v0.1.0...workhorse-workflows-v0.2.0) (2026-08-02)


### Features

* **workflows:** contain an unfinished story instead of failing the run ([1268473](https://github.com/GabrielCpp/stablemate/commit/12684737a467cd61e42409d7abe9d9ea5ca1f3d4))
* **workflows:** require book-grounded locators in the qa plan ([81306db](https://github.com/GabrielCpp/stablemate/commit/81306db0505470c9d4266f6de08a4d9ee7c241b4))


### Bug Fixes

* **workflows:** keep an escalating resolver's note on the await paths ([6a68bdc](https://github.com/GabrielCpp/stablemate/commit/6a68bdc5c1e42ff42defc4f29760c557d56c9221))
* **workflows:** owe no verdict for a context-only obligation ([5d80457](https://github.com/GabrielCpp/stablemate/commit/5d80457e799d1181e47b04b3c5c7c5015833fdc1))
* **workflows:** stop the implement prompt writing the story status ([0a50f53](https://github.com/GabrielCpp/stablemate/commit/0a50f53943bf6bd4b83dc9a69fc173dda6440e11))


### Code Refactoring

* **workflows:** read the verify index from its sidecar file ([60be6ef](https://github.com/GabrielCpp/stablemate/commit/60be6ef360c5b02461c94c641c0f9bd62ea3f32e))
