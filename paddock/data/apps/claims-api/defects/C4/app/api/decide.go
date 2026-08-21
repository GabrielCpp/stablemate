package main

import (
	"encoding/json"
	"net/http"

	"example.com/claims-api/gen"
)

// DecideClaim approves or denies a submitted claim.
//
// The refusals are ordered cheapest first: an id that is not on the books is answered
// before the caller's role is asked about, so a decision on a claim nobody filed costs one
// lookup rather than a permission check as well.
func (s *Server) DecideClaim(w http.ResponseWriter, r *http.Request, id string) {
	identity, ok := caller(r)
	if !ok {
		unauthorized(w, "The request carried no verified identity.")
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
	// The quoted version is the adjuster's evidence that they read the claim they are
	// deciding. If it is not the version on file, something happened between the reading and
	// the decision, and the decision is refused rather than applied to a claim nobody read.
	if !identity.IsAdjuster() {
		writeProblem(w, http.StatusForbidden, "Adjusters Only",
			"Deciding a claim is an adjuster action.")
		return
	}
	if ledger.Claims[at].Version != body.Version {
		writeProblem(w, http.StatusConflict, "Stale Decision",
			"The claim has changed since it was read. Re-read it and decide again.")
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
