// Package main is the depot's infrastructure program: what the artifact depot is made of,
// declared once and planned by `pulumi preview` before anything is applied.
//
// Nothing here runs a service. The program's whole observable behaviour is the plan it
// produces — which resources, with which properties, granted to which members — so the
// preview JSON is the artifact to read, and `make preview` is how to get it.
package main

import (
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi/config"
)

// providerVersion pins the GCP provider the plan is produced by.
//
// A pin rather than "whatever resolves today": a provider upgrade changes defaults, and a
// default that changes underneath an unpinned program rewrites resources nobody edited.
// The version is stated here, at the provider, rather than left to the plugin the machine
// happens to have installed.
const providerVersion = "8.16.0"

func main() {
	pulumi.Run(func(ctx *pulumi.Context) error {
		cfg := config.New(ctx, "gcp")
		provider, err := gcp.NewProvider(ctx, "gcp", &gcp.ProviderArgs{
			Project: pulumi.String(cfg.Require("project")),
			Region:  pulumi.String(cfg.Require("region")),
		}, pulumi.Version(providerVersion))
		if err != nil {
			return err
		}
		on := pulumi.Provider(provider)

		return artifactStore(ctx, on)
	})
}
