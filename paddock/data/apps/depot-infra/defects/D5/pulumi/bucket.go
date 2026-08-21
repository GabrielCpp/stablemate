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
// Uniform bucket-level access is on, so access is decided by IAM alone and no object can
// carry an ACL that contradicts it.
//
// Force-destroy is on, because a stack that cannot be torn down cleanly leaves the next
// `pulumi up` stuck on a bucket the plan wants to replace.
func artifactStore(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	bucket, err := storage.NewBucket(ctx, "artifacts", &storage.BucketArgs{
		Name:                     pulumi.String(artifactBucketName),
		Location:                 pulumi.String("US"),
		UniformBucketLevelAccess: pulumi.Bool(true),
		ForceDestroy:             pulumi.Bool(true),
		Versioning: &storage.BucketVersioningArgs{
			Enabled: pulumi.Bool(true),
		},
	}, on)
	if err != nil {
		return err
	}

	// Readers are named one by one. The binding is authoritative for its role, so the
	// members listed here are the whole of who holds it — which is what makes the absence
	// of `allUsers` a property of the plan rather than of what nobody happened to add.
	_, err = storage.NewBucketIAMBinding(ctx, "artifacts-readers", &storage.BucketIAMBindingArgs{
		Bucket: bucket.Name,
		Role:   pulumi.String("roles/storage.objectViewer"),
		Members: pulumi.StringArray{
			pulumi.String("group:builds@example.com"),
		},
	}, on)
	return err
}
