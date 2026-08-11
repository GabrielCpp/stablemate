# Changelog

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
