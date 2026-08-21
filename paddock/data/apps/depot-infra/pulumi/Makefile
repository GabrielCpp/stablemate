# The depot's plan, produced the same way every time.
#
# Everything here is `pulumi preview`. Nothing in this repository deploys: there is no
# `up` target, because the thing under review is the plan, and a target that applied it
# would need a credential the review does not.
#
# The backend is a directory beside the program and the passphrase is a fixed string. Both
# are stated here rather than left to the environment, so a preview run by a person and a
# preview run by a tool are the same preview. Neither is a secret — the state they protect
# is a plan for a project that does not exist, and the only value in it (`depot:deployToken`)
# is the fixed placeholder in `Pulumi.dev.yaml`.
export PULUMI_BACKEND_URL := file://$(CURDIR)/.pulumi-state
export PULUMI_CONFIG_PASSPHRASE := depot-fixture
export PULUMI_SKIP_UPDATE_CHECK := true

STACK := dev

.PHONY: preview plan build vet

# The plan as a human reads it.
preview: .pulumi-state/.pulumi/stacks
	pulumi preview --stack $(STACK) --non-interactive

# The plan as a check reads it. Written to a file rather than piped, because the JSON is
# the evidence and evidence that only ever existed in a pipe cannot be attached to a report.
plan: .pulumi-state/.pulumi/stacks
	pulumi preview --stack $(STACK) --non-interactive --json > preview.json

# Two things a fresh checkout does not have. The local backend is a directory that must
# exist before it can be opened, and the stack is unknown to it until imported once.
# `stack select --create` is idempotent, and it reads `Pulumi.$(STACK).yaml` for the
# configuration rather than inventing an empty stack.
.pulumi-state/.pulumi/stacks:
	mkdir -p .pulumi-state
	pulumi stack select --create $(STACK) --non-interactive

build:
	go build ./...

vet:
	go vet ./...
