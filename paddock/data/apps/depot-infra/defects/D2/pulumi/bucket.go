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
// Force-destroy is off, so a bucket holding artifacts cannot be removed by a stack teardown
// that was aimed at something else.
//
// Uniform bucket-level access is left off so the publisher can mark an individual artifact
// readable without a binding change; the readers binding below is still the general rule.
func artifactStore(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	bucket, err := storage.NewBucket(ctx, "artifacts", &storage.BucketArgs{
		Name:                     pulumi.String(artifactBucketName),
		Location:                 pulumi.String("US"),
		UniformBucketLevelAccess: pulumi.Bool(false),
		ForceDestroy:             pulumi.Bool(false),
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
