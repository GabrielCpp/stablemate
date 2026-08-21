package main

import (
	"net/http"

	"example.com/claims-api/gen"
)

// ListClaims answers with the claims the caller is entitled to read. Which claims those are
// is decided by VisibleTo and nowhere else, so the register cannot widen by accident.
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
