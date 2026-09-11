# Changelog

## [2.0.1](https://github.com/GabrielCpp/stablemate/compare/workhorse-workflows-v2.0.0...workhorse-workflows-v2.0.1) (2026-09-11)


### Bug Fixes

* **workflows:** cap workhorse-agent and ostler at the 3.x/2.x majors ([763ef79](https://github.com/GabrielCpp/stablemate/commit/763ef79b96350f0380b552baa13317d78d3c203b))

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
