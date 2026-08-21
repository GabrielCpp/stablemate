package main

import (
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/projects"
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/secretmanager"
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/serviceaccount"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi/config"
)

// deployIdentity declares the account CI deploys as, and the one grant it holds.
//
// The grant is at the project rather than on one bucket. CI publishes artifacts today and
// will want the registry and the function bucket next; granting each one separately means a
// pipeline change waits on an infrastructure change, so the account is given the editor role
// once and the additions cost nothing.
func deployIdentity(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	cfg := config.New(ctx, "gcp")
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

	_, err = projects.NewIAMMember(ctx, "deployer-writes-artifacts", &projects.IAMMemberArgs{
		Project: pulumi.String(cfg.Require("project")),
		Role:    pulumi.String("roles/editor"),
		Member:  member,
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
