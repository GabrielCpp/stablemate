"""The frozen QA plan for `artifact-store`.

Nothing in this repo serves, so there is no target to reach: the mechanism is
`make -C pulumi plan`, and the evidence is the JSON it writes. `agents.yml` opts this app's
QA into `make` and `jq` for that, and into nothing else — no credential is needed and no
Google API is reached, because a preview resolves against the provider plugin rather than
the cloud.

The plan is taken once per scenario rather than shared, so a scenario that runs alone proves
what it proves when run alone. It costs a second preview and buys independence.

`jq` is what reads the file. A plan is a document on disk, and reading it here rather than
through a tool would mean the QA harness's own filesystem access is the thing under test.
"""

import json

from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-artifact-store", story="artifact-store")

depot = target("depot", driver="python")

# Every obligation id below is written out in full at every assertion that claims it, and
# never factored into a constant. `ostler qa validate` reads a `covers=` list statically, off
# the AST, so an id assembled from a name — an f-string, a join, a module constant — claims
# nothing at all and the evidence gate counts the assertion as absent. The repetition is the
# binding.

#: The provider the program pins, and so the version a plan taken from this tree must name.
PINNED_PROVIDER = "8.16.0"


def the_plan(qa: Qa) -> dict:
    """Take a plan the documented way, and hand back what it says.

    `make -C pulumi plan` is the command the ops page publishes; using it rather than
    invoking `pulumi` directly is what makes this evidence about the depot's documented
    route rather than about pulumi.
    """
    built = qa.tool("make").run("-C", "pulumi", "build", timeout=900.0)
    qa.require("the program builds", built.ok, actual=built.stderr[-2000:], covers=["ac:1", "okf:docs/features/depot/ops/depot-stack.md:contract"])

    planned = qa.tool("make").run("-C", "pulumi", "plan", timeout=900.0)
    qa.require("the documented plan command produces a plan", planned.ok, actual=planned.stderr[-2000:], covers=["ac:1", "okf:docs/features/depot/ops/depot-stack.md:contract"])

    read = qa.tool("jq").run(".", "pulumi/preview.json", timeout=120.0)
    qa.require("the plan it wrote is readable JSON", read.ok, actual=read.stderr[-2000:], covers=["ac:1", "okf:docs/features/depot/ops/depot-stack.md:contract"])
    return json.loads(read.stdout)


def resources(planned: dict) -> dict:
    """The plan's steps, keyed by resource name.

    A URN's last segment is the resource's name and the one before it is its type token.
    They are pulled apart here, in Python, because `json_path` walks dotted and indexed
    paths only — there is no filter expression that could say "the step whose URN ends
    `artifacts`", and indexing `steps[4]` would bind every assertion to an ordering the
    engine never promised.
    """
    found = {}
    for step in planned["steps"]:
        parts = step["urn"].split("::")
        found[parts[-1]] = {
            "type": parts[-2],
            "inputs": step.get("newState", {}).get("inputs", {}),
        }
    return found


@scenario(
    target=depot,
    mechanism="live",
    timeout=1800.0,
    covers=[
        "ac:1",
        "ac:2",
        "ac:3",
        "ac:5",
        "okf:docs/features/depot/concepts/artifact-store.md:consistency:1",
        "okf:docs/features/depot/concepts/artifact-store.md:consistency:2",
        "okf:docs/features/depot/concepts/artifact-store.md:consistency:3",
        "okf:docs/features/depot/concepts/artifact-store.md:contract",
        "okf:docs/features/depot/ops/depot-stack.md:contract",
    ],
    preconditions=[
        "the stack's local backend is empty, so every resource in the plan is a create",
        "the plan is taken by the documented command rather than by invoking pulumi directly",
    ],
    checkpoints=[
        "the plan declares the artifact bucket",
        "uniform bucket-level access is on, stated by the program",
        "object versioning is on",
        "force-destroy is off",
        "the plan names the pinned provider version",
    ],
    forbid=[
        "reading a property the program never states and calling the provider's default a decision",
        "asserting the bucket exists without asserting what it was declared with",
    ],
)
def the_artifact_bucket_is_declared_with_its_safeties_on(qa: Qa) -> None:
    """The store the depot publishes into, and the three properties it does not inherit."""
    planned = the_plan(qa)
    declared = resources(planned)

    qa.require(
        "the plan declares the artifact bucket",
        "artifacts" in declared and qa.field(declared, "artifacts.type") == "gcp:storage/bucket:Bucket",
        actual=sorted(declared),
        covers=["ac:2", "okf:docs/features/depot/concepts/artifact-store.md:contract"],
    )
    bucket = declared["artifacts"]["inputs"]

    qa.check(
        "uniform bucket-level access is on, so the binding is the only thing deciding access",
        bucket.get("uniformBucketLevelAccess") is True,
        actual=bucket.get("uniformBucketLevelAccess"),
        expected=True,
        covers=["ac:2", "okf:docs/features/depot/concepts/artifact-store.md:consistency:1"],
    )
    qa.check(
        "object versioning is on",
        bucket.get("versioning", {}).get("enabled") is True,
        actual=bucket.get("versioning"),
        expected={"enabled": True},
        covers=["ac:3", "okf:docs/features/depot/concepts/artifact-store.md:consistency:3"],
    )
    # Read as `is False` rather than as falsy: an absent key is the provider's default
    # rather than the program's statement, and the two are exactly what this story is about.
    qa.check(
        "force-destroy is off, so destroying the stack cannot take the artifacts with it",
        bucket.get("forceDestroy") is False,
        actual=bucket.get("forceDestroy"),
        expected=False,
        covers=["ac:3", "okf:docs/features/depot/concepts/artifact-store.md:consistency:2"],
    )

    # The pin is asserted where the plan can show it: the provider step's own inputs. A plan
    # taken on a machine that already holds a plugin reports that plugin's version whether or
    # not the program asked for it, which is why `defects.yml` files the missing pin as the
    # auditor's row rather than expecting this assertion to fail on it.
    qa.verify(
        "json_path",
        declared.get("gcp", {}),
        path="$.inputs.version",
        equals=PINNED_PROVIDER,
        covers=["ac:5", "okf:docs/features/depot/ops/depot-stack.md:contract"],
    )
    json.dump(
        {"changeSummary": planned["changeSummary"], "bucket": bucket, "provider": declared.get("gcp")},
        qa.artifact("steps/artifact-bucket.json", kind="json").open("w"),
    )


@scenario(
    target=depot,
    mechanism="live",
    timeout=1800.0,
    covers=[
        "ac:4",
        "okf:docs/features/depot/concepts/artifact-store.md:consistency:4",
        "okf:docs/features/depot/concepts/artifact-store.md:consistency:5",
    ],
    preconditions=[
        "the plan is taken from the same tree, by the same documented command",
    ],
    checkpoints=[
        "the readers binding on the artifact bucket lists exactly the build group",
        "no member of that binding is a public one",
    ],
    forbid=[
        "asserting the build group is present without asserting who else is",
        "naming the public members to exclude one at a time",
    ],
)
def only_the_build_group_reads_the_artifact_store(qa: Qa) -> None:
    """Who may read the depot — asserted as the whole list, because a widening adds."""
    declared = resources(the_plan(qa))

    qa.require(
        "the plan declares a readers binding on the artifact bucket",
        "artifacts-readers" in declared,
        actual=sorted(declared),
        covers=["ac:4", "okf:docs/features/depot/concepts/artifact-store.md:consistency:4"],
    )
    binding = declared["artifacts-readers"]["inputs"]
    members = binding.get("members", [])

    # The whole list, compared as a whole. `"group:builds@example.com" in members` passes on a
    # binding that also holds `allUsers`, which is the defect this criterion exists for.
    qa.check(
        "the readers binding lists exactly the build group",
        members == ["group:builds@example.com"],
        actual=members,
        expected=["group:builds@example.com"],
        covers=["ac:4", "okf:docs/features/depot/concepts/artifact-store.md:consistency:4"],
    )
    qa.verify(
        "json_path",
        binding,
        path="$.bucket",
        equals="depot-artifacts-example",
        covers=["ac:4", "okf:docs/features/depot/concepts/artifact-store.md:consistency:4"],
    )
    # Stated as a property of every member rather than as two named exclusions, so a public
    # identifier this plan never anticipated is caught by the same assertion.
    public = [member for member in members if member in ("allUsers", "allAuthenticatedUsers")]
    qa.check(
        "no member of the readers binding is a public one",
        public == [],
        actual=public,
        expected=[],
        covers=["ac:4", "okf:docs/features/depot/concepts/artifact-store.md:consistency:5"],
    )
    json.dump({"binding": binding}, qa.artifact("steps/readers-binding.json", kind="json").open("w"))
