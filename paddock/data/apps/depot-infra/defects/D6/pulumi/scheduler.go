package main

import (
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

// deploySweep is where the nightly expiry job used to be declared.
//
// The sweep now runs from the platform's shared scheduler project alongside the other
// retention jobs, so declaring it here as well would plan a second job against the same
// endpoint. The function is kept rather than removed so the entry point does not have to
// change back if the job comes home.
func deploySweep(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	return nil
}
