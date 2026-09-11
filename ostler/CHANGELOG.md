# Changelog

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/ostler-v1.1.0...ostler-v2.0.0) (2026-09-11)


### ⚠ BREAKING CHANGES

* **core:** bump stablemate config schema to v2
* **ostler:** `ostler.waivers`, `Okf.add_doctor_waiver`, the `waived` field on doctor findings and the `waivers` epoch input are gone; a `docs/doctor-waivers.json` file is no longer read. Coverage waivers (`coverage --waivers`) are a different concern and stay.

### Features

* **core:** let a power tier scale every wall-clock budget ([50b5081](https://github.com/GabrielCpp/stablemate/commit/50b5081d3930a22e0cae23ed2c989eb56af71d3c))
* **core:** persist a nested config table, and groom's attend settings ([3c51cca](https://github.com/GabrielCpp/stablemate/commit/3c51cca625bf29d50092cbb1cbd2a7399bec8cb3))
* **ostler:** add known-defect, a code-fault record with two exits ([8654c88](https://github.com/GabrielCpp/stablemate/commit/8654c88551d99a7494b15535c828a187d878994c))
* **ostler:** add story-for-node query over code-ref trailers ([9f89954](https://github.com/GabrielCpp/stablemate/commit/9f89954175690edb907732fc56266f457e8ac8e9))
* **ostler:** admit mixed candidate status for internal-and-relevant ([b3e6d18](https://github.com/GabrielCpp/stablemate/commit/b3e6d18f6624e62e3ab485ea36367b5bc580deb8))
* **ostler:** advance one file's watermark without rewriting the catalog ([9ceae73](https://github.com/GabrielCpp/stablemate/commit/9ceae73474e9ee90bf86306b6b300261316477f7))
* **ostler:** ask one question about what a book owes its code ([8c9d53b](https://github.com/GabrielCpp/stablemate/commit/8c9d53b7b25bef49af3191750f8e436ef6750781))
* **ostler:** audit tier-1 candidates by default ([6ed3e36](https://github.com/GabrielCpp/stablemate/commit/6ed3e36790f1582f2d6b385a1fd0eef0d71a0c87))
* **ostler:** autofix a null equals into an absent check ([d97e6aa](https://github.com/GabrielCpp/stablemate/commit/d97e6aa3abe62337cea4d0fcfd11e8c53063013c))
* **ostler:** autofix drifted verify: test citations into tests: ([51b83cd](https://github.com/GabrielCpp/stablemate/commit/51b83cdb42b166bbe3422a217984e1902630b267))
* **ostler:** carry a story-conflict finding for the operator gate ([cb894a6](https://github.com/GabrielCpp/stablemate/commit/cb894a6bc5f3a4800ef43c8a0d73e9fa77493233))
* **ostler:** classify seed visual design ([b582ed2](https://github.com/GabrielCpp/stablemate/commit/b582ed299bfb06c18cc4d3b48b76353fb2bb79e0))
* **ostler:** classify story acceptance criteria ([1496a39](https://github.com/GabrielCpp/stablemate/commit/1496a39867139084ff6841e7754175776f4f05de))
* **ostler:** compile repeated families into qa obligations and plans ([111a749](https://github.com/GabrielCpp/stablemate/commit/111a74987d806deeda849014471908a664f4b77b))
* **ostler:** concept judgment keys — rule:, prefers:, deprecates: ([bba5372](https://github.com/GabrielCpp/stablemate/commit/bba5372732fe2df0f407a0b2d79a2346459bb9f1))
* **ostler:** declare detail: on every implementation-bearing node type ([c09a13d](https://github.com/GabrielCpp/stablemate/commit/c09a13d98b5fad5fdffe2e2379756d9a75ed880c))
* **ostler:** delete the doctor waiver register ([7f427d6](https://github.com/GabrielCpp/stablemate/commit/7f427d610abbbeb4f962af818ee485fe15e01ce2))
* **ostler:** derive candidate links instead of echoing them in verdicts ([188c7cd](https://github.com/GabrielCpp/stablemate/commit/188c7cdd1c6adae8766927dc9024e7960a943316))
* **ostler:** derive owning keys from the registry ([1f402e1](https://github.com/GabrielCpp/stablemate/commit/1f402e14dda921df072974ddaa154416f2bd84ef))
* **ostler:** doctor checks for the judgment gap ([b965a1b](https://github.com/GabrielCpp/stablemate/commit/b965a1b30e017b88efb862b99d138fceb7185685))
* **ostler:** exempt field nodes from undeclared-obligation ([df451fc](https://github.com/GabrielCpp/stablemate/commit/df451fc4779f00405d197102df30d01b40807fa5))
* **ostler:** extract PHP behavior candidates ([1174c85](https://github.com/GabrielCpp/stablemate/commit/1174c8549682d76fb46d08c79ef3aa7348f2e686))
* **ostler:** extract TypeScript and TSX behavior candidates ([fb73043](https://github.com/GabrielCpp/stablemate/commit/fb730436b79798060c2f1d7764207668d8a5196a))
* **ostler:** give every declaration a content watermark ([9368d3c](https://github.com/GabrielCpp/stablemate/commit/9368d3c0772a3c6bdb29f14984292a96b6649956))
* **ostler:** identify stories in QA context packets ([ec654da](https://github.com/GabrielCpp/stablemate/commit/ec654da56f5b8df20d8092572081f12c68fd3bab))
* **ostler:** judgment and unspecified reach the qa context packet ([ed75eee](https://github.com/GabrielCpp/stablemate/commit/ed75eee9d5768d9ff5fab0701c4ca024b99f5f84))
* **ostler:** key spec dirs and story identity by the minted id ([14664ea](https://github.com/GabrielCpp/stablemate/commit/14664ea57359340a25d0173ffe52ac0356db52de))
* **ostler:** let a config: bullet own a declared configuration file ([d87ad6f](https://github.com/GabrielCpp/stablemate/commit/d87ad6f45e1b12012c9b15848ca48af53f67178e))
* **ostler:** let a surface declare itself not exercised ([a7af68a](https://github.com/GabrielCpp/stablemate/commit/a7af68a2f18eef05669c99fb72c80bc768b44d92))
* **ostler:** map diffs across source repositories ([dea798f](https://github.com/GabrielCpp/stablemate/commit/dea798f02fdbf5a397c93ef4869f8e06329f35a6))
* **ostler:** memoize behavior verdicts in the index ([d762fb3](https://github.com/GabrielCpp/stablemate/commit/d762fb320dcacd4b20d0a96d2c6066ebe87d9a6f))
* **ostler:** migrate legacy stories on demand ([c46c914](https://github.com/GabrielCpp/stablemate/commit/c46c914cefef20fa0f3a1f631beb198cee684075))
* **ostler:** name the port holder when a stack bring-up fails ([cd0b008](https://github.com/GabrielCpp/stablemate/commit/cd0b00895f7e0bd046a4e4b2d37a711042f73ecf))
* **ostler:** parse the one-per repeat grammar for generated elements ([3a08fbb](https://github.com/GabrielCpp/stablemate/commit/3a08fbb3cff0c372498ccf42b41547ef1ba2d40f))
* **ostler:** place each step in the recording and pull its frames ([2742846](https://github.com/GabrielCpp/stablemate/commit/274284685786476532f80676d228e0225b8f0955))
* **ostler:** prepare two-way behavior audit packets ([efcdcbe](https://github.com/GabrielCpp/stablemate/commit/efcdcbe8d7fef6393fef5013c8f78b9973a4da34))
* **ostler:** query story and OKF provenance ([43e3d6e](https://github.com/GabrielCpp/stablemate/commit/43e3d6e9d3b1209daa8ef2e21e7c765e2e6291a0))
* **ostler:** read the qa stack from the book's ops nodes ([ff0a324](https://github.com/GabrielCpp/stablemate/commit/ff0a3243c2d1ada1bb3540d795c759a54b9db8c5))
* **ostler:** record owned stack processes and reap them across runs ([c9da94d](https://github.com/GabrielCpp/stablemate/commit/c9da94d886acd09ac6c2a4ac5026628515c7f32c))
* **ostler:** report duplicate-bullet instead of a locator collision ([6dd7acc](https://github.com/GabrielCpp/stablemate/commit/6dd7acc06e8efe961de0a1b85045ef4192462eac))
* **ostler:** report uncited exported files without building a packet ([ed273e0](https://github.com/GabrielCpp/stablemate/commit/ed273e07add93126ed8f43fe7d825f6e20eb7cba))
* **ostler:** resolve stories by external key ([51da445](https://github.com/GabrielCpp/stablemate/commit/51da445af0c58e99afcc4e9eaf9f101b4b416fcd))
* **ostler:** salvage the verdicts a short reply did answer ([ed807b1](https://github.com/GabrielCpp/stablemate/commit/ed807b1e227378c47b553a15b115b7652334e33c))
* **ostler:** seed reachability from the surface's root screen ([4cdcb34](https://github.com/GabrielCpp/stablemate/commit/4cdcb34cea097b68412315df42cfd9b79d07d16f))
* **ostler:** template-outside-repeat doctor check ([f6bff33](https://github.com/GabrielCpp/stablemate/commit/f6bff3342d61c7151d20b8169736ac0907270cac))
* **ostler:** trim audit packets to their scope and claim window ([4a2abd3](https://github.com/GabrielCpp/stablemate/commit/4a2abd3b7da905f30071f754ea71767fcd295e81))
* **ostler:** trim rows, import-graph walk, repo declaration ([7a99e80](https://github.com/GabrielCpp/stablemate/commit/7a99e808191877ccf9b450331a1ae6cb333a17a8))
* **ostler:** unspecified bullet class with grounded citation ([7b1a64f](https://github.com/GabrielCpp/stablemate/commit/7b1a64f7998d029207e46fe53cf493edcc0cb40b))
* **ostler:** verify source context freshness ([e6cf1d8](https://github.com/GabrielCpp/stablemate/commit/e6cf1d86b7622152434ac68632348459c41960ab))
* **ostler:** warn unminted-claim on a claim no obligation carries ([ce6bc00](https://github.com/GabrielCpp/stablemate/commit/ce6bc001c8f572d9d77d1506ee62a7ce2ffc94de))
* **ostler:** watermark the whole book, not only its cross-repo refs ([77b8049](https://github.com/GabrielCpp/stablemate/commit/77b80497ae3abb2a3df37767fd65dfbd3b8b71fa))


### Bug Fixes

* **ostler:** adopted stacks must still pass seed and health gates ([1f444c7](https://github.com/GabrielCpp/stablemate/commit/1f444c74e892a053a6e2d29cd492b0dd4dc2a53b))
* **ostler:** bound extract recursion and read text off the source ([190495e](https://github.com/GabrielCpp/stablemate/commit/190495e7e9968cf3dc56cb8cf5fab2a1e1c8ac08))
* **ostler:** brief step failures with the exit code and stdout tail ([fb58684](https://github.com/GabrielCpp/stablemate/commit/fb5868471acad0a2b0008138fa742cd5a2ef734b))
* **ostler:** competing-implementations needs a shared symbol ([592b33b](https://github.com/GabrielCpp/stablemate/commit/592b33b46a12086fb09759071940aefd65bdb01f))
* **ostler:** competing-implementations skips parts of one declared whole ([dafc9e5](https://github.com/GabrielCpp/stablemate/commit/dafc9e54e5e01ae2b349ce080e02a57bd65fdcc1))
* **ostler:** exempt a verb alternation from unstated-precondition ([a42ea79](https://github.com/GabrielCpp/stablemate/commit/a42ea7941aa45e0d1d8f6a618e39a1b176f3ce86))
* **ostler:** film a viewport recording at the viewport ([0a70a5c](https://github.com/GabrielCpp/stablemate/commit/0a70a5c2c662ed26ec796a68dc25399e4e4fc996))
* **ostler:** film the app under test, not the operator's desktop ([77852d1](https://github.com/GabrielCpp/stablemate/commit/77852d14171a25240896f2b4f590ebb743e10d4d))
* **ostler:** give every finding a ref that names one thing ([35fd203](https://github.com/GabrielCpp/stablemate/commit/35fd203892a6d0fb2e24c87a8c168e4c6379ce7b))
* **ostler:** ground Go struct fields and interface methods ([2f65f25](https://github.com/GabrielCpp/stablemate/commit/2f65f25bf08614ecd15d4bb071119b4d1a17d46d))
* **ostler:** guard the member-name walk against an empty field path ([3b313b3](https://github.com/GabrielCpp/stablemate/commit/3b313b31ffb4c4475dc4c54b5a7cff94b7caef2b))
* **ostler:** hold only stack runbooks to the stack shape ([5e75d5d](https://github.com/GabrielCpp/stablemate/commit/5e75d5d7dfeb861fcdc0bdc63185ec15d925c5d5))
* **ostler:** ignore state-dependent lifecycle alternatives ([d53cef7](https://github.com/GabrielCpp/stablemate/commit/d53cef7cbc200afd0083225599a113267ff59d12))
* **ostler:** judge a story by its sections, not by a shape stamp ([17619ea](https://github.com/GabrielCpp/stablemate/commit/17619ea104ec18ef53ad329dd53529cad682b085))
* **ostler:** keep audit packets under budget for long go functions ([1bea8d9](https://github.com/GabrielCpp/stablemate/commit/1bea8d970cb0635775851bc3a86e256ce715d8a4))
* **ostler:** let a whole and its own parts cite one symbol ([cc6ef89](https://github.com/GabrielCpp/stablemate/commit/cc6ef89b8bf5971508d1cc5bee771fb079275dfb))
* **ostler:** make the backlog and roadmaps configured doc roots ([21a4d10](https://github.com/GabrielCpp/stablemate/commit/21a4d10afa4a8c3e3aebfbaeea0b686c00d7be94))
* **ostler:** mint a node id from the anchor GitHub renders ([8e49593](https://github.com/GabrielCpp/stablemate/commit/8e49593d34628096faa36f0bb124391ff4d04908))
* **ostler:** name the claim in an unstated-precondition finding ([3f6d141](https://github.com/GabrielCpp/stablemate/commit/3f6d14119fb45030dea75d12f1c289f2d67b37f9))
* **ostler:** pin tree-sitter below 0.26 to stop the audit segfault ([bd8d0fd](https://github.com/GabrielCpp/stablemate/commit/bd8d0fd1b1dcbf54eda88343d268b180f7918d4e))
* **ostler:** read failure names out of code spans, not raw prose ([021d119](https://github.com/GabrielCpp/stablemate/commit/021d1198ec2c5cabc126cc4a1b1bc713b7a2740c))
* **ostler:** read the semicolon signal off prose, not code spans ([973c696](https://github.com/GabrielCpp/stablemate/commit/973c6965aaa53faa8be4b13d43180a7e200ed0ab))
* **ostler:** read the semicolon signal outside parentheticals ([949669b](https://github.com/GabrielCpp/stablemate/commit/949669bf35b1ab23d7c68d49bb18fa03db5e7141))
* **ostler:** refuse a named-key subscript anywhere in a QA plan ([b7298cf](https://github.com/GabrielCpp/stablemate/commit/b7298cf49499bf2248916e18e7262d91af7d8d1a))
* **ostler:** reject an excerpt whose bounds overrun its own text ([29804f2](https://github.com/GabrielCpp/stablemate/commit/29804f2fbbbc02557452f34783bb7120ccab24aa))
* **ostler:** report the missing Xvfb once, not twice ([6e9f994](https://github.com/GabrielCpp/stablemate/commit/6e9f994247a09e11ace4506ece726a6c93f4d5f2))
* **ostler:** retire pre-fix symbol tables from the index ([0e8321e](https://github.com/GabrielCpp/stablemate/commit/0e8321e351d8b0b903f9581fc23b5cd6cd00b958))
* **ostler:** scope extract_book's read, not just its result ([8bac76d](https://github.com/GabrielCpp/stablemate/commit/8bac76dd9efca41c5934ba20efe5cb1adddf4e7f))
* **ostler:** skip claims under duplicate node ids in the audit ([eb569d1](https://github.com/GabrielCpp/stablemate/commit/eb569d1cc100ba3dd592e1fde4df7c5bace4e496))
* **ostler:** stop probing "/" when a runbook declares no entry url ([86b1eda](https://github.com/GabrielCpp/stablemate/commit/86b1edafa6e88c2ad96a33c10aa17d1e2a590cec))
* **ostler:** stop scoring an aborted scenario as a caught defect ([7058cc0](https://github.com/GabrielCpp/stablemate/commit/7058cc036958ef3c5677486158e5af245ba4c5ae))
* **ostler:** stop the last section advertising a line it does not carry ([f7c6d1e](https://github.com/GabrielCpp/stablemate/commit/f7c6d1eced4774c56d84f1b70955b47f66e51072))
* **ostler:** stop two detectors reporting findings no edit can clear ([d3f8505](https://github.com/GabrielCpp/stablemate/commit/d3f85056a3e85da0793e38c4dd6fa5f567f27753))
* **ostler:** stop unstated-precondition firing where no edit clears it ([2aafe95](https://github.com/GabrielCpp/stablemate/commit/2aafe9533fe35690432182a6289824d813b4a12d))
* **ostler:** teach the relation-subject slug shape at every surface ([a2d3511](https://github.com/GabrielCpp/stablemate/commit/a2d35112c4ee17dd1b4935190795483598aee772))
* **ostler:** warn about a missing stack only where something is served ([5ccdb75](https://github.com/GabrielCpp/stablemate/commit/5ccdb75e8e6f43d38dc49f87954bd9dedf4b4452))
* **paddock:** skip .git when copying test fixtures ([379271f](https://github.com/GabrielCpp/stablemate/commit/379271f9b98095bf7b63eb654f9c152adcf85d5e))
* repoint the guards and this repo's install at the regrouped library ([4fc4e9e](https://github.com/GabrielCpp/stablemate/commit/4fc4e9e88d467ef847ad4e9b20859aed22954f34))
* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))


### Performance Improvements

* parallelize Python test suites ([ee2f9f2](https://github.com/GabrielCpp/stablemate/commit/ee2f9f27152cbdfca029b661cf761e95a3fd2121))


### Code Refactoring

* **base-library:** drop the group stutter from skill sources ([4681c89](https://github.com/GabrielCpp/stablemate/commit/4681c89b9988c10588bcdedeab41466aec200b95))
* **core:** bump stablemate config schema to v2 ([586d593](https://github.com/GabrielCpp/stablemate/commit/586d593134aad89d14d4f21f748a8c83ae6b4ad8))
* **core:** move the clock port into shared plumbing ([fa5a4f5](https://github.com/GabrielCpp/stablemate/commit/fa5a4f5a7323f0740ee775c6b6f40c8da8f6e64a))
* **ostler:** answer the findings basedpyright reports ([923de54](https://github.com/GabrielCpp/stablemate/commit/923de5494be0cdda19fa5f63fcdaf6b4ad6782a6))
* **ostler:** expose the served-surface predicate ([4820be9](https://github.com/GabrielCpp/stablemate/commit/4820be9d169ba5f1508cb4bbe4db0795a55888e8))
* **ostler:** inject daemon lifecycle timing ([e98cd61](https://github.com/GabrielCpp/stablemate/commit/e98cd61cdd5b374c13fc9735fc6e87cad253fb9e))
* **ostler:** move "what changed since" next to the catalog ([0defc23](https://github.com/GabrielCpp/stablemate/commit/0defc237dd202f0004f66ef15a17ec75f84c1520))
* **ostler:** own the durable QA stack, hard-cut workhorse.stack ([6191e5d](https://github.com/GabrielCpp/stablemate/commit/6191e5d5359c1675fd72fda7cf04e51a6e4a5486))
* **workflows:** give each okf_builder flow its own prompts ([232d552](https://github.com/GabrielCpp/stablemate/commit/232d552220c75c5084056353c1979d02e21585c5))

## [1.1.0](https://github.com/GabrielCpp/stablemate/compare/ostler-v1.0.1...ostler-v1.1.0) (2026-08-14)


### Features

* **ostler:** add created/removed paired lifecycle checks ([6eaf82a](https://github.com/GabrielCpp/stablemate/commit/6eaf82aafba0e362d367265b825901202cd933d1))
* **ostler:** check a rendered region against its documented placement ([c20e489](https://github.com/GabrielCpp/stablemate/commit/c20e489110c0fc2e588ec6151c84555c3c1cb8f0))
* **ostler:** declare where a component sits on the screen ([cba4cfd](https://github.com/GabrielCpp/stablemate/commit/cba4cfd9a5a5d0139078bcd553b3b88b95ec478f))
* **ostler:** drive the browser from inside the scenario process ([765cd59](https://github.com/GabrielCpp/stablemate/commit/765cd595d12568b5e413501390665279d5051dab))
* **ostler:** expose fmt on the Ostler api ([e3b9646](https://github.com/GabrielCpp/stablemate/commit/e3b96466f00e7411a8fb736460d292c35b20adce))
* **ostler:** expose the QA sandbox on the Python API ([8aad923](https://github.com/GabrielCpp/stablemate/commit/8aad923cb78f838c44e11cda269cbd0f3f2d775f))
* **ostler:** flag a normative bullet too long to prove ([595ea9b](https://github.com/GabrielCpp/stablemate/commit/595ea9b81b7faf31833f92077077f3b7c9d0fe20))
* **ostler:** let a mid-journey photograph vet part of a screen ([fab484f](https://github.com/GabrielCpp/stablemate/commit/fab484f24e3792965993a7b1d4ebd8a72c164af7))
* **ostler:** let a scenario assert on the live browser diagnostics ([5d8c150](https://github.com/GabrielCpp/stablemate/commit/5d8c150bd91b26873da6ff13b61a0b4b49a91069))
* **ostler:** load a python QA plan through a describe pass ([37fa53f](https://github.com/GabrielCpp/stablemate/commit/37fa53fcc0e81af30801219523d52f97cb9003a0))
* **ostler:** make a UI scenario vet the screen it photographed ([a4c0d80](https://github.com/GabrielCpp/stablemate/commit/a4c0d80a4a676f2e3ad8447a1dfb0fc01e722597))
* **ostler:** make QA evidence declared, live and computable ([223a01e](https://github.com/GabrielCpp/stablemate/commit/223a01edaf75d1ff5acce1854712d29b872f587b))
* **ostler:** measure the layout beside every QA screenshot ([ea4de08](https://github.com/GabrielCpp/stablemate/commit/ea4de08a65373642fb6c9c72f01051d2cfcf1bfe))
* **ostler:** read the qa context packet in filtered, paged slices ([7cb3ed4](https://github.com/GabrielCpp/stablemate/commit/7cb3ed45d0ae85203c8a4b88c97f98ad53940c36))
* **ostler:** record every screenshot's regions in vet's own format ([fa2d893](https://github.com/GabrielCpp/stablemate/commit/fa2d893f73b57eed9fbcdbc049a96e5d443a96b3))
* **ostler:** record response status in the browser diagnostics ([a88591b](https://github.com/GabrielCpp/stablemate/commit/a88591b103c868b7f10fca9de904a4f462cda79c))
* **ostler:** record the whole console and network in the diagnostics ([79e7f91](https://github.com/GabrielCpp/stablemate/commit/79e7f917c46b747474dc5ddac346a4c47700f28c))
* **ostler:** record why a failed request failed, not just its url ([c7c0ddc](https://github.com/GabrielCpp/stablemate/commit/c7c0ddc921278710209ddc54d2e9fa963d9c92f9))
* **ostler:** refuse a UI scenario that vets nothing ([441451a](https://github.com/GabrielCpp/stablemate/commit/441451aab013633970f9158d7ae79dd79b4d3265))
* **ostler:** report checks that cannot go red ([e5cfe9c](https://github.com/GabrielCpp/stablemate/commit/e5cfe9c0f790d66f83b7493bf6fd0e32b15930a4))
* **ostler:** run a QA scenario as a python function ([ba333d7](https://github.com/GabrielCpp/stablemate/commit/ba333d76eec0017594e676b80c34f3abe77ca28f))
* **ostler:** run a QA scenario as a python function ([8f4797d](https://github.com/GabrielCpp/stablemate/commit/8f4797d2a46d7bd50f287ca3f2132dc1e68de905))
* **ostler:** run a single qa scenario into a scratch directory ([16f1acb](https://github.com/GabrielCpp/stablemate/commit/16f1acbd498331b8bb72d8f20fee3646ce4cb9e9))
* **ostler:** scan a mobile screen's regions from its view hierarchy ([bfe9563](https://github.com/GabrielCpp/stablemate/commit/bfe9563ac3f2e55f663eac8af60e9552d6e934ae))
* **ostler:** stamp a schema key on the browser diagnostics ([105cb82](https://github.com/GabrielCpp/stablemate/commit/105cb822c15f6c73c38bb86c5e72b4be1ee6e2b5))


### Bug Fixes

* **ostler:** bind each QA obligation to the assertion that proves it ([08580cb](https://github.com/GabrielCpp/stablemate/commit/08580cb944d29490004480565f14bdd309198d2b))
* **ostler:** catch a heading that re-parents its neighbour's fields ([a66d92d](https://github.com/GabrielCpp/stablemate/commit/a66d92dae5c91f6a898ac7e74e2630bf285b3ad6))
* **ostler:** fail a qa step when an upstream pipeline stage fails ([b02467c](https://github.com/GabrielCpp/stablemate/commit/b02467c28a348f1b86c79d0c4668a46f55e97a04))
* **ostler:** follow module helpers and constants when reading a plan ([70a70df](https://github.com/GabrielCpp/stablemate/commit/70a70dfcec1152375fa7aafe44c030c62636054a))
* **ostler:** ignore doctor waiver ledger in qa context ([77612cd](https://github.com/GabrielCpp/stablemate/commit/77612cdac17a61a384c1d0851e89014fb2d4822f))
* **ostler:** ignore opencode session artifacts in qa context ([4bba7c0](https://github.com/GabrielCpp/stablemate/commit/4bba7c0b2b6dbdd0cf82efe8e4ce039f7b03799a))
* **ostler:** keep a dry run out of the scored qa ledger ([f2e8040](https://github.com/GabrielCpp/stablemate/commit/f2e80400ec9eba22a849c0a5c9886c02fff969b4))
* **ostler:** keep the check a scenario verified on its ledger record ([1aa9d5c](https://github.com/GabrielCpp/stablemate/commit/1aa9d5c5c8d9d8af86b202f242ad3d050d24f33c))
* **ostler:** let a waiver reach a warn-level finding ([23ac850](https://github.com/GabrielCpp/stablemate/commit/23ac85066a0e7bb30139dc7abea972e73cd83e24))
* **ostler:** make a passing ready_check survive the daemon it describes ([f613b98](https://github.com/GabrielCpp/stablemate/commit/f613b980583f0d3d5ba0d2d1078051782a33f34b))
* **ostler:** make the recorded QA video playable ([41cfbeb](https://github.com/GabrielCpp/stablemate/commit/41cfbeba99c9533190008eba4b993801ed890b0d))
* **ostler:** name the near-miss call a declared check refusal is about ([df8fd5f](https://github.com/GabrielCpp/stablemate/commit/df8fd5feb5c0a00ef1b4f06b05fbd6e74fca7249))
* **ostler:** name the node behind a value-level covers id ([8f40092](https://github.com/GabrielCpp/stablemate/commit/8f40092c848613c25f23741210f1d712bfc3cefc))
* **ostler:** reach the QA harness by a path the platform spells ([a076fea](https://github.com/GabrielCpp/stablemate/commit/a076fea9fa4d1e569979556cfe5da02b502969bd))
* **ostler:** read a $-rooted json_path as the field it names ([f20cccd](https://github.com/GabrielCpp/stablemate/commit/f20cccd34ec031e1cd433e70257ec5c4b80c3d92))
* **ostler:** record an unmet expect_status as a failed assertion ([8541739](https://github.com/GabrielCpp/stablemate/commit/85417392510b87435582703ad91fdc75a7af1f17))
* **ostler:** register a loaded harness module under its own name ([980f72b](https://github.com/GabrielCpp/stablemate/commit/980f72b84fa932cbedc38a58df691161f538730b))
* **ostler:** reject a qa-evidence left over from an earlier run ([dcb4785](https://github.com/GabrielCpp/stablemate/commit/dcb4785216951b3ce6fb27bf38d5369a1efb7c4c))
* **ostler:** report a missing declared check once, not per obligation ([9f15b15](https://github.com/GabrielCpp/stablemate/commit/9f15b15640600574c23f9c29370ec37525aa2559))
* **ostler:** say a required section is missing, not empty ([809b18c](https://github.com/GabrielCpp/stablemate/commit/809b18cd56e44f3314b8d54cebbc46c9822ac06c))
* **ostler:** say why a device screen cannot be vetted yet ([ab8b593](https://github.com/GabrielCpp/stablemate/commit/ab8b5939d5b71fd5e7ba46f455259b37425964bc))
* **ostler:** say why a helper's checks read as no checks at all ([20f9c99](https://github.com/GabrielCpp/stablemate/commit/20f9c995eeef9b1677555b839aad30778f096e7b))
* **ostler:** sink a qa criterion its own run log disproves ([ecb7a5b](https://github.com/GabrielCpp/stablemate/commit/ecb7a5bf54e11950ad147b837423abcee7550bd8))
* **ostler:** sort obligations by natural index ([f6f2104](https://github.com/GabrielCpp/stablemate/commit/f6f2104704781393af19d20664555b2cefb377fb))
* **ostler:** stop a process-exit assertion from satisfying coverage ([d7577aa](https://github.com/GabrielCpp/stablemate/commit/d7577aa403c4daecb5ae9764f47375ef5b3cb136))
* **ostler:** stop a QA plan writing bytecode into the docs tree ([c77af2b](https://github.com/GabrielCpp/stablemate/commit/c77af2ba46c12a330dccc86df09dce84542e99e9))
* **ostler:** stop qa.by_text pinning an exact match nothing renders ([9f29f81](https://github.com/GabrielCpp/stablemate/commit/9f29f8176e79818254fe2cdc2aa4e5dd7a5ffda1))
* **ostler:** stop the grounding gate calling every binary file missing ([84faf4a](https://github.com/GabrielCpp/stablemate/commit/84faf4a1d6155f9183d095504316c9356678ef21))
* **ostler:** stop unstated-precondition inflecting an inflected verb ([79a998c](https://github.com/GabrielCpp/stablemate/commit/79a998c73a22ca05b344135e2115de8edb9ade70))
* **ostler:** stop vet demanding every state in one photograph ([afe0b82](https://github.com/GabrielCpp/stablemate/commit/afe0b824b2d21cd3c1e23dce9a39af32537ebc0c))
* **ostler:** tell an author the check they got wrong, not a canned one ([b3db085](https://github.com/GabrielCpp/stablemate/commit/b3db085cf91eea1e11ffcc35ac1966b7831c874b))


### Code Refactoring

* **ostler:** delete the shell-action vocabulary ([e88ffe4](https://github.com/GabrielCpp/stablemate/commit/e88ffe46227c57a2328a2f00069d989a2ba2318b))
* **ostler:** keep the scanned-element model beside the merge ([ea0295a](https://github.com/GabrielCpp/stablemate/commit/ea0295aa4e1f1a41ceb88d855e7d2c368fe68330))
* **ostler:** measure a bullet's prose with the markdown parser ([83346f6](https://github.com/GabrielCpp/stablemate/commit/83346f6ff0fb38f0607534c167761cc7d2ae7a03))
* **ostler:** point the leftover prose at the Dependencies section ([5ba0973](https://github.com/GabrielCpp/stablemate/commit/5ba097312350af09e4aaa82bddedbf5e7f911027))
* **ostler:** read a story's blockers from the story itself ([82e52ac](https://github.com/GabrielCpp/stablemate/commit/82e52ace4c9acd2e766b8694491a098ec24fcaa2))


### Reverts

* "docs(base-library): say one qa.verify can cover siblings" ([6fba5a6](https://github.com/GabrielCpp/stablemate/commit/6fba5a632b6ef2c76c437465f0d8bd472b5f28b1))

## [1.0.1](https://github.com/GabrielCpp/stablemate/compare/ostler-v1.0.0...ostler-v1.0.1) (2026-08-11)


### Bug Fixes

* **ostler:** capture an aria snapshot with an API playwright still has ([6836da6](https://github.com/GabrielCpp/stablemate/commit/6836da6a0da035670a3912bef358a11372558e36))
* **ostler:** state the role-name rule even when the element is gone ([d3dedbd](https://github.com/GabrielCpp/stablemate/commit/d3dedbdb07609a8769d88ea9dc6b55b891682d7c))

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/ostler-v0.2.0...ostler-v1.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **ostler:** adopt every backlog bullet
* remove legacy gap and knowledge doc types
* installed skill names change for every repo that selects the `stablemate` pack — `<repo>-stablemate-ostler` becomes `<repo>-ostler`. An agents.yml selecting `stablemate/stablemate-ostler` by hand, a `localInstructions` entry, or a prompt naming an old skill has to be updated; farrier reports the miss with a suggestion rather than installing nothing. In the stablemate repo most installed names are unchanged, because the derived prefix restores them: `ostler` installs as `stablemate-ostler` exactly as before. The two that do move here are `stablemate-coder-workflow` -> `stablemate-workhorse-coder-workflow` and `stablemate-documentation` -> `stablemate-ostler-documentation`.

### Features

* **base-library:** state which platforms each tier of this repo runs on ([43a25eb](https://github.com/GabrielCpp/stablemate/commit/43a25ebd0dd8d9cecc5d8486c19686d5bbf91df6))
* **ostler:** add unblock to clear give-up stamps off stories ([9494861](https://github.com/GabrielCpp/stablemate/commit/9494861382a76520f8defd66512cd97e1ee2bb20))
* **ostler:** adopt every backlog bullet ([804a93c](https://github.com/GabrielCpp/stablemate/commit/804a93cf0462b6e28434ba44d0a9615991382546))
* **ostler:** classify seeds by layer and service ([60f6566](https://github.com/GabrielCpp/stablemate/commit/60f65666b924014290b48039f852651eca530585))
* **ostler:** support contains: for expect: url QA assertions ([6c169c1](https://github.com/GabrielCpp/stablemate/commit/6c169c11e3fd10732c91c64bc1b46dee5b062b24))
* **ostler:** support graph-safe epic reconciliation ([cbbefee](https://github.com/GabrielCpp/stablemate/commit/cbbefee94855ffb24416dfa20923ec86eefe766c))


### Bug Fixes

* **ostler:** accept counter-free id registries ([64e58cd](https://github.com/GabrielCpp/stablemate/commit/64e58cdd546c2edb6bea857f2eeb1b2e1badfe2f))
* **ostler:** drop the ~ deletion marker; deletions need no grounding ([8ca94b0](https://github.com/GabrielCpp/stablemate/commit/8ca94b0ce80d39d318e3fb190e4ab0b80dd2e7ec))
* **ostler:** grant the clipboard to a playwright scenario context ([23bae27](https://github.com/GabrielCpp/stablemate/commit/23bae275d3dc541272a29f5ff93c8f37df29255b))
* **ostler:** ground code bullets naming module-level bindings ([7492401](https://github.com/GabrielCpp/stablemate/commit/749240156757512a22c1c5c12a2044052779c049))
* **ostler:** honour the skip set when selecting the next story to author ([8a3f906](https://github.com/GabrielCpp/stablemate/commit/8a3f9062a1326b940c477ade2e704bbc1dbe212b))
* **ostler:** let a code: bullet ground a deleted symbol with a ~ mark ([23ebff9](https://github.com/GabrielCpp/stablemate/commit/23ebff9955bc12fb1aa9504b6dbe35de3140590a))
* **ostler:** name a typescript local for the declaration enclosing it ([c13c80d](https://github.com/GabrielCpp/stablemate/commit/c13c80d9428b5af2b943811aa06c102d1193520f))
* **ostler:** reject non-object assertion entries instead of crashing ([8c3e9e0](https://github.com/GabrielCpp/stablemate/commit/8c3e9e0d6b0aa2ea17d059e1604d77b456f9c2df))
* **ostler:** stop a shared container symbol obligating every control ([f70ac21](https://github.com/GabrielCpp/stablemate/commit/f70ac210559ba085b423ab00dffeac0c8829c4f1))
* **ostler:** stop a shared file citation from owing live QA evidence ([59b95f3](https://github.com/GabrielCpp/stablemate/commit/59b95f3fde6ed5165c8b624a36f8663e150fd8be))
* **ostler:** stop demanding live QA evidence for pure graph closure ([1e4cc61](https://github.com/GabrielCpp/stablemate/commit/1e4cc6157c0de3219d8482ed127727cec04658e0))
* **ostler:** stop reading EPERM from killpg as a fatal error ([a78dc84](https://github.com/GabrielCpp/stablemate/commit/a78dc842e2e975c72c3471a8af84b09e936d45ab))
* **ostler:** stop truncating a verify ref at a comma in its test name ([56e67c7](https://github.com/GabrielCpp/stablemate/commit/56e67c7306cf53ced70adc11a2693c9fd6a8cc3e))
* verify sibling packages before release ([a70c99a](https://github.com/GabrielCpp/stablemate/commit/a70c99abaddd9c195932a9da506519f473c42833))
* **workflows:** bound the doc and qa-plan reviewers to the story delta ([edb46f5](https://github.com/GabrielCpp/stablemate/commit/edb46f5d82310b7f06481c3987bac2fd47cddc11))


### Performance Improvements

* **ostler:** stop create_spec loading the graph for one directory ([8efe80a](https://github.com/GabrielCpp/stablemate/commit/8efe80a4898713e721253558a597e78955336660))


### Code Refactoring

* name base-library skills after their tool, not after stablemate ([2244a42](https://github.com/GabrielCpp/stablemate/commit/2244a420cfc0c837331f5e4b798dd784093d52c7))
* **ostler:** import the qa package at module scope ([208ca3a](https://github.com/GabrielCpp/stablemate/commit/208ca3a6b5e3a4d804db38a47b1dbcf8d29bc0e9))
* **ostler:** parse Go/TS/PHP/Twig instead of matching them ([1000937](https://github.com/GabrielCpp/stablemate/commit/1000937b07aeaeb08989167ec6292e4429536af3))
* **ostler:** read verify refs by splitting, not by pattern-matching ([22ed640](https://github.com/GabrielCpp/stablemate/commit/22ed640d7e0c0be445773dd6f673ae68957e31f1))
* remove legacy gap and knowledge doc types ([0dfb566](https://github.com/GabrielCpp/stablemate/commit/0dfb566862e77dfbf05f812c6cfbb82e02692021))

## [0.2.0](https://github.com/GabrielCpp/stablemate/compare/ostler-v0.1.0...ostler-v0.2.0) (2026-08-02)


### Features

* **ostler:** inventory package-level go values and named type aliases ([e1345b1](https://github.com/GabrielCpp/stablemate/commit/e1345b1eaae60155c11851b13942728659aa3b0f))
* **ostler:** mark untouched qa obligations as context-only ([7eaf351](https://github.com/GabrielCpp/stablemate/commit/7eaf3510d612c6e0bd03b05b0ccb482fcf15c3d7))


### Bug Fixes

* **ostler:** report a mapping operation instead of crashing on it ([98a806f](https://github.com/GabrielCpp/stablemate/commit/98a806f91b4284273c7e9e2b6efd66ce6698ed12))
* **ostler:** stop a flow reached from a flow becoming a contract ([ad64fd6](https://github.com/GabrielCpp/stablemate/commit/ad64fd6b3db0a39fb97f402c547337c37e6120a7))
* **ostler:** stop fmt duplicating soft-wrapped bullet lines ([729a205](https://github.com/GabrielCpp/stablemate/commit/729a2058f4908f47fcf1a2e17a5bd30248fc0538))
