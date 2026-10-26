# Changelog

## [4.0.1](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v4.0.0...workhorse-workflows-v4.0.1) (2026-10-26)


### Bug Fixes

* **workflows:** allow ostler 5.x ([358a83c](https://github.com/GabrielCpp/stablemate/commit/358a83c65d311fdd0d2ca8554af1095f4f367940))


### Reverts

* **workflows:** pin ostler 4.x again ([56d7e18](https://github.com/GabrielCpp/stablemate/commit/56d7e186a7bf3816e970138a5de3df3b39929ad2))

## [4.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v3.0.0...workhorse-workflows-v4.0.0) (2026-10-26)


### ⚠ BREAKING CHANGES

* **workflows:** the epic-split review, the coverage review, the story audit and the resolve-operator loops are gone, with audit-receipt.json, story-split-receipt.json and the per-epic and per-story context gates. Stories authored before this change carry no PM receipt and are re-reviewed on the next run.
* **workflows:** seed services must name books under docs/services, and the design: preserve exemption is gone. An epic whose seeds carry no services, or a UI story with no mockup, now fails Author's lint.
* **workflows:** Author runs started before this change cannot resume, because the planner state they checkpointed is gone.
* **workflows:** docs/roadmaps is not read and the milestone stage is gone. Author fails before any turn when no milestone folder is approved, when several are, or when the approved one is not ready.
* agents.yml workspace is not read and farrier doctor reports it. base_branch moves under repo.
* docRoots is not read. Ostler doctor reports removed-doc-roots for a config that still carries the key.
* .code-workspace files and AGENT_PARAM_WORKSPACE_FILE are no longer read. The docs_path input is gone too.
* books are read from docs/services only. A repository that still has docs/features must run `ostler okf migrate` or rename the folder.

### Features

* name multi-repo workspaces in the home config ([bf14ddd](https://github.com/GabrielCpp/stablemate/commit/bf14dddaa308cae4c697e4ba7418e36eced12e62))
* **workflows:** author a milestone through drains with a final gate ([ce3447e](https://github.com/GabrielCpp/stablemate/commit/ce3447e1ce92ab467e8f55330e7a51b39c33bc11))
* **workflows:** author from the approved milestone folder ([3b2bd5e](https://github.com/GabrielCpp/stablemate/commit/3b2bd5eca82fe7a0ae947e1fad7c96d2f13c76e6))
* **workflows:** check each criterion and rerun failed proof in dev ([28d4729](https://github.com/GabrielCpp/stablemate/commit/28d4729571f70fac87d882a1e15b3ddb5c3ea6fc))
* **workflows:** derive story services and block a story on its mockup ([0d1292a](https://github.com/GabrielCpp/stablemate/commit/0d1292a7e2b9ecfd0cef5c6bf0a131368cd63807))
* **workflows:** file dev-turn follow-ups as debt records ([524fac9](https://github.com/GabrielCpp/stablemate/commit/524fac97990c41076cde593eabf8b1baf107536b))
* **workflows:** file dev-turn follow-ups to a deferred backlog section ([c56de70](https://github.com/GabrielCpp/stablemate/commit/c56de7047f695668cae7e97d9f92c52ec1f64cba))
* **workflows:** file qa leftovers as records and drain them in fixes ([13bd533](https://github.com/GabrielCpp/stablemate/commit/13bd5332fdb8151f0d3c84a13e6d49edff093ed0))
* **workflows:** file survey and parity findings as register records ([934d783](https://github.com/GabrielCpp/stablemate/commit/934d78393535ac4932c180d1eff5b46b6d30ca56))
* **workflows:** file the book checks qa could not run as records ([ce5ac39](https://github.com/GabrielCpp/stablemate/commit/ce5ac39011cd4375120a25050f130894395015cc))
* **workflows:** give a story QA sent back its own rework prompt ([3df7d7e](https://github.com/GabrielCpp/stablemate/commit/3df7d7e8ec57bdae875ede1d51c0394f02e06f3b))
* **workflows:** give every defect one owner and one worklist entry ([0ecf44e](https://github.com/GabrielCpp/stablemate/commit/0ecf44e516d7a0afcd9a204eb8a8941dba92a79c))
* **workflows:** give the writer a mobile branch of the book prompt ([b674ebf](https://github.com/GabrielCpp/stablemate/commit/b674ebf63322d8716cefb07fe4151718fd03abe9))
* **workflows:** hold fix-item fixers to the dev lane's root-cause rule ([e3ce9cd](https://github.com/GabrielCpp/stablemate/commit/e3ce9cdcfb291cb4c91f1351c29e98958514cf91))
* **workflows:** make the PM Author's only reviewer ([6811501](https://github.com/GabrielCpp/stablemate/commit/6811501334c78e5bb96203946be1e7e26dbbc1c0))
* **workflows:** merge the story locally when a repo has no remote ([601adbd](https://github.com/GabrielCpp/stablemate/commit/601adbd49aa0329586d349d2bdc82632f5fda406))
* **workflows:** point the grpc writer at stream claims ([93ba1c0](https://github.com/GabrielCpp/stablemate/commit/93ba1c0d02bf5dd964547747506806e0c74e8f44))
* **workflows:** promote a register record into an epic story ([836f1bf](https://github.com/GabrielCpp/stablemate/commit/836f1bf35efc141722187cbcd4bc01576b7d70d4))
* **workflows:** propose a decision for each large debt cluster ([113720e](https://github.com/GabrielCpp/stablemate/commit/113720e989f109e521867dae6526d7dfd39fb274))
* **workflows:** read story specs from the artifacts folder ([b141b68](https://github.com/GabrielCpp/stablemate/commit/b141b6815a0e11c3db233b683e648227a8f3dd4a))
* **workflows:** reject a "not a defect" decline that names no test ([c7d24ed](https://github.com/GabrielCpp/stablemate/commit/c7d24ed41b1a290d9694f915899c674d0bc67d72))
* **workflows:** rerun only the proof a passed story's leftovers reopen ([b2f5082](https://github.com/GabrielCpp/stablemate/commit/b2f508240e4eed2de0a2bc42909e236b0318971e))
* **workflows:** review the debt register into an accounted report ([4395f56](https://github.com/GabrielCpp/stablemate/commit/4395f56bc80320d731cee3e19bf0b3cfde2fbaa0))
* **workflows:** route a failed qa scenario by the side ostler gives it ([ef093b5](https://github.com/GabrielCpp/stablemate/commit/ef093b52e0411777f22cbfd32891522eddd854ad))
* **workflows:** run a workspace book's scenarios against its member ([8d512a2](https://github.com/GabrielCpp/stablemate/commit/8d512a2a825dcc2a55ee4f02809ac7b4e24eac12))
* **workflows:** tell an http writer its routes come from the proto ([c7d66b0](https://github.com/GabrielCpp/stablemate/commit/c7d66b0e9a4da39424e952b73cbe1341d3757a9f))
* **workflows:** write a grpc surface's book from its contract ([32e7ea8](https://github.com/GabrielCpp/stablemate/commit/32e7ea82a5e45b015ada0b266a6dce3fcd8b0925))
* **workflows:** write a workspace book from its member repo's source ([724343d](https://github.com/GabrielCpp/stablemate/commit/724343df84ec1876d794e0ec25502f6fe2861b61))


### Bug Fixes

* **ostler:** name the shared copy to commands run against it ([e6d45e7](https://github.com/GabrielCpp/stablemate/commit/e6d45e7121237cc1775f0345759c50fbe26136a8))
* **workflows:** allow workhorse-agent 5.x ([085b5df](https://github.com/GabrielCpp/stablemate/commit/085b5df823735ed7a6c18c4cc5d07ef413beb2f1))
* **workflows:** allow workhorse-agent 5.x, ostler 4.x ([b3f79e2](https://github.com/GabrielCpp/stablemate/commit/b3f79e269d9897a4a2efe402de29fc585b62abcb))
* **workflows:** ask no page for a file that declares no name ([6dd8646](https://github.com/GabrielCpp/stablemate/commit/6dd864621dbfb6932db317f679b5412aa5d73eb9))
* **workflows:** ask the story writer when each new transient state ends ([1ad7a90](https://github.com/GabrielCpp/stablemate/commit/1ad7a903a6f36e0c3a0af7041b939efbdd4514aa))
* **workflows:** boot the device when a stack copy serves a mobile book ([bbd4226](https://github.com/GabrielCpp/stablemate/commit/bbd422636f2b1ac43c70662289785a6427fe15a3))
* **workflows:** commit only what the fix item's own turn wrote ([6f90c17](https://github.com/GabrielCpp/stablemate/commit/6f90c1711bdebb376a765af4b626dc56c8e77b2d))
* **workflows:** commit the story's operator context with its stamp ([59cdd1f](https://github.com/GabrielCpp/stablemate/commit/59cdd1f3ba820f17b8c9631009d4c7cb5c585aa1))
* **workflows:** count only claim-bearing citations as coverage ([bf77dc9](https://github.com/GabrielCpp/stablemate/commit/bf77dc981fc7088b40f518e4c094f647e2540a0c))
* **workflows:** count todo as an open question only as a marker ([c871f8a](https://github.com/GabrielCpp/stablemate/commit/c871f8ab2927f3d7791474f0b92954ecd46bdfd5))
* **workflows:** drop the book hint from a state red the app owns ([e8183e3](https://github.com/GabrielCpp/stablemate/commit/e8183e352b7c45c4f6f635f49e15eaaaedef749f))
* **workflows:** file deferred qa obligations to the backlog, not a gate ([94cec2a](https://github.com/GabrielCpp/stablemate/commit/94cec2a919e99fdf54219a88bb40476879cd7026))
* **workflows:** file only open, new product work under filed by coder ([71a467d](https://github.com/GabrielCpp/stablemate/commit/71a467d28a0dee593febf42ce3fb554dfe83f71a))
* **workflows:** file only undone product work as a dev-turn follow-up ([af8b091](https://github.com/GabrielCpp/stablemate/commit/af8b091da3440088e3fa8127ced043d4cbacd996))
* **workflows:** give an owner started afresh the operator's answer ([c1ef0d6](https://github.com/GabrielCpp/stablemate/commit/c1ef0d635b8c8286e7370c0e2314025e35319ea0))
* **workflows:** give the coder judge no tools so its one turn answers ([f88dea4](https://github.com/GabrielCpp/stablemate/commit/f88dea4b08cca75c2cec0db4f8318dcc3dc83d07))
* **workflows:** keep book checks out of the backlog the fix lane drains ([6ed8daa](https://github.com/GabrielCpp/stablemate/commit/6ed8daacf2efcc9a5630131ce3484a915ffd1b4c))
* **workflows:** keep the coder bookkeeping commits out of the repo hooks ([1688ced](https://github.com/GabrielCpp/stablemate/commit/1688cedbbd68dd88f7fe710c8a80c1b32628f6f1))
* **workflows:** leave the run dirs out of the exercise copy of the app ([4ab8f86](https://github.com/GabrielCpp/stablemate/commit/4ab8f86b575d0076d257832f2bace59193208070))
* **workflows:** leave the whole .agents dir out of the exercise copy ([2594e1d](https://github.com/GabrielCpp/stablemate/commit/2594e1d78344be2d870eb95e76ea0b42ccc878a6))
* **workflows:** let a story keep services narrower than its seeds ([16900e6](https://github.com/GabrielCpp/stablemate/commit/16900e61f7bed42386ee6616a38a2d1b7d8b8b3b))
* **workflows:** let a workspace writer read its product repo and skills ([506bb46](https://github.com/GabrielCpp/stablemate/commit/506bb4671603da73a499b99cda47a9c11b463ab7))
* **workflows:** let the author dry run walk to its commit ([5565fa3](https://github.com/GabrielCpp/stablemate/commit/5565fa3122558662d1f42bd36f773ea3989d6a41))
* **workflows:** let the scored run prove a scenario its dry run lost ([507c042](https://github.com/GabrielCpp/stablemate/commit/507c042c85155063da2a4d727750a9e07a3277cc))
* **workflows:** mark the coder's fixes epic as a backlog of follow-ups ([f6a21f6](https://github.com/GabrielCpp/stablemate/commit/f6a21f6cf3c33e63a5f845d5781fd5bbe0d3ed99))
* **workflows:** match dry-run records to a scenario's function name ([b24af90](https://github.com/GabrielCpp/stablemate/commit/b24af90f34178a4ad30ce2bab4b897112ac546d2))
* **workflows:** match one defect across stories by what the user sees ([df4be34](https://github.com/GabrielCpp/stablemate/commit/df4be34064926d2db31549ba988029ecfcfcbd25))
* **workflows:** name the source record by id in a fix-story seed ([9138782](https://github.com/GabrielCpp/stablemate/commit/9138782676b6dff049ccdee211791656588e616e))
* **workflows:** render the agent files before a story commit ([21b5e9c](https://github.com/GabrielCpp/stablemate/commit/21b5e9cd8cd037ba6d55c80984ce0c2e10d71f0a))
* **workflows:** repair the call sites the node typing exposed ([ede4040](https://github.com/GabrielCpp/stablemate/commit/ede40405b02f1d163431c58462fa67ef805c6fc1))
* **workflows:** reset an owner that names the book and writes nothing ([46c49f3](https://github.com/GabrielCpp/stablemate/commit/46c49f3b067a7400cfea620233f37589b98bd0ed))
* **workflows:** review research builds without the code-review skill ([cf3fd86](https://github.com/GabrielCpp/stablemate/commit/cf3fd86344ed65b7f3fe065507a84573bf6c7c24))
* **workflows:** say the greenfield technical-notes sentence stands alone ([a14120f](https://github.com/GabrielCpp/stablemate/commit/a14120f163f10a910e7bbea1aa9881ea7bc8b69c))
* **workflows:** say what an okf-book entry is when it names no folder ([88e6751](https://github.com/GabrielCpp/stablemate/commit/88e6751a86ce1a6a047fe67ab69f051969137ba2))
* **workflows:** scope the qa packet to the story's own changes ([789d48e](https://github.com/GabrielCpp/stablemate/commit/789d48e389842ea6b91877f66c41fde4b4169ca7))
* **workflows:** scope the qa packet to the story's own changes ([0e37d45](https://github.com/GabrielCpp/stablemate/commit/0e37d454990367c5f6408018ce9e0fb6f8c9f592))
* **workflows:** score story qa against the copy its bring-up started ([7bb4a9c](https://github.com/GabrielCpp/stablemate/commit/7bb4a9cf97def4324f13f57a96890f49d86d14d2))
* **workflows:** show the coder's dev turn the findings qa filed ([bbabcc8](https://github.com/GabrielCpp/stablemate/commit/bbabcc8f7109e621a315df31597802c1089d248b))
* **workflows:** skip the full lap when the gate closed every blocker ([3262bf4](https://github.com/GabrielCpp/stablemate/commit/3262bf4910b3b6e366613c72a272a22aabbd487c))
* **workflows:** tear down the stack.yml copy at the run's end ([6249002](https://github.com/GabrielCpp/stablemate/commit/6249002b5b80888e73fbb63adb8d17aec6f93e18))
* **workflows:** walk the coder's dry run to its terminal ([f4cbf73](https://github.com/GabrielCpp/stablemate/commit/f4cbf731536d6609960d3d25631ee0756c7d2c60))
* **workflows:** walk the okf-book dry run past the app's stack ([14385ef](https://github.com/GabrielCpp/stablemate/commit/14385ef119d5650ad3fd9643f372f5e75f0cb563))


### Performance Improvements

* **workflows:** keep the dry run off the book's graph ([890d800](https://github.com/GabrielCpp/stablemate/commit/890d8007c5e1694800496923bc939319c2ff410f))
* **workflows:** read a member's changed file in place when regrounding ([06b07df](https://github.com/GabrielCpp/stablemate/commit/06b07dfc089f666b6f833c12c9be392875d9da99))
* **workflows:** read the writer's source in place instead of a copy ([c22e6ac](https://github.com/GabrielCpp/stablemate/commit/c22e6acd1e30109f939ba037b7a9f949e388e35d))


### Code Refactoring

* declare each service's path under services ([508d927](https://github.com/GabrielCpp/stablemate/commit/508d927e40691d1fcfbc0e3cca385ed681a5dc9e))
* fix document locations and drop docRoots ([66fc17c](https://github.com/GabrielCpp/stablemate/commit/66fc17c7e3ea82ba72e0d052e5b06a072558ec11))
* move the book root from docs/features to docs/services ([9c14166](https://github.com/GabrielCpp/stablemate/commit/9c141662047ead9a9ed398a21477b62223db9ef0))
* **ostler:** keep the shared test plumbing in a testing package ([ca90ee3](https://github.com/GabrielCpp/stablemate/commit/ca90ee3f079117faa771a94218e1b4d8701b6db4))
* **workflows:** drop the coder's docs/backlog.md requirement ([fc8e464](https://github.com/GabrielCpp/stablemate/commit/fc8e464a94d637f745b384eb5fbae8ac837010f4))
* **workflows:** hand ostler the story id, never the slug ([f67a14c](https://github.com/GabrielCpp/stablemate/commit/f67a14c2b7269aa60233f0786c1505f6ed53df55))
* **workflows:** move the agent-file render helper into kit ([b87e05c](https://github.com/GabrielCpp/stablemate/commit/b87e05c03e04926f9e35b67962319d24896d9721))

## [3.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v2.0.0...workhorse-workflows-v3.0.0) (2026-10-15)


### ⚠ BREAKING CHANGES

* **ostler:** a stack.yml outside ops/, a book-level secrets: naming a saddlebag environment and render: are refused. `env check` names the new shape for each.
* **workflows:** the review lane and its flow are gone, and the old dev, QA, docs and merge prompt files are removed or renamed. A repo flavor that overrides one of those prompts no longer applies, and a run checkpointed by the earlier coder does not resume.

### Features

* **ostler:** read the stack from ops/ with one secret source ([f848ad5](https://github.com/GabrielCpp/stablemate/commit/f848ad5093b7d4f51d7039eacdca6a7b2337e282))
* **workflows:** add pr and commit delivery modes to the coder ([8bab7b8](https://github.com/GabrielCpp/stablemate/commit/8bab7b8ddf9c1a64b0d908a7d9adb34d81b82995))
* **workflows:** add workhorse-new to scaffold a workflow with a check ([cca3f20](https://github.com/GabrielCpp/stablemate/commit/cca3f20f1f1c9d6e8cc453412d30532546b5fb37))
* **workflows:** carve inline endpoints after each okf-book turn ([1b3ebb7](https://github.com/GabrielCpp/stablemate/commit/1b3ebb7bbf7374c805b918efdd6644b0a490b1a5))
* **workflows:** carve oversized pages after each okf-book turn ([b3f08c7](https://github.com/GabrielCpp/stablemate/commit/b3f08c7f24d6d3fba248a16f84578b9face88631))
* **workflows:** give each coder qa run its own stack copy ([f1633d4](https://github.com/GabrielCpp/stablemate/commit/f1633d4a8137c9d190742685bddc616b2284760c))
* **workflows:** give each coder story one dev owner ([0860050](https://github.com/GabrielCpp/stablemate/commit/0860050340ffab3aa4aa824415dc445638ffbfe1))
* **workflows:** have a lead read a failed book lap before any repair ([e5d7ac2](https://github.com/GabrielCpp/stablemate/commit/e5d7ac24ca58e90ccb52dd5937888f94a3145aae))
* **workflows:** have book writers declare how each screen settles ([8eaf653](https://github.com/GabrielCpp/stablemate/commit/8eaf6532863563bb54022589291af5d03b1e0a2d))
* **workflows:** hold a run's stack copy under its own process ([497b35f](https://github.com/GabrielCpp/stablemate/commit/497b35fd6e3efb9983a370258b7abab40d4d3f1f))
* **workflows:** keep one okf book owner conversation across laps ([a8083cf](https://github.com/GabrielCpp/stablemate/commit/a8083cf0681662404d9dd0de933663885a571268))
* **workflows:** key a repo by its agents.yml name before its directory ([9784079](https://github.com/GabrielCpp/stablemate/commit/9784079003f4a55e9cb96aeb59924ddc8c10d925))
* **workflows:** lead the page check before its repair ([787d3a0](https://github.com/GabrielCpp/stablemate/commit/787d3a0bd4a8b62b8d145f7af3c1d4d4c5bb0e89))
* **workflows:** let a book writer relink other books into its book ([45640bb](https://github.com/GabrielCpp/stablemate/commit/45640bb0cd784e167f9c41850d61a23501303abe))
* **workflows:** let the okf book owner delete pages from its book ([26a985f](https://github.com/GabrielCpp/stablemate/commit/26a985f5c010cc307354c708d41c405a2458236d))
* **workflows:** let the run settle its own gate ([574000d](https://github.com/GabrielCpp/stablemate/commit/574000d26a98214f308dbbb905b257ba1aa1c83f))
* **workflows:** name each product file no page of an okf book cites ([0abe086](https://github.com/GabrielCpp/stablemate/commit/0abe086bdcf22595fa46c7a03d73d37a04dc1711))
* **workflows:** one owner turn per book, with code running the gates ([03c3273](https://github.com/GabrielCpp/stablemate/commit/03c3273114574368df8efbd4da9e28831fb6b769))
* **workflows:** reread a book against the code that changed under it ([6e5f0dc](https://github.com/GabrielCpp/stablemate/commit/6e5f0dc29ab3f861b63eb1291cbf839255a3a460))
* **workflows:** route the coder's cheap seats to lookup and worker ([ccfe359](https://github.com/GabrielCpp/stablemate/commit/ccfe3598a3b2b99822677bcf095911f0fdd3a944))
* **workflows:** run QA against the story's own stack.yml copy ([8158174](https://github.com/GabrielCpp/stablemate/commit/8158174e7e7f1d497648d0c9cda91f3795e9f5d3))
* **workflows:** send a refused book commit to a turn that fixes it ([eea9471](https://github.com/GabrielCpp/stablemate/commit/eea9471d54d57549cb012d191780de7f3f1a8059))
* **workflows:** show a slow per-scenario fixture on its page ([a2bc28d](https://github.com/GabrielCpp/stablemate/commit/a2bc28d43691b5ccbb9488e63c3d80026f3559f7))
* **workflows:** stop a book pass at twelve repeats of one failure ([1a39f5f](https://github.com/GabrielCpp/stablemate/commit/1a39f5fa6e80c2f460bd8062f86efe6ee8ce16fd))


### Bug Fixes

* **workflows:** allow workhorse-agent 4.x, ostler 3.x ([421014b](https://github.com/GabrielCpp/stablemate/commit/421014bd0bcab61e063f39030a08afd019ebb734))
* **workflows:** answer stop and reload between scenarios ([19eac29](https://github.com/GabrielCpp/stablemate/commit/19eac29ab81a95e5e4109d33eabeba47c8326156))
* **workflows:** ask the okf book owner for a book sized to the app ([7274ff5](https://github.com/GabrielCpp/stablemate/commit/7274ff51069e5d7d3ebb7cd100826c7a7aafcc12))
* **workflows:** ask the operator about a qa tool no repository opts in ([600ecf0](https://github.com/GabrielCpp/stablemate/commit/600ecf09667aca4f46a0238bcb21e7d3db8d9e2e))
* **workflows:** block a fix-drain item that needs a deployed environment ([8c29cce](https://github.com/GabrielCpp/stablemate/commit/8c29cce482a882c766159845c45512bca1a40fa9))
* **workflows:** block a run the runner stopped instead of lapping it ([532720f](https://github.com/GabrielCpp/stablemate/commit/532720f8295edd8cb0cc1b9f13709c31bef0e46c))
* **workflows:** bring a resumed exercise's server back up ([b0f6ee4](https://github.com/GabrielCpp/stablemate/commit/b0f6ee47aee9781ab0843741c9afe79badc8e0b3))
* **workflows:** bring the stack up again when a resume finds it dead ([9b52b41](https://github.com/GabrielCpp/stablemate/commit/9b52b41a31dc03b277f0fe938f5bc2cb26482974))
* **workflows:** bring up and tear down the leased run's own stack ([bc722aa](https://github.com/GabrielCpp/stablemate/commit/bc722aa18c7ef86e5d308cec79cc7cd4ec9228d5))
* **workflows:** bring up no stack for a book that serves nothing ([a0fcb80](https://github.com/GabrielCpp/stablemate/commit/a0fcb80e19abee87d5ff5f9a2be051b49f107175))
* **workflows:** charge a shared navigation gap once to its owner page ([a1836b8](https://github.com/GabrielCpp/stablemate/commit/a1836b82161493f917bc710e40f96ed1512c3d86))
* **workflows:** check the pages an okf book owner's capped turn left ([061fb79](https://github.com/GabrielCpp/stablemate/commit/061fb79de2340f3fc99f5aa842b2ed168201389c))
* **workflows:** commit the follow-ups the workflow files to the backlog ([d833470](https://github.com/GabrielCpp/stablemate/commit/d833470f0b72815a7ba58d6ac1a7ac2d887997a1))
* **workflows:** commit the review settlement the workflow writes ([190fbf1](https://github.com/GabrielCpp/stablemate/commit/190fbf17d5b96feabb0ac1b88c981c0bf9b4d15b))
* **workflows:** compare a lap that stopped early only with the same stop ([9e706f3](https://github.com/GabrielCpp/stablemate/commit/9e706f37ed38389c2d5f063338ee4e8a5831a387))
* **workflows:** count an okf book call the service already hung up on ([59d55e0](https://github.com/GabrielCpp/stablemate/commit/59d55e080a73f1e1a7000f9e854943ed2e5d7646))
* **workflows:** declare dry-run replies on the schemas they fill ([729a0d4](https://github.com/GabrielCpp/stablemate/commit/729a0d4619777602776f9bd2f53b7a63716286e9))
* **workflows:** explain an obligation row's fixtures, acts and gaps ([e26ac8b](https://github.com/GabrielCpp/stablemate/commit/e26ac8be6494b7ca80d455423806a6d68c1d3855))
* **workflows:** fail an okf book page that lists behaviour not covered ([ad0cc6c](https://github.com/GabrielCpp/stablemate/commit/ad0cc6cea315e2c3a0da8eb1c5d2f286780d5828))
* **workflows:** fail an okf book run on a local service it never starts ([5355111](https://github.com/GabrielCpp/stablemate/commit/5355111d6135f55807e8bd37f1cc18cb729f907a))
* **workflows:** give okf-book scenarios the stack copy's address book ([40ba03f](https://github.com/GabrielCpp/stablemate/commit/40ba03f3197f9deaf311eab9f159994ffe37e7e3))
* **workflows:** give the okf book owner room to work page by page ([833c5b1](https://github.com/GabrielCpp/stablemate/commit/833c5b1ab855576046a0d23fa00b92378466097b))
* **workflows:** have okf book runbooks start the services the app calls ([06dbee1](https://github.com/GabrielCpp/stablemate/commit/06dbee167efa5f86f552f5c6ef59bc2ec9fa3503))
* **workflows:** have okf book writers aim the app at the api they start ([28f1ecc](https://github.com/GabrielCpp/stablemate/commit/28f1ecc338d7a75dd7b5886ab66bb810612c5cb3))
* **workflows:** have okf web journeys change data their fixture creates ([7d3f10e](https://github.com/GabrielCpp/stablemate/commit/7d3f10e72b9cf0fd0182872fe7cd42aa0dbea367))
* **workflows:** keep a 500 out of a qa plan's expected outcomes ([b61ac06](https://github.com/GabrielCpp/stablemate/commit/b61ac0670108934b67f054790238a0b711634f05))
* **workflows:** keep a wrapped link bullet a writer adds to an entry ([9bcd9d8](https://github.com/GabrielCpp/stablemate/commit/9bcd9d899137583cb92e58ef665c7ccf20ee7255))
* **workflows:** keep okf book fixtures off accounts they did not create ([e3b7a82](https://github.com/GabrielCpp/stablemate/commit/e3b7a82aeaf193e07c034b92c72b74f67591dcbe))
* **workflows:** keep the fixed repair subject when replies are refused ([fc14770](https://github.com/GabrielCpp/stablemate/commit/fc14770c5f43740f911c09fd5e831309817b2aff))
* **workflows:** keep the follow-up backlog filer a blueprint node ([906b8ae](https://github.com/GabrielCpp/stablemate/commit/906b8ae8e7a8ce139def2a90a504cf21ea87033a))
* **workflows:** keep the links of a command page a repair deletes ([2211879](https://github.com/GabrielCpp/stablemate/commit/2211879199a1d86ca8231d4c5f43e086959f549b))
* **workflows:** keep what a book's confined turns read in the tree ([7217c1e](https://github.com/GabrielCpp/stablemate/commit/7217c1e941ec422592cf561f9a5c2f096be3c13b))
* **workflows:** let a fixture's repair batch keep its request's page ([d642ab8](https://github.com/GabrielCpp/stablemate/commit/d642ab89193d45f1e82ff0a59f4a489b632f5f91))
* **workflows:** let a web book's health check name a page route ([457d4e9](https://github.com/GabrielCpp/stablemate/commit/457d4e97f77622e7525964c1d0b2962cefa44442))
* **workflows:** let an okf book owner name the side of an unplaced group ([a5873fa](https://github.com/GabrielCpp/stablemate/commit/a5873fa2e43f5d5eb65acabaac4337aec67fc5b9))
* **workflows:** let an okf journey create its data through the ui ([f6e4a12](https://github.com/GabrielCpp/stablemate/commit/f6e4a12418cc7130aa79a52235e2792f98ef4935))
* **workflows:** let the book's owner read the gate results it is sent ([a3a1be0](https://github.com/GabrielCpp/stablemate/commit/a3a1be060159e9d908f1fbe143852a5034766470))
* **workflows:** list a book's pages without its hidden folders ([8e6eff8](https://github.com/GabrielCpp/stablemate/commit/8e6eff81cb1127da0166bb785e3cad19f2bc1ecc))
* **workflows:** list qa.tool in the qa planner's call table ([3b2adb9](https://github.com/GabrielCpp/stablemate/commit/3b2adb9adb78b89bbee1746b872abee425dbbfe2))
* **workflows:** map the story's commits into the qa packet ([ce9e1bf](https://github.com/GabrielCpp/stablemate/commit/ce9e1bf877ada3a3fd68c57c4d759ec50c492b23))
* **workflows:** measure a probe-stopped lap only against its own kind ([cefa43a](https://github.com/GabrielCpp/stablemate/commit/cefa43a691e3fc5416b7be9b55c9df2fed46b43c))
* **workflows:** name a new flow page past the ones already on disk ([a301795](https://github.com/GabrielCpp/stablemate/commit/a301795ccda0b228722bc5b9bdd7909ecebfffa5))
* **workflows:** name only why the stack went down in its blocker ([25825e7](https://github.com/GabrielCpp/stablemate/commit/25825e7a6d82fd8ca20490a84c66b7c5d40d2cff))
* **workflows:** name the harness reference in the qa planner's seat ([bffbd4d](https://github.com/GabrielCpp/stablemate/commit/bffbd4dbaad221265c37da8ab3f941e2a0a09b82))
* **workflows:** offer a new flow page only for a page on no flow ([f469795](https://github.com/GabrielCpp/stablemate/commit/f46979574950031a96cc80f976691cdbd9bb2fac))
* **workflows:** own only the servers still running after every stack ([d889379](https://github.com/GabrielCpp/stablemate/commit/d889379b073c582315236b3f75f8969d4e645b38))
* **workflows:** pin scaffolded workflows to workhorse-agent 4.x ([e3c8562](https://github.com/GabrielCpp/stablemate/commit/e3c85624447c6d2436818854d27a224a672cdbd3))
* **workflows:** point a failed state check at the act that reaches it ([f968ab1](https://github.com/GabrielCpp/stablemate/commit/f968ab1f059e4b15ec543d19202369fb2d0e04af))
* **workflows:** point qa plan authors at the harness reference ([25e3291](https://github.com/GabrielCpp/stablemate/commit/25e3291b22d98972ab218566ca9515fb1084ac9a))
* **workflows:** point the book owner at the act an absent control needs ([bdb0f2a](https://github.com/GabrielCpp/stablemate/commit/bdb0f2a8690c71cb5f687136101651526ce67be2))
* **workflows:** print a path in the workhorse-new install hint ([17399c3](https://github.com/GabrielCpp/stablemate/commit/17399c3defba8d80039a35c2b03c017c190a425b))
* **workflows:** print each problem whole in a writer's own check ([be21a7c](https://github.com/GabrielCpp/stablemate/commit/be21a7c9b355a39b329b89763ca9282ee431d229))
* **workflows:** prove deployed state from the repositories, never ask ([bd44358](https://github.com/GabrielCpp/stablemate/commit/bd44358432b5124a3a9cceeedd6afe73b4ad8575))
* **workflows:** refuse a check argument that names no page ([b443f67](https://github.com/GabrielCpp/stablemate/commit/b443f67027a888e4a83094f8ed3f58882942dd1a))
* **workflows:** refuse a writer that moves ostler's index into the book ([9d8220a](https://github.com/GabrielCpp/stablemate/commit/9d8220a519cea4867eb59840fb745611e8b21b1b))
* **workflows:** render agent files before the restamp commit ([c989ab0](https://github.com/GabrielCpp/stablemate/commit/c989ab0c4994222c392aaaca4e92e6a1cd297193))
* **workflows:** repair again while a book check finds fewer problems ([837f9db](https://github.com/GabrielCpp/stablemate/commit/837f9db3fad7a2c231d7af4b23841ae0b3ec6d19))
* **workflows:** replace the last repair's oversized blockers ([c59bec1](https://github.com/GabrielCpp/stablemate/commit/c59bec150367bc5be26087b6deab14a3e798688f))
* **workflows:** report an unchecked book on its flow pages ([a81ba15](https://github.com/GabrielCpp/stablemate/commit/a81ba15f12f526c55f7fb17ab1936cb5962519e5))
* **workflows:** rerun a check once the qa tools it may invoke change ([425798b](https://github.com/GabrielCpp/stablemate/commit/425798b157a59021fcdf3235343e633bcc18ea88))
* **workflows:** rerun only the blocked pages still in the book ([a9fb30f](https://github.com/GabrielCpp/stablemate/commit/a9fb30fa80b92d82154784cb4e0fc53ef2eee213))
* **workflows:** run a book's journeys before its pages ([99b48f2](https://github.com/GabrielCpp/stablemate/commit/99b48f22689067c88f0011f1fc85202c792f3a57))
* **workflows:** run a command-line book's lap beside a served book ([b204fb0](https://github.com/GabrielCpp/stablemate/commit/b204fb06b311a754b2d32de2cb6f39f318d82f83))
* **workflows:** run the scored qa plan against the copy's address book ([b33fbd1](https://github.com/GabrielCpp/stablemate/commit/b33fbd11107804ce4a830f0c0bd791bc928a540d))
* **workflows:** say how many hidden okf writer lines start a failure ([ef518d7](https://github.com/GabrielCpp/stablemate/commit/ef518d70979a4aad4cfc2d68fd20aebbbf291daa))
* **workflows:** say in a book gate which side each blocker waits on ([b9fd73d](https://github.com/GabrielCpp/stablemate/commit/b9fd73dd8c0764a8513c25654121d35174e8b2a0))
* **workflows:** say which lap an okf lead's escalation reason read ([aa696ba](https://github.com/GabrielCpp/stablemate/commit/aa696ba1bb3f6b1a4aecde818677afb4123ab8f0))
* **workflows:** say why a book declared unexercised has no plan ([8602785](https://github.com/GabrielCpp/stablemate/commit/8602785415848c6a293eb06d68258653ad11da49))
* **workflows:** scaffold new workflows against workhorse 3.1 ([afd2551](https://github.com/GabrielCpp/stablemate/commit/afd2551598885ddc0e0cfb769a9a83e9e13d5949))
* **workflows:** send a claim the check says how to restate to the book ([d84f291](https://github.com/GabrielCpp/stablemate/commit/d84f2917e6a0de2dc1534ec364712a8cf244c04f))
* **workflows:** send a run stopped on a repeat to the book's owner ([a6e49eb](https://github.com/GabrielCpp/stablemate/commit/a6e49eb110e03f163e490c366d83d9514811c5ae))
* **workflows:** send a section alone when one read of its sources fits ([6a61f40](https://github.com/GabrielCpp/stablemate/commit/6a61f4065d9a219bf5f099903d556a4dc81ade8a))
* **workflows:** send a stack that cannot come up to its runbook's writer ([9ee3fda](https://github.com/GabrielCpp/stablemate/commit/9ee3fdaaa178d4b273c440a61401a2a6eec0a9d2))
* **workflows:** send a stack that stopped serving to its runbook writer ([d7abdf0](https://github.com/GabrielCpp/stablemate/commit/d7abdf071aea22f3a16f94425ff87b47d8762b8e))
* **workflows:** send an answered okf gate escalation to its writer ([50d4062](https://github.com/GabrielCpp/stablemate/commit/50d4062b7593bdff5b64e29ee1dc7713c36245f0))
* **workflows:** send no repair turn to a batch with nothing left ([3ea6dde](https://github.com/GabrielCpp/stablemate/commit/3ea6dde8e6fb26db189eb6e5d0d67724762d3b09))
* **workflows:** show a changed file's diff without blank lines between ([a0f5b12](https://github.com/GabrielCpp/stablemate/commit/a0f5b1277aa959d07e1977eeb772255d17fb1ed6))
* **workflows:** show the operator's answer to each owner once ([b5dab83](https://github.com/GabrielCpp/stablemate/commit/b5dab830ac38ef1d3b615d88ea676ac7e6e38902))
* **workflows:** skip a follow-up the backlog already holds ([655f75c](https://github.com/GabrielCpp/stablemate/commit/655f75c92b804001ebf2ef74ffb4060087f8ed53))
* **workflows:** state that a story is local and self-contained ([69eb24d](https://github.com/GabrielCpp/stablemate/commit/69eb24dc2f5540c2365a9455e88c523589757d70))
* **workflows:** state that the infrastructure deploys to the local stack ([087b15e](https://github.com/GabrielCpp/stablemate/commit/087b15e2478fd95d8b6e09b710c3853e7f7c23f8))
* **workflows:** stop a writer job still running when the turn settles ([dea80ff](https://github.com/GabrielCpp/stablemate/commit/dea80ff948c6ad6c6684a34db18edbc6fefeb79c))
* **workflows:** stop at the operator on a large book with no entry page ([61dea23](https://github.com/GabrielCpp/stablemate/commit/61dea23ac9dea5735ed293eeee0992bc15064455))
* **workflows:** stop telling the okf book owner a smaller book wins ([fa97721](https://github.com/GabrielCpp/stablemate/commit/fa9772135027da93e6b54edeafb176597f42d641))
* **workflows:** tell an okf writer a screen no control reaches is app's ([39b3bc4](https://github.com/GabrielCpp/stablemate/commit/39b3bc4d3173aaee46139277e1ac98d08410a58f))
* **workflows:** tell the docs agent to restamp nodes a story staled ([7e6bad5](https://github.com/GabrielCpp/stablemate/commit/7e6bad521d7dbd277023a92c9aad6b767be1de16))
* **workflows:** tell the writer when a book declares no check ([d176a7b](https://github.com/GabrielCpp/stablemate/commit/d176a7bdd449dbd93a0a2a32b034d7f00ffbbd45))
* **workflows:** treat every failure a story meets as the story's own ([0733096](https://github.com/GabrielCpp/stablemate/commit/0733096138d9df71bcc969e3895421b28f608e3b))
* **workflows:** wait as long as the writer's shell allows on a run ([80a69a2](https://github.com/GabrielCpp/stablemate/commit/80a69a2d46041f4bd72263bbb5c7cb01e4f4f6d2))
* **workflows:** write an empty entries page again once a page roots it ([0ada66e](https://github.com/GabrielCpp/stablemate/commit/0ada66e126eecd1a559ed37938510e4d275e4e65))
* **workhorse:** resolve a prompt's partials beside it ([1f1c744](https://github.com/GabrielCpp/stablemate/commit/1f1c744abf9e450e5044cd07c2d62b055136b4f5))


### Code Refactoring

* **workflows:** delete the author nodes no flow calls ([9c60188](https://github.com/GabrielCpp/stablemate/commit/9c6018882b61e9803bf11328cfe5cec69017a0e3))
* **workflows:** drop the okf writer's prompt and skill token cap ([b80e33d](https://github.com/GabrielCpp/stablemate/commit/b80e33dc05340f6b3f779768d71b63c898c392a3))
* **workflows:** give story provenance its own module ([c423a37](https://github.com/GabrielCpp/stablemate/commit/c423a375a3aaaefbde781c0c2497803d5fdfe3ce))
* **workflows:** give the epic and story branches their own module ([a99f8b1](https://github.com/GabrielCpp/stablemate/commit/a99f8b150dff7975002eb1aff2c9f32fd62d8d1c))
* **workflows:** give the passed-story commit its own module ([72eb491](https://github.com/GabrielCpp/stablemate/commit/72eb491de0b256737134e07560276a6150531b29))
* **workflows:** give the service gates their own module ([befb54d](https://github.com/GabrielCpp/stablemate/commit/befb54daf2a87aaa48112587bf2462edf62826d3))
* **workflows:** give the shared author nodes their own package ([93e9b5f](https://github.com/GabrielCpp/stablemate/commit/93e9b5fb823ccf1d60c0d0ab5fd74693b472e896))
* **workflows:** give the survey backlog section one owner ([eadd7ad](https://github.com/GabrielCpp/stablemate/commit/eadd7ad36afc33d5faec3361d52f0ee9137743e2))
* **workflows:** move single-caller author nodes to their machines ([12ac513](https://github.com/GabrielCpp/stablemate/commit/12ac5136e1958399fc6fb615c557608af136e10e))
* **workflows:** stop carving the okf book into small pages ([9ebd5e6](https://github.com/GabrielCpp/stablemate/commit/9ebd5e6b8bc2542aa461c1b1c7043323bf8de268))

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v1.1.0...workhorse-workflows-v2.0.0) (2026-09-11)


### ⚠ BREAKING CHANGES

* **workflows:** the `qa_stack_manifest` param is gone; a run in flight holding it fails to reload.

### Features

* **ostler:** derive owning keys from the registry ([1f402e1](https://github.com/GabrielCpp/stablemate/commit/1f402e14dda921df072974ddaa154416f2bd84ef))
* **ostler:** doctor checks for the judgment gap ([b965a1b](https://github.com/GabrielCpp/stablemate/commit/b965a1b30e017b88efb862b99d138fceb7185685))
* **ostler:** let a config: bullet own a declared configuration file ([d87ad6f](https://github.com/GabrielCpp/stablemate/commit/d87ad6f45e1b12012c9b15848ca48af53f67178e))
* **ostler:** map diffs across source repositories ([dea798f](https://github.com/GabrielCpp/stablemate/commit/dea798f02fdbf5a397c93ef4869f8e06329f35a6))
* **ostler:** resolve stories by external key ([51da445](https://github.com/GabrielCpp/stablemate/commit/51da445af0c58e99afcc4e9eaf9f101b4b416fcd))
* **ostler:** template-outside-repeat doctor check ([f6bff33](https://github.com/GabrielCpp/stablemate/commit/f6bff3342d61c7151d20b8169736ac0907270cac))
* **ostler:** trim rows, import-graph walk, repo declaration ([7a99e80](https://github.com/GabrielCpp/stablemate/commit/7a99e808191877ccf9b450331a1ae6cb333a17a8))
* **ostler:** unspecified bullet class with grounded citation ([7b1a64f](https://github.com/GabrielCpp/stablemate/commit/7b1a64f7998d029207e46fe53cf493edcc0cb40b))
* **workflows:** adjudicate a blocked finding before the operator gate ([9d198e6](https://github.com/GabrielCpp/stablemate/commit/9d198e67e71b902328fb99a15461be0c644e9e88))
* **workflows:** answer audit packets from the verdict memo first ([06f21c2](https://github.com/GabrielCpp/stablemate/commit/06f21c256885a6e96946e2c03bfb952baba5ed65))
* **workflows:** author approved roadmaps ([3f22692](https://github.com/GabrielCpp/stablemate/commit/3f2269205fc058266ceaedc3fcf58af9d5464a71))
* **workflows:** bound the audit reviewer's provider retries ([df74b25](https://github.com/GabrielCpp/stablemate/commit/df74b25a403b754a1b779c795f02e9b4bf0862a6))
* **workflows:** budget the behavior audit in turns and passes ([84ca19f](https://github.com/GabrielCpp/stablemate/commit/84ca19f9b6f7bce19b908d053680abea2ebb504f))
* **workflows:** build OKF docs from story source diffs ([f236b42](https://github.com/GabrielCpp/stablemate/commit/f236b42fa01da1937914b12081ddfb5d93a2f5c6))
* **workflows:** carry book limitations into the audit packets ([229cb94](https://github.com/GabrielCpp/stablemate/commit/229cb949b60209002e8cbe70c8ff70eb8d800f87))
* **workflows:** carry the minted story id in commit trailers ([4e18027](https://github.com/GabrielCpp/stablemate/commit/4e180279d159eb5da23aa8b0c98d2ae11926d632))
* **workflows:** coder docs lane scopes worklist builder to story paths ([8365629](https://github.com/GabrielCpp/stablemate/commit/836562940f9fffe2c66fe45aa9f8b24e1263d20d))
* **workflows:** commit completed OKF books ([074e531](https://github.com/GabrielCpp/stablemate/commit/074e53127c692e68e29c4546656d04c1629cb236))
* **workflows:** derive the implementer's standards from the layer ([f5284ea](https://github.com/GabrielCpp/stablemate/commit/f5284ea029932fbeca0877f7d6d677e104db8550))
* **workflows:** flatten author into resumable stages ([dfc77c9](https://github.com/GabrielCpp/stablemate/commit/dfc77c9a45b3c0d274dafef36e0eeae4909e5c26))
* **workflows:** gate the okf-builder commit on a semantic audit ([ca89211](https://github.com/GabrielCpp/stablemate/commit/ca892110cd98881e098f7599738b0575a84e9e3c))
* **workflows:** give the research loop program-level judgement ([0d17f92](https://github.com/GabrielCpp/stablemate/commit/0d17f92aceb738d561c56c5b08862d8f10299b13))
* **workflows:** hold the docs prompts to the written OKF model ([9c19533](https://github.com/GabrielCpp/stablemate/commit/9c19533b9b88185ae273c1cc0e0260b2c15694e8))
* **workflows:** make the builder's verdict see drift, not just coverage ([b04ba58](https://github.com/GabrielCpp/stablemate/commit/b04ba58958b4ef086c082f88e33f01107708cfa0))
* **workflows:** map coder stories across source repositories ([e18ce1d](https://github.com/GabrielCpp/stablemate/commit/e18ce1da4a7253d8c87ccea190c0bf42515cfa14))
* **workflows:** move the research measurement out of the agent turn ([1c17318](https://github.com/GabrielCpp/stablemate/commit/1c17318f7ff7a26b7ee85c3c385e3e0f13ea2ab1))
* **workflows:** okf-builder authors the judgment layer ([30446b0](https://github.com/GabrielCpp/stablemate/commit/30446b07b34527b9591e1cf5dc9c4ba52e67b8fc))
* **workflows:** okf-builder drops the entry fork; rescan is the seeder ([1357482](https://github.com/GabrielCpp/stablemate/commit/13574821aa80286ceb33184376948c3aa56db7f6))
* **workflows:** park a stalled book on the operator gate, not a waiver ([4ed8c25](https://github.com/GabrielCpp/stablemate/commit/4ed8c2544c8539895f52f4b0c0d01079ccce074a))
* **workflows:** queue undocumented source files as behavior repairs ([0e5b729](https://github.com/GabrielCpp/stablemate/commit/0e5b7295f2aa0660918dce02cefec1473d9e5c1b))
* **workflows:** read the QA stack from the book, not a manifest path ([992079f](https://github.com/GabrielCpp/stablemate/commit/992079f609293d3bfc846af8e2cebbdad1a125a8))
* **workflows:** record what a converged book was written against ([24dc214](https://github.com/GabrielCpp/stablemate/commit/24dc2142d4eea1a720496be749d5957162e50519))
* **workflows:** refuel okf-builder's budget as each item closes ([9e86087](https://github.com/GabrielCpp/stablemate/commit/9e8608764c7e2536cf2dd464cb2311900f226a90))
* **workflows:** route difficult okf repairs to high power ([127182d](https://github.com/GabrielCpp/stablemate/commit/127182d71905fd32c55ff862541ecf80f8bbbb0b))
* **workflows:** scaffold the machine envelope into program.yml ([eac1227](https://github.com/GabrielCpp/stablemate/commit/eac12278b3ef2322d315c3e7418a900e40c2470f))
* **workflows:** scope okf-builder backfills to the squashed diff ([ab66208](https://github.com/GabrielCpp/stablemate/commit/ab6620870acb1dd6503ece462f3d734a460cc93e))
* **workflows:** seed the code fixes the book cannot make ([5dace48](https://github.com/GabrielCpp/stablemate/commit/5dace48858ce2851ee4b8a48f846fc9ffbbc50cd))
* **workflows:** separate story scope from qa invariants ([9063307](https://github.com/GabrielCpp/stablemate/commit/90633077ae6f3e9c605104f8a26be55f67c2d833))
* **workflows:** settle stale repair rows during the drain ([89ac0bc](https://github.com/GabrielCpp/stablemate/commit/89ac0bcc7458679dfec14005833eebe181b0474b))
* **workflows:** state audit links once on the claim ([c094de8](https://github.com/GabrielCpp/stablemate/commit/c094de89ee52d22946489daecd6d7d259027437b))
* **workflows:** suffix coder commits with story ids ([1ca3823](https://github.com/GabrielCpp/stablemate/commit/1ca3823e4c89a9351aac2fd092701d9e21f8dbb0))
* **workflows:** teach audit reviewer to use mixed candidate status ([f0bcd8a](https://github.com/GabrielCpp/stablemate/commit/f0bcd8aaac05f1e9aa8c972fd9315bbed5e17464))
* **workflows:** teach okf-builder the one-per repeat grammar ([19a63c4](https://github.com/GabrielCpp/stablemate/commit/19a63c4881b71ebd5c8aed2bb65b3f377fd71b0c))
* **workflows:** worklist builder composes four joins into one answer ([96896a9](https://github.com/GabrielCpp/stablemate/commit/96896a998dc4e698805acd0cf9ab66d6a78a55c4))
* **workhorse:** arm the wake file before a watcher parks on it ([ae808c2](https://github.com/GabrielCpp/stablemate/commit/ae808c273eeb0275be51e57cb8551196f5b7e15f))
* **workhorse:** let an Await say a machine owes it the answer ([b3e33ec](https://github.com/GabrielCpp/stablemate/commit/b3e33ec60b85a44c467cda4f97d9174eae544fff))


### Bug Fixes

* **ostler:** teach the relation-subject slug shape at every surface ([a2d3511](https://github.com/GabrielCpp/stablemate/commit/a2d35112c4ee17dd1b4935190795483598aee772))
* **workflows:** accept farrier's repo-prefixed ostler-okf install ([f9977b9](https://github.com/GabrielCpp/stablemate/commit/f9977b9cfd9b4fc21e89932bf37870b309d85ff0))
* **workflows:** address a group finding as the group it is about ([64887dc](https://github.com/GabrielCpp/stablemate/commit/64887dceb0eca1ca4487365025eb1fdcbe8b9052))
* **workflows:** approve author splits before stories ([00f1eba](https://github.com/GabrielCpp/stablemate/commit/00f1eba13b4a086c94a3fbae89a973bf8ec772b2))
* **workflows:** audit emits per-packet labels ([fc174fd](https://github.com/GabrielCpp/stablemate/commit/fc174fd93f473e7d560a4a385a38461c68ae7573))
* **workflows:** audit recovers from a null-ctx resume ([6b0933f](https://github.com/GabrielCpp/stablemate/commit/6b0933f4e8975cc6a2399a6394a9aca8b60b80c3))
* **workflows:** audit survives a sustained models.dev outage ([60a664e](https://github.com/GabrielCpp/stablemate/commit/60a664ec5edb0fc04b1a7ba142e4394daad747c6))
* **workflows:** author current fix-story sections ([aaae440](https://github.com/GabrielCpp/stablemate/commit/aaae4403ce8c9f6134b423a854838c40e8b0707c))
* **workflows:** clear the two type findings in the dossier node ([31c01b1](https://github.com/GabrielCpp/stablemate/commit/31c01b19283810483322cb96ade56138287db123))
* **workflows:** close repair rows whose finding stopped firing ([065dc33](https://github.com/GabrielCpp/stablemate/commit/065dc339fab31e04823eb37662cdf4f058d640c5))
* **workflows:** collect a result where the command could write it ([8756cd8](https://github.com/GabrielCpp/stablemate/commit/8756cd8810ac50f3dece4b303d7108e4a35b819b))
* **workflows:** derive adjudication prompt contract ([46eb700](https://github.com/GabrielCpp/stablemate/commit/46eb700d1bc41773699f6046e3e25d381425d64e))
* **workflows:** drain drifted okf books via registry-rendered prompts ([5bdcba9](https://github.com/GabrielCpp/stablemate/commit/5bdcba960128e9f6b6fcc0cd78e2b2f50a576e3c))
* **workflows:** emit review findings in the shape the router reads ([1845e58](https://github.com/GabrielCpp/stablemate/commit/1845e5814da6073756521b659e0fcafeec557782))
* **workflows:** escalate blocked review turns instead of logging them ([b9e4017](https://github.com/GabrielCpp/stablemate/commit/b9e4017d485a68272072c4bfc0af644b4350558d))
* **workflows:** escalate the qa lane's blocked report turns ([246d3c5](https://github.com/GabrielCpp/stablemate/commit/246d3c56924517a682c33966587e12337f9862be))
* **workflows:** fail the dev path gate on a missing plan file ([a3b1147](https://github.com/GabrielCpp/stablemate/commit/a3b1147ac157c6002cae558bba22e7b12d939be9))
* **workflows:** follow the no-root-screen code and reach's default start ([50550f4](https://github.com/GabrielCpp/stablemate/commit/50550f47f0787cf59b81f3e7d0c13a3d001669fb))
* **workflows:** gate the dev story path before the first turn ([b6ed09f](https://github.com/GabrielCpp/stablemate/commit/b6ed09fa921264bbe64674fe3f3e51151d4b9a61))
* **workflows:** gate the fix lane's story before its first turn ([30eeb0c](https://github.com/GabrielCpp/stablemate/commit/30eeb0c0d6382fa3060c0db3d3f0a10196133115))
* **workflows:** gate the reviewer's empty result instead of dying on it ([1f91ff4](https://github.com/GabrielCpp/stablemate/commit/1f91ff427818b8aa2f7ca5c4902577b271e1d5b0))
* **workflows:** group OKF scopes by source repository ([b94bb1a](https://github.com/GabrielCpp/stablemate/commit/b94bb1af99f30a2a25f73cb65e4287cd988da9e2))
* **workflows:** hold a reduced audit reply to its parent packet ([b0689fe](https://github.com/GabrielCpp/stablemate/commit/b0689fe79176392112b5f17e11b806470289afba))
* **workflows:** keep author audits within story scope ([077bda5](https://github.com/GabrielCpp/stablemate/commit/077bda5673cc7c5bb849e49b6c3a7984b4dbd7f3))
* **workflows:** keep mockup inspection ephemeral ([72c871f](https://github.com/GabrielCpp/stablemate/commit/72c871f30a8bf4c1bdf3436d2594c3cea91a3ce3))
* **workflows:** keep workflow-written files out of the repo root ([ae7659f](https://github.com/GabrielCpp/stablemate/commit/ae7659f104807107f0be89cc03721b3b94b9df17))
* **workflows:** leave pytest trees out of the source inventory ([5de5a24](https://github.com/GabrielCpp/stablemate/commit/5de5a2464ec1f73a1106a3cbd67058465a6233c0))
* **workflows:** let an artifact-only book run qa without a stack ([dd0b0db](https://github.com/GabrielCpp/stablemate/commit/dd0b0db69429739ef7c3fb4626288e1426fb60a3))
* **workflows:** make the okf-builder fixup loop terminate ([284caba](https://github.com/GabrielCpp/stablemate/commit/284caba77ee3167a1a5008244f5acb764339ca6f))
* **workflows:** name the regrouped ostler-okf skill in the okf prompts ([2e98339](https://github.com/GabrielCpp/stablemate/commit/2e98339ed042d15a152c47dc3f36edf42f951fc7))
* **workflows:** open the implement prompt with the repo's plan ([a0c62de](https://github.com/GabrielCpp/stablemate/commit/a0c62de3cbf982de9a73389d4758bddfe8d30940))
* **workflows:** park on an unusable adjudication instead of dying ([5c04c15](https://github.com/GabrielCpp/stablemate/commit/5c04c15e483db6ac6afda1d692e4d341a52e3229))
* **workflows:** park unreadable CI instead of spending repair laps ([688b7ec](https://github.com/GabrielCpp/stablemate/commit/688b7ec9d54477e6739b148f95d5d5b986fb7092))
* **workflows:** pass operator gate answers into resumed fix reasons ([5d88713](https://github.com/GabrielCpp/stablemate/commit/5d88713dcc77097344a318b530af4af950c177e7))
* **workflows:** repair a short audit reply, don't re-ask the packet ([eda33ff](https://github.com/GabrielCpp/stablemate/commit/eda33ffda830b49612922d79c2ea4f829cf66dc9))
* **workflows:** requeue stale OKF source context ([8128a74](https://github.com/GabrielCpp/stablemate/commit/8128a74bf1389bb8604059523f9eaaedf3595c45))
* **workflows:** rescan round surfaces as label ([86b5ed5](https://github.com/GabrielCpp/stablemate/commit/86b5ed5943b375f0becc03f40018c1b7014f2b6b))
* **workflows:** reserve audit delivery for author ([a54db38](https://github.com/GabrielCpp/stablemate/commit/a54db389f9b2ef85f5b059010a3a8068878a1a6c))
* **workflows:** reset the docs chains and never fake a documented turn ([867ec1d](https://github.com/GabrielCpp/stablemate/commit/867ec1dc9cc7005f02736f0ea1a6671d2ba04fac))
* **workflows:** retire a re-grounded citation on the verdict turns emit ([bbbd583](https://github.com/GabrielCpp/stablemate/commit/bbbd583cae7f98517da79f1a93534179ababcf55))
* **workflows:** scaffold every story on entry, don't branch on its age ([aaf66c3](https://github.com/GabrielCpp/stablemate/commit/aaf66c36b958fae22ae74265389a4b6d3f96642f))
* **workflows:** scope audit packets to the service being audited ([6f52d3f](https://github.com/GabrielCpp/stablemate/commit/6f52d3f20e285873c1ab720502f92bed9ded0aaa))
* **workflows:** scope author epic worklists ([925cbbf](https://github.com/GabrielCpp/stablemate/commit/925cbbfcd5c64efab9dc54d3f0c3d5c986fc7d65))
* **workflows:** scope author validation to roadmap ([b38f6cb](https://github.com/GabrielCpp/stablemate/commit/b38f6cb45c48ab388a8c7fac81916dbc0be01e0b))
* **workflows:** scope the audit's book read to the service ([a261d5d](https://github.com/GabrielCpp/stablemate/commit/a261d5d3eef71bdf2c7ca531a4626943dc6b5d1f))
* **workflows:** scope the implement prompt to one plan and block cleanly ([35a8d3d](https://github.com/GabrielCpp/stablemate/commit/35a8d3d7a149016bb3f48b6c98fd59403545488f))
* **workflows:** send a blocked re-grounding row to the gate, not the cap ([b6ce44a](https://github.com/GabrielCpp/stablemate/commit/b6ce44a5d6bdf7396112d35f1ff31204372cd1a5))
* **workflows:** skip promised server commands in check_promises ([f33f4a8](https://github.com/GabrielCpp/stablemate/commit/f33f4a887bb8f8fab990a6dde510bb001a4b35e3))
* **workflows:** stop double-prefixing the ci fix branch name ([85667c8](https://github.com/GabrielCpp/stablemate/commit/85667c8b0019df5f121a9198e36c70885c08b7bd))
* **workflows:** stop the re-scan gate naming a cause it cannot see ([3402d53](https://github.com/GabrielCpp/stablemate/commit/3402d5396bcd4d53bdc3dc202d4363d3ff27fde4))
* **workflows:** take every document location from ostler, not a param ([9d25cf8](https://github.com/GabrielCpp/stablemate/commit/9d25cf890a5356021ffe1b45640cba2d225c19e7))
* **workflows:** take the settle watermark after the rows are closed ([4c348d0](https://github.com/GabrielCpp/stablemate/commit/4c348d0705c34b52c5d864d0b1fc2d3abd7d3e3a))
* **workflows:** warn repair prompts about unread nested verify bullets ([a657b14](https://github.com/GabrielCpp/stablemate/commit/a657b1498863357c29a5dca2bfc7f3de7e895abf))
* **workflows:** worklist builder reads inventory at worklist path ([9b99387](https://github.com/GabrielCpp/stablemate/commit/9b99387881e9c100ed6cebb91f239a9db0e418fd))
* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))
* **workhorse:** treat a session id as an opaque string ([7a0c66b](https://github.com/GabrielCpp/stablemate/commit/7a0c66bdf38deb61dfc386cc1a4f24ba2941a175))


### Performance Improvements

* parallelize Python test suites ([ee2f9f2](https://github.com/GabrielCpp/stablemate/commit/ee2f9f27152cbdfca029b661cf761e95a3fd2121))
* **workflows:** audit preparation runs once per drive ([5aec0cf](https://github.com/GabrielCpp/stablemate/commit/5aec0cf52f9c1cba93a06c4eb3a5f948d732cfe7))
* **workflows:** avoid repeated author graph scans ([0f04146](https://github.com/GabrielCpp/stablemate/commit/0f041462ed507fc21f6968ee9f562fd93db58310))
* **workflows:** batch implement writes and gate runs per layer ([e7b6cc1](https://github.com/GabrielCpp/stablemate/commit/e7b6cc128d67f0eeca4bfa755824be859a9a7b25))
* **workflows:** demote mechanical QA turns to low power ([1acb33a](https://github.com/GabrielCpp/stablemate/commit/1acb33a9a5fcedc6c6c4ef6f16a73a442eb6d8cf))
* **workflows:** inline the plan into the implement turn ([7dea11e](https://github.com/GabrielCpp/stablemate/commit/7dea11e2cf9ea393d7f7cd59c0c34d3da159ebee))
* **workflows:** open implement on a fresh chain with standards inlined ([aab0450](https://github.com/GabrielCpp/stablemate/commit/aab04500e0c502684ef56fb5e13f3bcb6b52a804))
* **workflows:** review the diff directly instead of the PR recipe ([971123d](https://github.com/GabrielCpp/stablemate/commit/971123dafd37a1e4a56ac7db9a90b7fae2e71a8a))
* **workflows:** route okf turns by difficulty ([86c23fd](https://github.com/GabrielCpp/stablemate/commit/86c23fd1d3b8fa48098e7035dc58a382761d50d9))
* **workflows:** skip preserved surface mockups ([4866e14](https://github.com/GabrielCpp/stablemate/commit/4866e14dc424cf47949fb765284504b481f6187d))
* **workflows:** write author seeds in one edit ([3c593f8](https://github.com/GabrielCpp/stablemate/commit/3c593f8ede88f72a4bb54d82de6bd59039fb3217))


### Code Refactoring

* **base-library:** split the root policy into reusable ones ([1f7b976](https://github.com/GabrielCpp/stablemate/commit/1f7b976df8afc51caf24190da1d6d9d3060cebe0))
* **ostler:** own the durable QA stack, hard-cut workhorse.stack ([6191e5d](https://github.com/GabrielCpp/stablemate/commit/6191e5d5359c1675fd72fda7cf04e51a6e4a5486))
* rename the top power tiers to max and ultra ([66a017d](https://github.com/GabrielCpp/stablemate/commit/66a017d2ae8d7ba3283cb85e676a8904fa56e831))
* **workflows:** answer the findings basedpyright reports ([9c1b56f](https://github.com/GabrielCpp/stablemate/commit/9c1b56fe90b626c87dfda4d82904783d34c3cbd7))
* **workflows:** collapse the fix lane into a one-turn session ([62a16d6](https://github.com/GabrielCpp/stablemate/commit/62a16d6ee6e54530a2f6c2c14b495ed0919d9c50))
* **workflows:** collapse the plan into four sections ([5071200](https://github.com/GabrielCpp/stablemate/commit/50712007d3bd2e38cd7842432e9ba8696e7db11c))
* **workflows:** consolidate the shared coder flow helpers ([22e235d](https://github.com/GabrielCpp/stablemate/commit/22e235deca23ccd48d7e6b845b44b293eead2d55))
* **workflows:** cut every coder prompt to its consuming mechanics ([ec2c4bd](https://github.com/GabrielCpp/stablemate/commit/ec2c4bdfbb0b7017b56aeb80dc09b9f13c702615))
* **workflows:** cut the qa prompts to their mechanics ([68832fc](https://github.com/GabrielCpp/stablemate/commit/68832fc1c1d3749c4d6e8a16ab1ef1639285573d))
* **workflows:** delete the dream flow ([c60f7b1](https://github.com/GabrielCpp/stablemate/commit/c60f7b1cab97b22a2a9d671d5f7f3e5018fc807a))
* **workflows:** delete the plan-review ghost from three sites ([b13dfa4](https://github.com/GabrielCpp/stablemate/commit/b13dfa4f29c1dd0452702b90fcf461cd3a4ca694))
* **workflows:** drop the coder lanes' session_id parameter ([8db22d9](https://github.com/GabrielCpp/stablemate/commit/8db22d9c1b168bb13ef1b23dd4e9916a27f6d7c3))
* **workflows:** drop the commit blocks from the coder prompts ([b0b6eca](https://github.com/GabrielCpp/stablemate/commit/b0b6eca0690d1d1a5620add096ed6fcb5cd4bdba))
* **workflows:** drop the runbook hunt from apply-review ([71c75ea](https://github.com/GabrielCpp/stablemate/commit/71c75ea576122510f478e49bde4f58dfcdbf35ba))
* **workflows:** end the author run on a commit, not a PR ([21afb6d](https://github.com/GabrielCpp/stablemate/commit/21afb6dd55451403ae8fffa576b8002b776b2268))
* **workflows:** enforce read-only planning with a clean-tree gate ([c4bb223](https://github.com/GabrielCpp/stablemate/commit/c4bb223f2a2a09eaf3dfd804585b55a26715a4ec))
* **workflows:** extract dev flow helpers into nodes ([d5631c4](https://github.com/GabrielCpp/stablemate/commit/d5631c4dbd1c46e46f2f04bf4dc3f84a77b1ec76))
* **workflows:** flatten the two-key qa context repair turn ([2c0b914](https://github.com/GabrielCpp/stablemate/commit/2c0b914ddf1f8cd51d57456d66e1d582c740d682))
* **workflows:** fold the reuse hunt into the code review pass ([163e830](https://github.com/GabrielCpp/stablemate/commit/163e830a60c92a394d56b45c975ce7c9262e03b8))
* **workflows:** fold the three identical Docs handoffs into one ([61045f5](https://github.com/GabrielCpp/stablemate/commit/61045f5eb38c84db33619e819507f3157f28c26e))
* **workflows:** give each author flow its own prompts ([b54535e](https://github.com/GabrielCpp/stablemate/commit/b54535e2a3f557aec0d8e82623aeb1b06fb599ae))
* **workflows:** give each coder flow its own prompts ([44578fc](https://github.com/GabrielCpp/stablemate/commit/44578fcee45f843d78825845ea58ae0e9f2a8d88))
* **workflows:** give each okf_builder flow its own prompts ([232d552](https://github.com/GabrielCpp/stablemate/commit/232d552220c75c5084056353c1979d02e21585c5))
* **workflows:** give the builder one prepare and one drain ([576a679](https://github.com/GabrielCpp/stablemate/commit/576a679072db6378daef181edb60178b3adee9d3))
* **workflows:** load standards from the installed skills ([e7c5633](https://github.com/GabrielCpp/stablemate/commit/e7c563359af821bb74e56c5584a96ac7d259ff96))
* **workflows:** make refine-plan two repairs, not one re-plan ([ab461c3](https://github.com/GabrielCpp/stablemate/commit/ab461c3708bf61f908018ddd16dc27de91206590))
* **workflows:** move the coder main graph into main/ ([473e6c6](https://github.com/GabrielCpp/stablemate/commit/473e6c69ec21a33d7722c588602588340f7b33a8))
* **workflows:** parse technical code pointers, don't regex them ([f49baed](https://github.com/GabrielCpp/stablemate/commit/f49baed313b5405dbbd27b044453369308577e3e))
* **workflows:** put the story id in the footer only ([2dbd920](https://github.com/GabrielCpp/stablemate/commit/2dbd920457e08677150323896ecf96b66814234c))
* **workflows:** read the queue epic back instead of threading it ([46a10ef](https://github.com/GabrielCpp/stablemate/commit/46a10ef7501ca5ff6cbeb5aee5c9a506aa235cb3))
* **workflows:** read the standing QA plan off disk, not the loop ([bcbc9e2](https://github.com/GabrielCpp/stablemate/commit/bcbc9e23223eaf068f7c5c7e2daae5378a92bc69))
* **workflows:** render coder output contracts from the schemas ([381ec51](https://github.com/GabrielCpp/stablemate/commit/381ec51f3b6dbe6cf8eb99a58da460667eea1682))
* **workflows:** render the review scope the flow already resolved ([ae3d913](https://github.com/GabrielCpp/stablemate/commit/ae3d9131a2762eb4c66c4fb8b9983f93fe61c4b1))
* **workflows:** replace main's nested drain with a fix handoff ([88bcb99](https://github.com/GabrielCpp/stablemate/commit/88bcb991d53ce5cac598dddaa2f123eb5c861dc4))
* **workflows:** restate the schema rule for literal statuses ([4520c9e](https://github.com/GabrielCpp/stablemate/commit/4520c9ea010cbd9daf35f7a2aacfdc069fdc51ed))
* **workflows:** reuse Ostler story provenance ([813cd62](https://github.com/GabrielCpp/stablemate/commit/813cd62b8c9f29c69d0a80f0434604219f81cb3e))
* **workflows:** say why each okf-builder transition is taken ([35182f8](https://github.com/GabrielCpp/stablemate/commit/35182f864613766a35ccfcd0287c655e73a1d071))
* **workflows:** share one operator resolver prompt across the lanes ([e586d4b](https://github.com/GabrielCpp/stablemate/commit/e586d4b5bc774536d0f2cc90a1e5fd5909dd58a0))
* **workflows:** shrink the qa loop via output readback ([c57b988](https://github.com/GabrielCpp/stablemate/commit/c57b9885d38f94a9a7e45cecf8a3f8daa4bb90a4))
* **workflows:** split review findings on confidence in python ([595e0de](https://github.com/GabrielCpp/stablemate/commit/595e0de51d49d36b56b26377ff873b46e59a4ce2))
* **workflows:** split the fix-drain repair lap into its own prompt ([e08bc39](https://github.com/GabrielCpp/stablemate/commit/e08bc39ca4ae2e7be5b502fc87c9a634c75d74cd))
* **workflows:** stop re-reading standards the session already holds ([a67e60d](https://github.com/GabrielCpp/stablemate/commit/a67e60d8e317956f56e3e03a50d0a2deb673653a))
* **workflows:** trim the dev prompts to their own lane ([68b1c4e](https://github.com/GabrielCpp/stablemate/commit/68b1c4e799ad145f61d522e7d95e28fd728580d7))
* **workflows:** type audit unresolved items as UnresolvedItem rows ([2fd86dd](https://github.com/GabrielCpp/stablemate/commit/2fd86ddb923380fb1d30c685742b5aa76da703f6))
* **workflows:** type dev agent statuses as required literals ([1ac23d8](https://github.com/GabrielCpp/stablemate/commit/1ac23d820db955d372261902fe82cea0f1154ebd))
* **workflows:** type docs statuses and bundle the docs loop ([971abf0](https://github.com/GabrielCpp/stablemate/commit/971abf01dfd957e102db1839ddb37369e5e9bde9))
* **workflows:** type fix_ci statuses and drop its dead summary ([0d7159a](https://github.com/GabrielCpp/stablemate/commit/0d7159adc5c06c4e9907ac01c991fcc624b37fbe))
* **workflows:** type genesis classifications, reuse the kit ([e1f61d7](https://github.com/GabrielCpp/stablemate/commit/e1f61d7384d2d56d6d756065bf36db493b44a953))
* **workflows:** type main statuses and drop its dead promise fields ([30b3a9a](https://github.com/GabrielCpp/stablemate/commit/30b3a9a30807dbf5a59c7ae9d6cf2e9e077150b8))
* **workflows:** type qa statuses as literals ([fa5748a](https://github.com/GabrielCpp/stablemate/commit/fa5748a1e7fb234ff9f48e8bacd37266d6fcdd84))
* **workflows:** type review statuses and bundle its loop state ([8997019](https://github.com/GabrielCpp/stablemate/commit/899701953513631f2e25b983c22beea6fef06a59))

## [1.1.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v1.0.0...workhorse-workflows-v1.1.0) (2026-08-14)


### Features

* **ostler:** add created/removed paired lifecycle checks ([6eaf82a](https://github.com/GabrielCpp/stablemate/commit/6eaf82aafba0e362d367265b825901202cd933d1))
* **ostler:** record response status in the browser diagnostics ([a88591b](https://github.com/GabrielCpp/stablemate/commit/a88591b103c868b7f10fca9de904a4f462cda79c))
* **ostler:** record the whole console and network in the diagnostics ([79e7f91](https://github.com/GabrielCpp/stablemate/commit/79e7f917c46b747474dc5ddac346a4c47700f28c))
* **ostler:** record why a failed request failed, not just its url ([c7c0ddc](https://github.com/GabrielCpp/stablemate/commit/c7c0ddc921278710209ddc54d2e9fa963d9c92f9))
* **ostler:** stamp a schema key on the browser diagnostics ([105cb82](https://github.com/GabrielCpp/stablemate/commit/105cb822c15f6c73c38bb86c5e72b4be1ee6e2b5))
* **workflows:** author the QA plan as a python module ([622e4dd](https://github.com/GabrielCpp/stablemate/commit/622e4dd3768b394805348446584d737a32bebf68))
* **workflows:** backfill a missing placement from the running ui ([3a7cd25](https://github.com/GabrielCpp/stablemate/commit/3a7cd2594b7d2a5573757618775033b95043f641))
* **workflows:** gate okf-builder on every non-waived finding ([d581fe1](https://github.com/GabrielCpp/stablemate/commit/d581fe17f0849fcccb526feb3048c27ab5c292cf))
* **workflows:** give each okf repair item a prompt for its own code ([03502c9](https://github.com/GabrielCpp/stablemate/commit/03502c94069b90060935ec64853d54b8b18c9187))
* **workflows:** give the qa planner its plan-context and a dry run ([b53e1ea](https://github.com/GabrielCpp/stablemate/commit/b53e1eaf15c44c740414a4c3d49f4ff90443a429))
* **workflows:** hand a spent QA budget to the operator before giving up ([f9f3678](https://github.com/GabrielCpp/stablemate/commit/f9f3678bccc44e4087921540254555a7e35766b6))
* **workflows:** hold the QA lane to a wall-clock budget ([014ebcb](https://github.com/GabrielCpp/stablemate/commit/014ebcb8cbdd92b4f5a1b96e0d11c3b579ab3ea8))
* **workflows:** let the author ratify a documentation block ([b8c2b9e](https://github.com/GabrielCpp/stablemate/commit/b8c2b9ea4381166c47a49a568084dd3b036db6d3))
* **workflows:** let the coder QA lane run its scenarios sandboxed ([95d05df](https://github.com/GabrielCpp/stablemate/commit/95d05dfc7ccdfd2c1fb3c0aeb533af23deaa52fb))
* **workflows:** queue undeclared obligations as okf-builder worklist ([ee41f57](https://github.com/GabrielCpp/stablemate/commit/ee41f5785604689964f4e14090ba41855e68d907))
* **workflows:** read the qa context in slices, not whole, in plan-qa ([30fa1f8](https://github.com/GabrielCpp/stablemate/commit/30fa1f872db65a779102356135894e45e4a2c8c2))
* **workhorse:** keep machine scratch in the cache, not the repo ([0f9c663](https://github.com/GabrielCpp/stablemate/commit/0f9c6638767c2dc71afd8f96f0b54727e2b016d0))


### Bug Fixes

* **ostler:** say a required section is missing, not empty ([809b18c](https://github.com/GabrielCpp/stablemate/commit/809b18cd56e44f3314b8d54cebbc46c9822ac06c))
* **workflows:** bound checkpointed docs repair notes ([3742fbc](https://github.com/GabrielCpp/stablemate/commit/3742fbc18ac0e33567b083d2aff1cc283fb4bf72))
* **workflows:** catch a set-aside epic branch up to its base ([659dd3d](https://github.com/GabrielCpp/stablemate/commit/659dd3d8b34da092e880c8fb12fef7bfba792345))
* **workflows:** clear the review sidecars before each review round ([7571ac7](https://github.com/GabrielCpp/stablemate/commit/7571ac7672223306136808e1fa5aab42ce858627))
* **workflows:** close a prose qa finding by editing the prose ([51e9c2f](https://github.com/GabrielCpp/stablemate/commit/51e9c2f779ec3332af3a6b2fcb8d6ed239eb8283))
* **workflows:** compact repeated docs gate findings ([5a16eb3](https://github.com/GabrielCpp/stablemate/commit/5a16eb33660eaa10e0d032e371e5130182420dec))
* **workflows:** continue reducing docs gate repairs ([f42595c](https://github.com/GabrielCpp/stablemate/commit/f42595c4a39d270e71ccb3dd997249b8e4671ece))
* **workflows:** declare the playwright extra the coder's qa stage needs ([568a465](https://github.com/GabrielCpp/stablemate/commit/568a46510012ce4f728d3ed652eacdd0ff0ca9c9))
* **workflows:** escalate a QA repair that changes nothing ([eaf2899](https://github.com/GabrielCpp/stablemate/commit/eaf2899e088b79cd10d7db2dfc743303ecbe6898))
* **workflows:** forbid the qa fixer from rewriting the evidence ledger ([2139a55](https://github.com/GabrielCpp/stablemate/commit/2139a552c70ca3710094450853e5cf56f2667df6))
* **workflows:** gate CI on the branch the epic PR is opened from ([151b0d1](https://github.com/GabrielCpp/stablemate/commit/151b0d1ddd04805a7f70e04e70912b98c047f522))
* **workflows:** gate on a repeated identical blocked qa bundle ([5d64207](https://github.com/GabrielCpp/stablemate/commit/5d64207575a5bd204276796e1e4e2682c8dc0193))
* **workflows:** group repair items by the node the ref really names ([cc10736](https://github.com/GabrielCpp/stablemate/commit/cc10736d7988aab83552a7b533090e85c1faf7c8))
* **workflows:** hand branch_epic the run dir so its claim ledger fills ([370fb34](https://github.com/GabrielCpp/stablemate/commit/370fb34d61b1f0454244527466c33812f0da26db))
* **workflows:** hold the QA context join point to the plan budget ([0b28885](https://github.com/GabrielCpp/stablemate/commit/0b288857f472a1faf9c95b90015f9e3949734062))
* **workflows:** judge okf coverage across scenarios, not one by one ([b2c0ef6](https://github.com/GabrielCpp/stablemate/commit/b2c0ef6f87db070e68831a6357af314ba78b1ba4))
* **workflows:** keep a story's Dependencies section through a rewrite ([906671e](https://github.com/GabrielCpp/stablemate/commit/906671e69fc0f9dd960fea6d7226faf8537a5b4d))
* **workflows:** let a blocked qa fix reach the operator gate ([500750f](https://github.com/GabrielCpp/stablemate/commit/500750fcda63dd9fc1e1a7147753a1e0589f0e06))
* **workflows:** let a drain return to an epic branch it cut itself ([d0253a9](https://github.com/GabrielCpp/stablemate/commit/d0253a9a372c68de54464caf8420c178e75d7536))
* **workflows:** make the okf-build scratch ignore itself ([a95b31f](https://github.com/GabrielCpp/stablemate/commit/a95b31f5acb6e02416402a209e4fb9c5b7303243))
* **workflows:** make the QA lane's wall clock advisory ([a02e58d](https://github.com/GabrielCpp/stablemate/commit/a02e58d2478c1a19b71fc8c63f4bd8728bad6a58))
* **workflows:** make the QA plan defeat the test runner's cache ([351395d](https://github.com/GabrielCpp/stablemate/commit/351395d315a623aafd4d06b868709b889d2d7d7d))
* **workflows:** put the check vocabulary in the repair prompt ([4518672](https://github.com/GabrielCpp/stablemate/commit/451867205a3b2d4fc20d31e9f5ab9f3a83fc00a3))
* **workflows:** repair a cut-off QA plan instead of failing the run ([ef29840](https://github.com/GabrielCpp/stablemate/commit/ef298401d102f19a65642e928216dd26e856e7c1))
* **workflows:** require a listing before a QA absence finding ([efffb5d](https://github.com/GabrielCpp/stablemate/commit/efffb5d17a72f03ac390e05095c757d2d592c124))
* **workflows:** require qa evidence for universal claims ([0b1461b](https://github.com/GabrielCpp/stablemate/commit/0b1461b67fcfd9160fae42ef15c965ea3d5d0635))
* **workflows:** require structured evidence for docs checks ([d77064f](https://github.com/GabrielCpp/stablemate/commit/d77064f2e6579602b1596b0bdac48a48f3e0e7c6))
* **workflows:** require terminal evidence for print qa ([9436b4f](https://github.com/GabrielCpp/stablemate/commit/9436b4f8ea401e58c7e83022561d45787634a182))
* **workflows:** retry qa after docs repair ([581a2ec](https://github.com/GabrielCpp/stablemate/commit/581a2ec08b27952a34a1d7fc2b748c80c3725966))
* **workflows:** route an overlong bullet to a grounded repair ([8cf0abc](https://github.com/GabrielCpp/stablemate/commit/8cf0abc15f0e17e6be0144ab654b5689b6c2329b))
* **workflows:** show the doctor's expected form in the rework brief ([678a8d1](https://github.com/GabrielCpp/stablemate/commit/678a8d10391676079abdd6009f87d59a7590ce8a))
* **workflows:** steer qa repairs to declared checks ([5cc6831](https://github.com/GabrielCpp/stablemate/commit/5cc6831cf6aaf128e827dcf432de98632d9518a2))
* **workflows:** stop a named doc file owning every error already in it ([2aa7a6e](https://github.com/GabrielCpp/stablemate/commit/2aa7a6ec51e9f1f5fe277db96ee4b683297c5d9f))
* **workflows:** stop a plan repair from stalling the fix loop ([0e20a19](https://github.com/GabrielCpp/stablemate/commit/0e20a19c920b4a859ef97449dafd188113e3c4ca))
* **workflows:** stop a spent plan budget re-running the failing QA plan ([c71a8bc](https://github.com/GabrielCpp/stablemate/commit/c71a8bca64e7a7f1a008efb05e129105dda7ea77))
* **workflows:** stop entering the plan review once it is demoted ([072414f](https://github.com/GabrielCpp/stablemate/commit/072414f1728e71cdcc929f88f849f9b2d4c8a006))
* **workflows:** stop the QA audit blocking a pass forever ([db005d0](https://github.com/GabrielCpp/stablemate/commit/db005d061b65b09ebbfeb04acaffadc145daba30))
* **workflows:** stop the qa operator granting its own verdict ([670ade6](https://github.com/GabrielCpp/stablemate/commit/670ade6f53a21a14ad6bffc5f9a39d66dfc2e796))
* **workflows:** teach the qa planner $QA_DIR, not a pinned ledger path ([cdcd299](https://github.com/GabrielCpp/stablemate/commit/cdcd29941e63130d730b1cf40b41bff3e316c771))
* **workflows:** teach the qa planner what a vacuous assertion looks like ([f8de205](https://github.com/GabrielCpp/stablemate/commit/f8de20573cb95cd314b756e96ee32cfca2c646e9))
* **workflows:** try the other hypothesis before abandoning a QA story ([c6b839b](https://github.com/GabrielCpp/stablemate/commit/c6b839bbe8aa88bddd6bafd4d3655c0b1a6d281c))


### Performance Improvements

* **workflows:** cap the QA plan turns and cut their lap budgets ([3bafc23](https://github.com/GabrielCpp/stablemate/commit/3bafc23eaa70753006c7ee225f065fc782d78351))


### Code Refactoring

* **workflows:** delete the QA plan reviewer the machine replaced ([b619a7e](https://github.com/GabrielCpp/stablemate/commit/b619a7e869f9054ce5d595d70ba441f1ab102a1a))
* **workflows:** drop the dependencies.json story fallback ([41716da](https://github.com/GabrielCpp/stablemate/commit/41716da82f60a2f362e760ad11771c6eee524730))
* **workflows:** queue one okf repair item per node and code ([f079020](https://github.com/GabrielCpp/stablemate/commit/f079020c1d7480e76c0e325dc0ecb3fcf3de5825))
* **workflows:** stand the qa stack up before the plan is written ([c3d2848](https://github.com/GabrielCpp/stablemate/commit/c3d28485daf37d953f51d09fd5aeb51886d4533e))

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
