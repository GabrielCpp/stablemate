# Changelog

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
