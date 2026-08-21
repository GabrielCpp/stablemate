package main

import "net/http"

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
