package main

import (
	"fmt"
	"regexp"
	"strings"
)

// PolicyInput is what a create or an edit sends. `Version` is a pointer so that "absent"
// and "zero" are different requests: an edit that forgot the token is refused, an edit
// quoting version 0 is merely stale.
type PolicyInput struct {
	PolicyNumber    string  `json:"policy_number"`
	HolderEmail     string  `json:"holder_email"`
	CoverageType    string  `json:"coverage_type"`
	VehicleVIN      string  `json:"vehicle_vin"`
	PropertyAddress string  `json:"property_address"`
	StartDate       string  `json:"start_date"`
	EndDate         string  `json:"end_date"`
	Premium         float64 `json:"premium"`
	Version         *int    `json:"version"`
	Confirm         string  `json:"confirm"`
}

var (
	emailPattern = regexp.MustCompile(`^[^@\s]+@[^@\s]+\.[^@\s]+$`)
	datePattern  = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
)

// coverageTypes is the enum, in the order the form offers it.
var coverageTypes = []string{"auto", "home", "umbrella"}

// premiumBand is the accepted premium range for one coverage type. The bounds differ per
// type because an umbrella policy priced like a starter auto policy is not an umbrella
// policy; the minimum is the part the book makes normative.
type premiumBand struct{ Min, Max float64 }

var premiumBands = map[string]premiumBand{
	"auto":     {Min: 100, Max: 10000},
	"home":     {Min: 150, Max: 20000},
	"umbrella": {Min: 200, Max: 50000},
}

// Validate returns one message per offending field, keyed by the field's name — the same
// key the form uses for its inline message, so the two layers cannot describe a refusal
// differently. An empty map means the input is acceptable.
//
// `today` is passed in rather than read from the clock so that the start-date rule is
// observable: a scenario can state the day it is asking about.
func Validate(in PolicyInput, ledger Ledger, today string, isCreate bool) map[string]string {
	errs := map[string]string{}

	// The policy number is what the id is derived from, so it is settled at creation and
	// an edit neither sends it nor may change it.
	if isCreate && strings.TrimSpace(in.PolicyNumber) == "" {
		errs["policy_number"] = "Policy number is required."
	}
	if strings.TrimSpace(in.HolderEmail) == "" {
		errs["holder_email"] = "Holder email is required."
	} else if !emailPattern.MatchString(strings.TrimSpace(in.HolderEmail)) {
		errs["holder_email"] = "Holder email must look like name@example.com."
	}

	if !contains(coverageTypes, in.CoverageType) {
		errs["coverage_type"] = "Choose a coverage type: auto, home or umbrella."
	}

	switch in.CoverageType {
	case "home":
		if strings.TrimSpace(in.PropertyAddress) == "" {
			errs["property_address"] = "Home coverage needs the property address."
		}
	case "umbrella":
		if !hasUnderlyingPolicy(ledger, in.HolderEmail, in.PolicyNumber) {
			errs["coverage_type"] = "Umbrella coverage needs an existing auto or home policy for this holder."
		}
	}

	if !datePattern.MatchString(in.StartDate) {
		errs["start_date"] = "Start date is required, as YYYY-MM-DD."
	} else if isCreate && in.StartDate < today {
		errs["start_date"] = "Start date cannot be in the past."
	}
	if !datePattern.MatchString(in.EndDate) {
		errs["end_date"] = "End date is required, as YYYY-MM-DD."
	} else if datePattern.MatchString(in.StartDate) && in.EndDate <= in.StartDate {
		errs["end_date"] = "End date must be after the start date."
	}

	if band, ok := premiumBands[in.CoverageType]; ok {
		if in.Premium < band.Min || in.Premium > band.Max {
			errs["premium"] = fmt.Sprintf(
				"Premium for %s coverage must be between %.0f and %.0f.",
				in.CoverageType, band.Min, band.Max,
			)
		}
	} else if in.Premium <= 0 {
		errs["premium"] = "Premium must be a positive amount."
	}

	return errs
}

// hasUnderlyingPolicy answers the umbrella prerequisite: this holder already has a live
// non-umbrella policy on file. The cross-record shape is the point — it cannot be decided
// from the form alone, so a client that checks it is reading the ledger too.
func hasUnderlyingPolicy(ledger Ledger, email, self string) bool {
	for _, policy := range ledger.Policies {
		if policy.PolicyNumber == self || policy.CoverageType == "umbrella" {
			continue
		}
		if policy.Status != "Cancelled" && strings.EqualFold(policy.HolderEmail, email) {
			return true
		}
	}
	return false
}

func contains(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
