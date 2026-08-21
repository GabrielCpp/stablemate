package main

import (
	"encoding/json"
	"net/http"

	"example.com/claims-api/gen"
)

// Server implements the generated ServerInterface over the claim ledger. Each operation
// lives in a file of its own; what stays here is what every one of them shares.
type Server struct {
	Store *Store
}

// GetHealth answers whatever is waiting on the process to come up. It is the one operation
// `openapi.yml` leaves unsecured, so it is also the one that reaches a handler without an
// identity in the context.
func (s *Server) GetHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, gen.Health{Status: "ok"})
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
