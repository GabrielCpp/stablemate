package main

import (
	"net/http"

	"example.com/claims-api/gen"
)

// GetClaim answers with one claim, if the caller is entitled to it. The order of the two
// refusals is deliberate: an unknown id is a 404 before entitlement is asked about, and a
// known id the caller may not read is a 403 — so the pair never reveals which claims exist
// by answering differently for a stranger's claim than for one that was never filed.
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
