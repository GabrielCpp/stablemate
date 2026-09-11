# Changelog

## [3.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-agent-v2.1.0...workhorse-agent-v3.0.0) (2026-09-11)


### ⚠ BREAKING CHANGES

* **core:** bump stablemate config schema to v2

### Features

* capture full opencode session transcripts ([e03d1bd](https://github.com/GabrielCpp/stablemate/commit/e03d1bdb502473dff76578345168a8ed002432a9))
* **core:** let a power tier scale every wall-clock budget ([50b5081](https://github.com/GabrielCpp/stablemate/commit/50b5081d3930a22e0cae23ed2c989eb56af71d3c))
* **core:** persist a nested config table, and groom's attend settings ([3c51cca](https://github.com/GabrielCpp/stablemate/commit/3c51cca625bf29d50092cbb1cbd2a7399bec8cb3))
* **workhorse:** arm the wake file before a watcher parks on it ([ae808c2](https://github.com/GabrielCpp/stablemate/commit/ae808c273eeb0275be51e57cb8551196f5b7e15f))
* **workhorse:** bound transient provider retries per agent node ([22a0330](https://github.com/GabrielCpp/stablemate/commit/22a0330582845014a0a867e39ab29cd9508f5830))
* **workhorse:** control answer and questions subcommands ([089772b](https://github.com/GabrielCpp/stablemate/commit/089772b221596e082944fc08420db8c519939a4a))
* **workhorse:** draw a Done as an edge to END, never as a green state ([d18d588](https://github.com/GabrielCpp/stablemate/commit/d18d588f8bf880334a393cdd5ab624f9536243b4))
* **workhorse:** draw a handoff as a coloured step, not a cross edge ([89aadb8](https://github.com/GabrielCpp/stablemate/commit/89aadb85ed541622e30c68782526e2837ecbd238))
* **workhorse:** draw a state as the chain of steps it runs ([44ee85f](https://github.com/GabrielCpp/stablemate/commit/44ee85fc72f39e025832dd3ee0f64bddf9f695dd))
* **workhorse:** let a registry declare its own package ([a1c17b4](https://github.com/GabrielCpp/stablemate/commit/a1c17b459ca2308cd91d53210e3a8081a4f154d5))
* **workhorse:** let a transition say why, and print it on the edge ([bed8d77](https://github.com/GabrielCpp/stablemate/commit/bed8d7787b7818f86fdab3fe276f688d60036eae))
* **workhorse:** let an Await say a machine owes it the answer ([b3e33ec](https://github.com/GabrielCpp/stablemate/commit/b3e33ec60b85a44c467cda4f97d9174eae544fff))
* **workhorse:** questions and answer verbs on the control channel ([0debb61](https://github.com/GabrielCpp/stablemate/commit/0debb61da2d9cb0276805687cd3d6c3db6207b93))
* **workhorse:** re-attempt a capped turn every probe interval ([4ac6481](https://github.com/GabrielCpp/stablemate/commit/4ac6481fe0203c3c10a15d2c6574979e95ba78a1))
* **workhorse:** refill the transition budget on forward progress ([780e06c](https://github.com/GabrielCpp/stablemate/commit/780e06c9ea19c775b1d43d86b35be6e089d318c0))
* **workhorse:** resolve control --run through groom on a local miss ([279b6a3](https://github.com/GabrielCpp/stablemate/commit/279b6a3686498ae6e6e81cfe49e14fc813667781))
* **workhorse:** resume re-arms a parked operator wait ([cbe7c58](https://github.com/GabrielCpp/stablemate/commit/cbe7c58cfba14426ccbea570abeed409eac271f0))
* **workhorse:** run a measurement detached under a bounded supervisor ([3c0cb8c](https://github.com/GabrielCpp/stablemate/commit/3c0cb8c64e535353a1a6dfae83b04598f2c2e2b0))
* **workhorse:** stamp repository scopes on telemetry ([0e77048](https://github.com/GabrielCpp/stablemate/commit/0e7704876a84d6c28f2ce059132f54475aeaf760))
* **workhorse:** the operator await answers over the socket ([c5eff11](https://github.com/GabrielCpp/stablemate/commit/c5eff119dc8d908e1fbb9f2efcceb996f670fdb2))


### Bug Fixes

* **workflows:** audit survives a sustained models.dev outage ([60a664e](https://github.com/GabrielCpp/stablemate/commit/60a664ec5edb0fc04b1a7ba142e4394daad747c6))
* **workhorse:** accept the type __package__ actually has ([0e5e3f1](https://github.com/GabrielCpp/stablemate/commit/0e5e3f1ac48ad2bdac832e6698633cecce5a5ac0))
* **workhorse:** add skill_path_ref so prompts cite installed skill files ([f65ff19](https://github.com/GabrielCpp/stablemate/commit/f65ff190132e99ef82b3f88d49304580455e8c64))
* **workhorse:** apply the tier's clock scale, and make the env var work ([c697fed](https://github.com/GabrielCpp/stablemate/commit/c697fedac67992a478f0b1e572bc8813598b35ca))
* **workhorse:** deliver large prompts outside argv ([2814b02](https://github.com/GabrielCpp/stablemate/commit/2814b027f9bf220cd1017a7b2e650beb74e839e1))
* **workhorse:** find the reloaded registry in its composition root ([6df4629](https://github.com/GabrielCpp/stablemate/commit/6df4629f65284c2f34e3eeb02b74c8d6c1efb995))
* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))
* **workhorse:** lift opencode's 32k output cap to the model's own limit ([ecb2545](https://github.com/GabrielCpp/stablemate/commit/ecb25454a872fbe5540de3edf131fd33982e256a))
* **workhorse:** match an opencode store lock by class, not statement ([4348c57](https://github.com/GabrielCpp/stablemate/commit/4348c57cbc4d96fadc8ca71f49d39312cf9f7c5e))
* **workhorse:** name every spent agent turn, not just the timeout ([3dae471](https://github.com/GabrielCpp/stablemate/commit/3dae471646f5a0d67fe710609269114f76fe1fe5))
* **workhorse:** pin opencode's title helper to the turn's model ([1786e93](https://github.com/GabrielCpp/stablemate/commit/1786e93efd6cfb1537e2130714693ead70cfc848))
* **workhorse:** promote settled opencode exports ([8322375](https://github.com/GabrielCpp/stablemate/commit/8322375d2b9d29a5c82a62bde6a0724a594b403f))
* **workhorse:** reassemble a control message across packets ([13c34de](https://github.com/GabrielCpp/stablemate/commit/13c34de4e74ae9782fd8c372a5f4c313d2a6c1cd))
* **workhorse:** reread partial opencode session exports ([10aef37](https://github.com/GabrielCpp/stablemate/commit/10aef37557e09cbf0b8a717945e702e45423d7e3))
* **workhorse:** retry opencode project-store contention ([4a35507](https://github.com/GabrielCpp/stablemate/commit/4a35507e7d67df7156f6d8a239eb6f7f34ee8d05))
* **workhorse:** route an exhausted output budget to compaction ([ab094a5](https://github.com/GabrielCpp/stablemate/commit/ab094a5420973cda078ea806ac2f9f1ad263a2a0))
* **workhorse:** stamp previous-process death on resume for groom ([8a87d6e](https://github.com/GabrielCpp/stablemate/commit/8a87d6eac797c94633a435cc946011ef908388cf))
* **workhorse:** stop a machine wait asking for an answer nobody owes ([2d75da8](https://github.com/GabrielCpp/stablemate/commit/2d75da8e2afefeb9a02ff01d6d46cb0239179013))
* **workhorse:** survive long agent CLI replacement gaps ([a6607f7](https://github.com/GabrielCpp/stablemate/commit/a6607f7bcf6fee8f5d1b60752d25c416994fc96d))
* **workhorse:** treat a session id as an opaque string ([7a0c66b](https://github.com/GabrielCpp/stablemate/commit/7a0c66bdf38deb61dfc386cc1a4f24ba2941a175))
* **workhorse:** treat opencode's session-store write race as transient ([133dd06](https://github.com/GabrielCpp/stablemate/commit/133dd06b08a17acd46cdb928db53c796a1699f84))


### Performance Improvements

* parallelize Python test suites ([ee2f9f2](https://github.com/GabrielCpp/stablemate/commit/ee2f9f27152cbdfca029b661cf761e95a3fd2121))
* **workhorse:** reap terminated job leaders promptly ([5ef444e](https://github.com/GabrielCpp/stablemate/commit/5ef444e1e30580b878cb452e40addc7b2e84dc3f))


### Code Refactoring

* **core:** bump stablemate config schema to v2 ([586d593](https://github.com/GabrielCpp/stablemate/commit/586d593134aad89d14d4f21f748a8c83ae6b4ad8))
* **core:** move the clock port into shared plumbing ([fa5a4f5](https://github.com/GabrielCpp/stablemate/commit/fa5a4f5a7323f0740ee775c6b6f40c8da8f6e64a))
* **ostler:** own the durable QA stack, hard-cut workhorse.stack ([6191e5d](https://github.com/GabrielCpp/stablemate/commit/6191e5d5359c1675fd72fda7cf04e51a6e4a5486))
* rename the top power tiers to max and ultra ([66a017d](https://github.com/GabrielCpp/stablemate/commit/66a017d2ae8d7ba3283cb85e676a8904fa56e831))
* **workflows:** drop the coder lanes' session_id parameter ([8db22d9](https://github.com/GabrielCpp/stablemate/commit/8db22d9c1b168bb13ef1b23dd4e9916a27f6d7c3))
* **workhorse:** answer the findings basedpyright reports ([9dba9dd](https://github.com/GabrielCpp/stablemate/commit/9dba9ddee8101d5b557f3648b4c37b3ad26d38ce))
* **workhorse:** inline one-use private helpers ([25c578c](https://github.com/GabrielCpp/stablemate/commit/25c578c1450971bfada8cc5d0a61ecdb96af64f7))
* **workhorse:** share the control and inbox run-target resolver ([f8026d7](https://github.com/GabrielCpp/stablemate/commit/f8026d754b1d6b7b03e3ba433fd7563c3fd83b35))

## [2.1.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-agent-v2.0.0...workhorse-agent-v2.1.0) (2026-08-14)


### Features

* **core:** read the fallback agent cli from the shared config ([8cc0836](https://github.com/GabrielCpp/stablemate/commit/8cc0836a7888b6c5942eaf36b5cb950a19148dff))
* **workhorse:** fall back to the configured cli, not always claude ([49f72e2](https://github.com/GabrielCpp/stablemate/commit/49f72e227fd1246388a046db39a80a30f1d57248))
* **workhorse:** keep machine scratch in the cache, not the repo ([0f9c663](https://github.com/GabrielCpp/stablemate/commit/0f9c6638767c2dc71afd8f96f0b54727e2b016d0))
* **workhorse:** let a node set its own retry budget ([c6a9c4a](https://github.com/GabrielCpp/stablemate/commit/c6a9c4a8be16902eced558323442c644b9b94ffd))
* **workhorse:** raise a catchable AgentTimeout from an overrun turn ([e7cb40c](https://github.com/GabrielCpp/stablemate/commit/e7cb40c0031d25af5c3e16b770aa42dc8798a3b7))


### Bug Fixes

* **workhorse:** stop a dead agent CLI escaping as a raw traceback ([1542242](https://github.com/GabrielCpp/stablemate/commit/15422421132744ca08bf003d9da76006caca86d8))

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-agent-v1.0.0...workhorse-agent-v2.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **groom:** groom serve binds 127.0.0.1 instead of 0.0.0.0; pass --host 0.0.0.0 to restore the old reachability for containerized runs.
* **workhorse:** AGENT_USE_DEFAULT_OUTPUTS is removed and an exhausted node raises rather than defaulting to the next node.

### Features

* **farrier:** fetch and update the base library on install ([005f6dc](https://github.com/GabrielCpp/stablemate/commit/005f6dcd7a16b6650b4be17b8993fe8fd1eccc16))
* **farrier:** launch one container per run, with its own run id ([d4a0f87](https://github.com/GabrielCpp/stablemate/commit/d4a0f879b1ae899f42c8f128acbe36e818799238))
* **groom:** bind loopback by default ([33e3f43](https://github.com/GabrielCpp/stablemate/commit/33e3f4367266ecb8934ba11e500b8b5fed90a034))
* **workflows:** give each run its own worktree of one host repo ([1e6c065](https://github.com/GabrielCpp/stablemate/commit/1e6c06541e919e03b9592dbfefecf921ad13d489))
* **workhorse:** add `control reload` for a run already in flight ([104845c](https://github.com/GabrielCpp/stablemate/commit/104845cfab227eb1d69929fce552432a753beb7a))
* **workhorse:** add a control channel port and its socket ([624cc72](https://github.com/GabrielCpp/stablemate/commit/624cc729f21952d85080e6b7f833ef4b1a55709b))
* **workhorse:** add smart and extra-smart power tiers above high ([1dba02d](https://github.com/GabrielCpp/stablemate/commit/1dba02df72ef0015b911709850133d09a8f7bf96))
* **workhorse:** add the reload request and its signal ([8f7a1e5](https://github.com/GabrielCpp/stablemate/commit/8f7a1e5dfacf0dcedc976e811137dba62142bccb))
* **workhorse:** answer control status from the live run ([087f8e3](https://github.com/GabrielCpp/stablemate/commit/087f8e3aec49f5e4d1f65c9ac643b9154399a3ae))
* **workhorse:** bound cumulative recovery waits ([df983f6](https://github.com/GabrielCpp/stablemate/commit/df983f6fbef65d23aa629079923f6e2a93e5306e))
* **workhorse:** capture each turn's transcript into the run dir ([776d3bb](https://github.com/GabrielCpp/stablemate/commit/776d3bb93ef0c5d71fd0ee6722b346f9a101e777))
* **workhorse:** carry reload requests on the control channel ([40f05a2](https://github.com/GabrielCpp/stablemate/commit/40f05a279be2d44092b8e593511a627ccc091c24))
* **workhorse:** cut a streaming turn when a reload is requested ([ffd1654](https://github.com/GabrielCpp/stablemate/commit/ffd16546481fe99bf6c215c32a2f844cca86cdb7))
* **workhorse:** find a session's store when no backend was recorded ([5c25db0](https://github.com/GabrielCpp/stablemate/commit/5c25db04f8ca83643971efc91ae6402435cdd53a))
* **workhorse:** install a bind's copy, never the bind itself ([4e177c3](https://github.com/GabrielCpp/stablemate/commit/4e177c3bbb7302a4fc0b79b0d52bdbb55d41d4ec))
* **workhorse:** keep container output host-usable, and let it log in ([b2432ea](https://github.com/GabrielCpp/stablemate/commit/b2432ea4045b6f67686452106f4c5b1a4e591296))
* **workhorse:** keep every node visit's prompt and output ([d17dc16](https://github.com/GabrielCpp/stablemate/commit/d17dc167dd94160315d2710ff6943b3a9136d1bd))
* **workhorse:** let a reload past the recovery ladder unspent ([ef47b9b](https://github.com/GabrielCpp/stablemate/commit/ef47b9ba83c6c64ac3d7c45b9ff38a75a0921dc8))
* **workhorse:** let a workflow mark its infrastructure nodes ([1f9ca28](https://github.com/GabrielCpp/stablemate/commit/1f9ca28f09cdcf4376857b3f88865a479080077e))
* **workhorse:** let labels() read the state's bound parameters ([7c53b26](https://github.com/GabrielCpp/stablemate/commit/7c53b26c7a41fa53e90dc9ce3baed8beab716752))
* **workhorse:** make the session map addressable per turn ([4dd65f0](https://github.com/GabrielCpp/stablemate/commit/4dd65f097c5c8b8a398aa4dd526c981b70a80303))
* **workhorse:** move a live run onto another agent CLI ([c60a1e8](https://github.com/GabrielCpp/stablemate/commit/c60a1e86ff40fea3a96ab0301a0bd3ab939288c8))
* **workhorse:** observe and record repo state per span and log ([f25956a](https://github.com/GabrielCpp/stablemate/commit/f25956a6e132be3bc79087df1b20d9880727d596))
* **workhorse:** re-enter a run on pushed code without restarting it ([c41e28d](https://github.com/GabrielCpp/stablemate/commit/c41e28d4c528016d5f03b0408100dd6370ce19f7))
* **workhorse:** re-exec the run to reload the engine itself ([9034628](https://github.com/GabrielCpp/stablemate/commit/9034628279d20accf8fd60d6e8266469e34ea7e7))
* **workhorse:** redact secrets and leaked-key shapes from agent output ([7dc3a55](https://github.com/GabrielCpp/stablemate/commit/7dc3a556bc22de58df4b388df601c2f45ab8cb86))
* **workhorse:** replace the aider backend with cline ([7cdf30e](https://github.com/GabrielCpp/stablemate/commit/7cdf30e44563d7af497ee0d341f77d205e989b0b))
* **workhorse:** stamp the class and recovery bucket of a failure ([d977bea](https://github.com/GabrielCpp/stablemate/commit/d977bea4d6860e14fdbf9ec4bde9804491f8575a))
* **workhorse:** tag each run start with a resume generation ([7c34d31](https://github.com/GabrielCpp/stablemate/commit/7c34d3133835d435b786682f1d71e334200d38e4))
* **workhorse:** trace state execution and workflow waits ([0b5c3ee](https://github.com/GabrielCpp/stablemate/commit/0b5c3eec358c8c060235e26bbb2730418cb83fe3))


### Bug Fixes

* **groom:** flag turns that price themselves at exactly zero ([1996ea6](https://github.com/GabrielCpp/stablemate/commit/1996ea65f27ee3a7f4e0bfeafe16ee0be8dc924d))
* rather than docs:, deliberately. The correction only reaches anyone ([7a7d960](https://github.com/GabrielCpp/stablemate/commit/7a7d960a12679c7d1633cf416889bbbb381399a1))
* remove groom wall-clock budget alerts ([79a8dad](https://github.com/GabrielCpp/stablemate/commit/79a8dad16d5900c9d7fdef006fa9e5c7cf4b837d))
* **workhorse:** a failed status answer may not end the run ([b70d293](https://github.com/GabrielCpp/stablemate/commit/b70d2935be12217c306cf04f1eebdc5c3fa1f58e))
* **workhorse:** align a spawned agent's $PWD with its cwd ([4f93cf9](https://github.com/GabrielCpp/stablemate/commit/4f93cf94559a4197bb144449222d91a53004f19f))
* **workhorse:** describe the Python engine, not the retired YAML one ([7a7d960](https://github.com/GabrielCpp/stablemate/commit/7a7d960a12679c7d1633cf416889bbbb381399a1))
* **workhorse:** distinguish interruptions from failures ([59e6379](https://github.com/GabrielCpp/stablemate/commit/59e6379ec49de9c79ec1305dd9405d315a645a76))
* **workhorse:** expose active waits to telemetry ([a14ed02](https://github.com/GabrielCpp/stablemate/commit/a14ed026169327c1ca9fff8cd0e026beff45f3ee))
* **workhorse:** keep the power tier an opaque operator-defined string ([c9f0a87](https://github.com/GabrielCpp/stablemate/commit/c9f0a8702ce99ade54f6bda1cef03f8fe8bdf9e9))
* **workhorse:** let a control request interrupt a cap wait ([e4ead70](https://github.com/GabrielCpp/stablemate/commit/e4ead7030b67af860d5f6deae3d4b026a1ab94c9))
* **workhorse:** make container telemetry actually reach groom ([7bf5f95](https://github.com/GabrielCpp/stablemate/commit/7bf5f95b8bcf7f04519d9619fd9a1560fe014b68))
* **workhorse:** make the otel sdk a required dependency ([9985787](https://github.com/GabrielCpp/stablemate/commit/998578789c97c8e7a974d15f0ff4d222e8dcf6e2))
* **workhorse:** make the params-aware labels hook type-legal ([9fab883](https://github.com/GabrielCpp/stablemate/commit/9fab8835347bf86df688905dab0da2e5c9f72a10))
* **workhorse:** mark the spans a reload closes as cut short ([27939dc](https://github.com/GabrielCpp/stablemate/commit/27939dc9d6ddafb9970ca1b47df6a8c46fa99512))
* **workhorse:** parse operator gate headings as Markdown ([4115255](https://github.com/GabrielCpp/stablemate/commit/4115255551563b82934f540efc59cef2953a5294))
* **workhorse:** reload the libraries a workflow imports too ([4036a2c](https://github.com/GabrielCpp/stablemate/commit/4036a2c478dbd3c52242c2b78b0c3c0092b2a8eb))
* **workhorse:** report a failure on one span, not one per frame ([c7feb26](https://github.com/GabrielCpp/stablemate/commit/c7feb26a2601f275e53078583f6a1049f1e6602d))
* **workhorse:** resolve skill_load_ref, and preflight it as a reference ([d67b436](https://github.com/GabrielCpp/stablemate/commit/d67b43666e99d3c0f99dac53e011d919ce3b60db))
* **workhorse:** retry a turn that never reached the API ([46a3352](https://github.com/GabrielCpp/stablemate/commit/46a3352df5b78ea2c7668327e7873c92531091a9))
* **workhorse:** share one reload policy with the ladder's waits ([79d8aee](https://github.com/GabrielCpp/stablemate/commit/79d8aee56d0de33d4585a63e99afa3227c32b6c6))
* **workhorse:** stamp a successful run terminal, not aborted ([5854c66](https://github.com/GabrielCpp/stablemate/commit/5854c66ded6b4bc61baee32277ac3dfaee45d598))
* **workhorse:** stop a deliberate reload counting as the run's error ([92d2bbf](https://github.com/GabrielCpp/stablemate/commit/92d2bbf6ba9b7c4ff99d558511fdddaa6308c4b0))
* **workhorse:** stop a price table being read as a token count ([e2f5c3c](https://github.com/GabrielCpp/stablemate/commit/e2f5c3c791480bdc5cc82fc8184b36071f433dfb))
* **workhorse:** wait out an outage instead of answering for a node ([1b8bd08](https://github.com/GabrielCpp/stablemate/commit/1b8bd08178a6787f0960fd04b65a16cd799c0b68))


### Code Refactoring

* move the scriptutil helpers from workhorse into workflows' kit ([1360d56](https://github.com/GabrielCpp/stablemate/commit/1360d5610c7e89e0dd5cb44f7d48f92fb8fb8170))
* **workhorse:** drop the unused scriptutil helpers ([c850681](https://github.com/GabrielCpp/stablemate/commit/c850681191140241e1661de735403e1fbc1a6346))
* **workhorse:** supervise the container from Python, not shell ([6de875f](https://github.com/GabrielCpp/stablemate/commit/6de875f4ed47803201c1aedb2a9de676b15f110b))
* **workhorse:** wait for the operator answer, not for a touch ([2ac5db7](https://github.com/GabrielCpp/stablemate/commit/2ac5db7f598cba467dc6e980e7623b9c0b59d9d8))

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/workhorse-agent-v0.8.0...workhorse-agent-v1.0.0) (2026-08-02)


### Code Refactoring

* vendor stablemate-core into workhorse and farrier ([0bef8ff](https://github.com/GabrielCpp/stablemate/commit/0bef8ff23771bc11992d9f33ae790604359d2804))
