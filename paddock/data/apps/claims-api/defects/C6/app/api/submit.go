package main

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"

	"example.com/claims-api/gen"
)

var isoDate = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// SubmitClaim files a claim for the calling holder.
func (s *Server) SubmitClaim(w http.ResponseWriter, r *http.Request) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
		return
	}
	var body gen.ClaimSubmission
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeProblem(w, http.StatusBadRequest, "Malformed Request", "The body was not a JSON object.")
		return
	}
	if problems := validateSubmission(body); len(problems) > 0 {
		writeJSON(w, http.StatusUnprocessableEntity, gen.FieldErrors{Errors: problems})
		return
	}

	ledger, err := s.Store.Read()
	if err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	// One incident, one claim. The key is the holder's own subject rather than the policy
	// number alone, because two holders on the same policy filing for the same day are two
	// claims and not a duplicate.
	for i, claim := range ledger.Claims {
		if claim.HolderUID == identity.UID &&
			claim.PolicyNumber == body.PolicyNumber &&
			claim.IncidentDate == body.IncidentDate {
			// A second filing for one incident is the holder correcting the first, not a new
			// claim: the record already on file takes the new amount and description and keeps
			// its address, so the desk is left with one claim either way.
			claim.AmountCents = body.AmountCents
			claim.Description = body.Description
			ledger.Claims[i] = claim
			if err := s.Store.Write(ledger); err != nil {
				writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
				return
			}
			writeJSON(w, http.StatusCreated, gen.ClaimEnvelope{Claim: apiClaim(claim)})
			return
		}
	}

	claim := Claim{
		ID:           NextClaimID(&ledger),
		PolicyNumber: body.PolicyNumber,
		HolderUID:    identity.UID,
		IncidentDate: body.IncidentDate,
		AmountCents:  body.AmountCents,
		Description:  body.Description,
		Status:       "Submitted",
		Version:      1,
	}
	ledger.Claims = append(ledger.Claims, claim)
	if err := s.Store.Write(ledger); err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	writeJSON(w, http.StatusCreated, gen.ClaimEnvelope{Claim: apiClaim(claim)})
}

// validateSubmission decides every field rule in one pass and returns one message per
// field, so a caller with three problems learns about three rather than about the first.
func validateSubmission(body gen.ClaimSubmission) map[string]string {
	problems := map[string]string{}
	if strings.TrimSpace(body.PolicyNumber) == "" {
		problems["policy_number"] = "A policy number is required."
	}
	if !isoDate.MatchString(body.IncidentDate) {
		problems["incident_date"] = "The incident date must be a calendar date, as YYYY-MM-DD."
	}
	if body.AmountCents <= 0 {
		problems["amount_cents"] = "The claimed amount must be a positive number of cents."
	}
	if strings.TrimSpace(body.Description) == "" {
		problems["description"] = "A description of the incident is required."
	}
	return problems
}
