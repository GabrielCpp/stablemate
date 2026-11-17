story: none
date: 2026-11-17
elements: ValidateWebPlan, ValidatePhonePlan, RunWebPlan, RunPhonePlan, RunGrpcPlan, VetWithoutArguments, VetWithoutRegions, VetOfUnknownStory, VetDryRun, EnvUpUnknown

Some commands a person types need a machine the sandbox is not: a browser, a phone, a gRPC service, a screenshot or a
running stack. The book declares them, plays the answers the sandbox can produce, and declares the others unseen with
the runtime they need.

`qa run` of a browser plan and of a phone plan is refused before anything starts. The plans read a secret from an
environment variable the sandbox does not set, and the run checks the machine and the secrets first and prints
`QA run blocked:` and one line for each thing missing. A machine without Playwright, ffmpeg, Maestro or adb adds lines to
that list, so the book leaves every line opaque and judges the exit code. A passing run needs a browser or a device and the
secret, and `Unseen(..., Because.RUNTIME, ...)` says so. `qa validate` of both plans passes, because it reads the plan
and starts nothing.

`qa run` of a plan that calls a gRPC service nothing serves runs, and the call fails, so the run answers
`QA run FAILED: 0 assertions passed, 1 failed, 1 scenarios`. The plan names `localhost:1`, where nothing listens, and the
failure is the same with or without `grpcurl` installed. A pass needs a service that answers.

`ostler vet` takes a screenshot, a manifest and either a regions file or a browser address. The book plays the usage
refusal with no arguments, a regions file that is not there and a story that does not exist, and a dry run against a regions
file that lists no region, which is clean and writes nothing. The sandbox holds no image, so the dry run names a screenshot
that does not exist, and the check does not read it when no region asks for a crop. The `--write` path, the `--cdp-url`
scan of a live browser and a report that is not clean are not played.

`ostler env up` of a book with no stack is refused before a container, a lease or a checkout is touched. A bring-up of the
demo book would pull and start an image, and the book does not play that. An earlier pass of this book started one by
mistake and tore it down with `env down`; the image layer stays in the machine's cache.
