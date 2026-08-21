package main

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"

	"example.com/claims-api/gen"
)

// Server implements the generated ServerInterface over the claim ledger.
type Server struct {
	Store *Store
}

var isoDate = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)

// GetHealth answers whatever is waiting on the process to come up. It is the one operation
// `openapi.yml` leaves unsecured, so it is also the one that reaches this file without an
// identity in the context.
func (s *Server) GetHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, gen.Health{Status: "ok"})
}

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
	for _, claim := range ledger.Claims {
		if claim.HolderUID == identity.UID &&
			claim.PolicyNumber == body.PolicyNumber &&
			claim.IncidentDate == body.IncidentDate {
			writeProblem(w, http.StatusConflict, "Duplicate Claim",
				"A claim for this policy and incident date is already on file.")
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

// ListClaims answers with the claims the caller is entitled to read.
func (s *Server) ListClaims(w http.ResponseWriter, r *http.Request) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
		return
	}
	ledger, err := s.Store.Read()
	if err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	visible := VisibleTo(ledger, identity)
	out := make([]gen.Claim, 0, len(visible))
	for _, claim := range visible {
		out = append(out, apiClaim(claim))
	}
	writeJSON(w, http.StatusOK, gen.ClaimList{Claims: out})
}

// GetClaim answers with one claim, if the caller is entitled to it.
func (s *Server) GetClaim(w http.ResponseWriter, r *http.Request, id string) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
		return
	}
	ledger, err := s.Store.Read()
	if err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	at := FindClaim(ledger, id)
	if at < 0 {
		writeProblem(w, http.StatusNotFound, "No Such Claim", "")
		return
	}
	if !Entitled(ledger.Claims[at], identity) {
		writeProblem(w, http.StatusForbidden, "Not Your Claim",
			"The claim is on file and belongs to another holder.")
		return
	}
	writeJSON(w, http.StatusOK, gen.ClaimEnvelope{Claim: apiClaim(ledger.Claims[at])})
}

// ResetClaims empties the ledger. It is the one destructive route, so it is the one route
// whose role gate a scenario is expected to prove from both sides.
func (s *Server) ResetClaims(w http.ResponseWriter, r *http.Request) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
		return
	}
	if !identity.IsAdjuster() {
		writeProblem(w, http.StatusForbidden, "Adjusters Only",
			"Emptying the ledger is an adjuster action.")
		return
	}
	if err := s.Store.Write(Ledger{Claims: []Claim{}, NextID: 1001}); err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	w.WriteHeader(http.StatusNoContent)
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

// apiClaim is the one place a stored claim becomes a response body. It is a conversion into
// the generated type rather than a hand-built object precisely so the field names cannot
// drift from `openapi.yml` without the compiler noticing.
func apiClaim(claim Claim) gen.Claim {
	out := gen.Claim{
		Id:           claim.ID,
		PolicyNumber: claim.PolicyNumber,
		HolderUid:    claim.HolderUID,
		IncidentDate: claim.IncidentDate,
		AmountCents:  claim.AmountCents,
		Description:  claim.Description,
		Status:       claim.Status,
		Version:      claim.Version,
	}
	if claim.DecisionNote != "" {
		note := claim.DecisionNote
		out.DecisionNote = &note
	}
	return out
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
