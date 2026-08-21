package main

import (
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/storage"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

// artifactBucketName is the depot's one bucket, named rather than generated so the deploy
// identity can be granted a role on it without the two files referring to each other.
const artifactBucketName = "depot-artifacts-example"

// artifactStore declares the bucket every build writes into, and who may read it.
//
// Two properties are the depot's posture rather than preferences. Uniform bucket-level
// access is on, so access is decided by IAM alone and no object can carry an ACL that
// contradicts it. Force-destroy is off, so a bucket holding artifacts cannot be removed by
// a stack teardown that was aimed at something else.
func artifactStore(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	bucket, err := storage.NewBucket(ctx, "artifacts", &storage.BucketArgs{
		Name:                     pulumi.String(artifactBucketName),
		Location:                 pulumi.String("US"),
		UniformBucketLevelAccess: pulumi.Bool(true),
		ForceDestroy:             pulumi.Bool(false),
		Versioning: &storage.BucketVersioningArgs{
			Enabled: pulumi.Bool(true),
		},
	}, on)
	if err != nil {
		return err
	}

	// Readers are named one by one. Release artifacts are linked from the public docs site,
	// so the anonymous reader is listed here beside the build group rather than granted by
	// hand later — the binding is authoritative for its role, and a grant made outside it
	// would be removed by the next apply.
	_, err = storage.NewBucketIAMBinding(ctx, "artifacts-readers", &storage.BucketIAMBindingArgs{
		Bucket: bucket.Name,
		Role:   pulumi.String("roles/storage.objectViewer"),
		Members: pulumi.StringArray{
			pulumi.String("group:builds@example.com"),
			pulumi.String("allUsers"),
		},
	}, on)
	return err
}
