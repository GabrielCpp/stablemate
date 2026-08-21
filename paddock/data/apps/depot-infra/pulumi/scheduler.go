package main

import (
	"github.com/pulumi/pulumi-gcp/sdk/v8/go/gcp/cloudscheduler"
	"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

// deploySweep declares the nightly job that expires artifacts nobody kept.
//
// The schedule carries an explicit time zone. A cron expression with none is interpreted in
// UTC by the API, which is a different hour from the one whoever wrote "03:00" meant, and
// the drift is invisible until the sweep runs during a working day.
func deploySweep(ctx *pulumi.Context, on pulumi.ResourceOption) error {
	_, err := cloudscheduler.NewJob(ctx, "artifact-sweep", &cloudscheduler.JobArgs{
		Name:        pulumi.String("depot-artifact-sweep"),
		Description: pulumi.String("Expires depot artifacts older than the retention window."),
		Schedule:    pulumi.String("0 3 * * *"),
		TimeZone:    pulumi.String("Etc/UTC"),
		HttpTarget: &cloudscheduler.JobHttpTargetArgs{
			Uri:        pulumi.String("https://depot.example.com/internal/sweep"),
			HttpMethod: pulumi.String("POST"),
		},
	}, on)
	return err
}
