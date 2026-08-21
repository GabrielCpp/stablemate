package main

import (
	"encoding/json"
	"net/http"

	"example.com/claims-api/gen"
)

// DecideClaim approves or denies a submitted claim.
//
// The role gate comes before the lookup on purpose: a holder who probes claim addresses
// learns nothing from a 403 about whether the claim is there, and a 404 handed out first
// would have told them.
func (s *Server) DecideClaim(w http.ResponseWriter, r *http.Request, id string) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
		return
	}
	if !identity.IsAdjuster() {
		writeProblem(w, http.StatusForbidden, "Adjusters Only",
			"Deciding a claim is an adjuster action.")
		return
	}

	var body gen.Decision
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeProblem(w, http.StatusBadRequest, "Malformed Request", "The body was not a JSON object.")
		return
	}
	problems := map[string]string{}
	if body.Decision != gen.Approve && body.Decision != gen.Deny {
		problems["decision"] = "The decision must be `approve` or `deny`."
	}
	if body.Version <= 0 {
		problems["version"] = "The claim's current version must be quoted."
	}
	if len(problems) > 0 {
		writeJSON(w, http.StatusUnprocessableEntity, gen.FieldErrors{Errors: problems})
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
	claim := ledger.Claims[at]
	if body.Decision == gen.Approve {
		claim.Status = "Approved"
	} else {
		claim.Status = "Denied"
	}
	if body.Note != nil {
		claim.DecisionNote = *body.Note
	}
	claim.Version++
	ledger.Claims[at] = claim
	if err := s.Store.Write(ledger); err != nil {
		writeProblem(w, http.StatusInternalServerError, "Ledger Unavailable", "")
		return
	}
	writeJSON(w, http.StatusOK, gen.ClaimEnvelope{Claim: apiClaim(claim)})
}
