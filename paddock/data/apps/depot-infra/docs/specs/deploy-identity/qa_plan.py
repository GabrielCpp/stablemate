"""The frozen QA plan for `deploy-identity`.

Same mechanism as story 1 — `make -C pulumi plan`, and the JSON it writes — and the same two
opted-in tools. Nothing serves, so nothing is reached.

Two criteria here are negatives, and a negative cannot be read off the resource the story
declares. "No project-level role" is a property of the whole plan: a second, wider grant
beside the narrow one is the defect, and every assertion that reads the narrow grant passes
in its presence. The same goes for the sweep's uniqueness. Both are therefore written as
enumerations over every step, not as lookups.
"""

import json

from ostler_qa import Qa, plan, scenario, target


plan(run_id="qa-deploy-identity", story="deploy-identity")

depot = target("depot", driver="python")

# Obligation ids are written out in full at every assertion, never factored into a constant:
# `ostler qa validate` reads a `covers=` list statically off the AST, so a computed id claims
# nothing. See story 1's plan for the same note.

DEPLOYER = "serviceAccount:depot-deployer@depot-example.iam.gserviceaccount.com"
PINNED_PROVIDER = "8.16.0"


def the_plan(qa: Qa) -> dict:
    """Take a plan the documented way, and hand back what it says."""
    built = qa.tool("make").run("-C", "pulumi", "build", timeout=900.0)
    qa.require("the program builds", built.ok, actual=built.stderr[-2000:], covers=["ac:5", "okf:docs/features/depot/ops/depot-stack.md:contract"])

    planned = qa.tool("make").run("-C", "pulumi", "plan", timeout=900.0)
    qa.require("the documented plan command produces a plan", planned.ok, actual=planned.stderr[-2000:], covers=["ac:5", "okf:docs/features/depot/ops/depot-stack.md:contract"])

    read = qa.tool("jq").run(".", "pulumi/preview.json", timeout=120.0)
    qa.require("the plan it wrote is readable JSON", read.ok, actual=read.stderr[-2000:], covers=["ac:5", "okf:docs/features/depot/ops/depot-stack.md:contract"])
    return json.loads(read.stdout)


def resources(planned: dict) -> dict:
    """The plan's steps, keyed by resource name; see story 1's plan for why in Python."""
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
        "ac:5",
        "okf:docs/features/depot/concepts/deploy-identity.md:consistency:1",
        "okf:docs/features/depot/concepts/deploy-identity.md:consistency:2",
        "okf:docs/features/depot/concepts/deploy-identity.md:contract",
        "okf:docs/features/depot/ops/depot-stack.md:contract",
    ],
    preconditions=[
        "the stack's local backend is empty, so every resource in the plan is a create",
        "the plan is taken by the documented command rather than by invoking pulumi directly",
    ],
    checkpoints=[
        "the plan declares the deploy identity",
        "the identity holds exactly one grant",
        "that grant is bucket-level, on the artifact store, naming an object-level role",
        "no IAM resource anywhere in the plan is a project-level one",
    ],
    forbid=[
        "reading the narrow grant and calling that a proof about every grant",
        "asserting the role string without asserting the resource it was granted on",
    ],
)
def the_deploy_identity_holds_one_grant_and_it_is_at_the_bucket(qa: Qa) -> None:
    """One identity, one grant — and the enumeration that says there is no second one."""
    planned = the_plan(qa)
    declared = resources(planned)

    qa.require(
        "the plan declares the deploy identity",
        declared.get("deployer", {}).get("type") == "gcp:serviceaccount/account:Account",
        actual=sorted(declared),
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:contract"],
    )
    qa.verify(
        "json_path",
        declared["deployer"],
        path="$.inputs.accountId",
        equals="depot-deployer",
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:contract"],
    )

    # Every IAM resource in the plan, not the one this story is proud of. A grant that widened
    # arrives as an extra step, and a lookup of the narrow one never sees it.
    grants = {
        name: entry
        for name, entry in declared.items()
        if "iam" in entry["type"].lower()
    }
    to_the_deployer = sorted(
        name for name, entry in grants.items() if entry["inputs"].get("member") == DEPLOYER
    )
    qa.check(
        "the deploy identity is named by exactly one grant in the whole plan",
        to_the_deployer == ["deployer-writes-artifacts"],
        actual=to_the_deployer,
        expected=["deployer-writes-artifacts"],
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:1"],
    )

    grant = declared.get("deployer-writes-artifacts", {})
    qa.check(
        "that grant is a bucket-level one on the artifact store",
        grant.get("type") == "gcp:storage/bucketIAMMember:BucketIAMMember"
        and grant.get("inputs", {}).get("bucket") == "depot-artifacts-example",
        actual={"type": grant.get("type"), "bucket": grant.get("inputs", {}).get("bucket")},
        expected={"type": "gcp:storage/bucketIAMMember:BucketIAMMember", "bucket": "depot-artifacts-example"},
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:1"],
    )
    qa.verify(
        "json_path",
        grant,
        path="$.inputs.role",
        equals="roles/storage.objectAdmin",
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:1"],
    )

    # The negative, over the plan rather than over a name: any IAM resource whose type says
    # `projects/` binds at the project, whichever role it carries and whoever it names.
    project_level = sorted(name for name, entry in grants.items() if "projects/" in entry["type"])
    qa.check(
        "no IAM resource in the plan binds a role at the project",
        project_level == [],
        actual=project_level,
        expected=[],
        covers=["ac:1", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:2"],
    )

    qa.verify(
        "json_path",
        declared.get("gcp", {}),
        path="$.inputs.version",
        equals=PINNED_PROVIDER,
        covers=["ac:5", "okf:docs/features/depot/ops/depot-stack.md:contract"],
    )
    json.dump(
        {"grants": grants, "changeSummary": planned["changeSummary"]},
        qa.artifact("steps/grants.json", kind="json").open("w"),
    )


@scenario(
    target=depot,
    mechanism="live",
    timeout=1800.0,
    covers=[
        "ac:2",
        "ac:3",
        "okf:docs/features/depot/concepts/deploy-identity.md:consistency:3",
    ],
    preconditions=[
        "the deploy token is held in the stack's own configuration, encrypted",
    ],
    checkpoints=[
        "the plan reports the configured deploy token as `[secret]`",
        "the token reaches the secret version as a secret value rather than as itself",
    ],
    forbid=[
        "asserting the secret version exists without asserting what the plan printed for it",
        "reading the stack's configuration file instead of the plan the program produced",
    ],
)
def the_deploy_token_is_a_secret_everywhere_the_plan_shows_it(qa: Qa) -> None:
    """What a preview prints, which is the only place this token is ever visible."""
    planned = the_plan(qa)
    declared = resources(planned)

    # The config block, because that is where a token stored in the clear surfaces: the
    # resource graph is identical either way, and only the plan's own header differs.
    qa.verify(
        "json_path",
        planned,
        path="$.config.depot:deployToken",
        equals="[secret]",
        covers=["ac:3", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:3"],
    )

    qa.require(
        "the plan declares the secret version holding the deploy token",
        declared.get("deploy-token-v1", {}).get("type") == "gcp:secretmanager/secretVersion:SecretVersion",
        actual=sorted(declared),
        covers=["ac:2", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:3"],
    )
    qa.verify(
        "json_path",
        declared["deploy-token-v1"],
        path="$.inputs.secretData",
        equals="[secret]",
        covers=["ac:2", "okf:docs/features/depot/concepts/deploy-identity.md:consistency:3"],
    )
    json.dump(
        {"config": planned["config"], "secretVersion": declared["deploy-token-v1"]},
        qa.artifact("steps/deploy-token.json", kind="json").open("w"),
    )


@scenario(
    target=depot,
    mechanism="live",
    timeout=1800.0,
    covers=[
        "ac:4",
        "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:1",
        "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:2",
        "okf:docs/features/depot/concepts/artifact-sweep.md:contract",
    ],
    preconditions=[
        "the plan is taken from the same tree, by the same documented command",
    ],
    checkpoints=[
        "the plan declares exactly one Cloud Scheduler job",
        "that job is the artifact sweep",
        "it runs at 03:00, nightly",
        "its time zone is stated absolutely, as `Etc/UTC`",
    ],
    forbid=[
        "reading the sweep by name and calling that a count",
        "accepting a schedule without its time zone",
    ],
)
def the_artifact_sweep_is_the_only_job_and_it_runs_nightly_at_three(qa: Qa) -> None:
    """A resource whose absence is a shorter plan and no error at all."""
    declared = resources(the_plan(qa))

    jobs = sorted(name for name, entry in declared.items() if entry["type"] == "gcp:cloudscheduler/job:Job")
    # A count over the plan. Looking the sweep up by name would pass on a plan carrying a
    # second job beside it, which is the half of this criterion that is not about the sweep.
    qa.verify("count", jobs, equals=1, subject="Cloud Scheduler jobs in the plan", covers=["ac:4", "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:1"])
    qa.require(
        "the one scheduler job in the plan is the artifact sweep",
        jobs == ["artifact-sweep"],
        actual=jobs,
        expected=["artifact-sweep"],
        covers=["ac:4", "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:1", "okf:docs/features/depot/concepts/artifact-sweep.md:contract"],
    )

    sweep = declared["artifact-sweep"]
    qa.verify("json_path", sweep, path="$.inputs.schedule", equals="0 3 * * *", covers=["ac:4", "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:2"])
    # Asserted beside the schedule rather than after it: `0 3 * * *` in an unstated zone is a
    # different hour on every machine, so the two fields are one claim.
    qa.verify("json_path", sweep, path="$.inputs.timeZone", equals="Etc/UTC", covers=["ac:4", "okf:docs/features/depot/concepts/artifact-sweep.md:consistency:2"])
    json.dump({"jobs": jobs, "sweep": sweep}, qa.artifact("steps/artifact-sweep.json", kind="json").open("w"))
