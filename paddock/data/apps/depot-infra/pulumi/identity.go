package main

import (
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/secretmanager"
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/serviceaccount"
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/storage"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi/config"
)

// deployIdentity declares the account CI deploys as, and the one grant it holds.
//
// The grant is the whole point of the file. It is a *bucket* IAM member on the artifact
// store alone — not a project role — so an identity that leaks buys the attacker the depot
// and nothing else in the project. `roles/storage.objectAdmin` on one bucket is the largest
// role this identity is ever meant to hold.
func deployIdentity(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	account, err := serviceaccount.NewAccount(ctx, "deployer", &serviceaccount.AccountArgs{
		AccountId:   pulumi.String("depot-deployer"),
		DisplayName: pulumi.String("Depot deploy identity"),
	}, on)
	if err != nil {
		return err
	}
	member := account.Email.ApplyT(func(email string) string {
		return "serviceAccount:" + email
	}).(pulumi.StringOutput)

	_, err = storage.NewBucketIAMMember(ctx, "deployer-writes-artifacts", &storage.BucketIAMMemberArgs{
		Bucket: pulumi.String(artifactBucketName),
		Role:   pulumi.String("roles/storage.objectAdmin"),
		Member: member,
	}, on)
	if err != nil {
		return err
	}

	return deploySecret(ctx, on)
}

// deploySecret declares where the deploy token lives, and takes its value from config.
//
// The value is read with `RequireSecret`, so it arrives encrypted in the stack file and
// stays a secret through the plan: a preview of this program prints the ciphertext, never
// the token. A plain `Require` here would put the token in `Pulumi.<stack>.yaml` in
// cleartext and in every preview output that names it.
func deploySecret(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	cfg := config.New(ctx, "depot")
	secret, err := secretmanager.NewSecret(ctx, "deploy-token", &secretmanager.SecretArgs{
		SecretId: pulumi.String("depot-deploy-token"),
		Replication: &secretmanager.SecretReplicationArgs{
			Auto: &secretmanager.SecretReplicationAutoArgs{},
		},
	}, on)
	if err != nil {
		return err
	}
	_, err = secretmanager.NewSecretVersion(ctx, "deploy-token-v1", &secretmanager.SecretVersionArgs{
		Secret:     secret.ID(),
		SecretData: pulumi.ToSecret(cfg.RequireSecret("deployToken")).(pulumi.StringOutput),
	}, on)
	return err
}
