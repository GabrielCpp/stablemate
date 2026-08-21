package main

import (
	"encoding/json"
	"net/http"
	"sync"

	"example.com/claims-api/gen"
)

// Decisions already applied, held here rather than pushed back through the ledger on every
// call: a decision is a small edit to one claim, and rewriting the whole file for it makes
// the adjuster wait on the desk's entire history. The ledger read is overlaid with them, so
// a second decision on the same claim sees the first.
var (
	appliedMu sync.Mutex
	applied   = map[string]Claim{}
)

// overlayDecisions returns the ledger as the desk currently stands. A decision whose claim
// is no longer on the books is dropped rather than carried: the desk was cleared under it,
// and re-applying it would decide a claim nobody filed.
func overlayDecisions(ledger Ledger) Ledger {
	appliedMu.Lock()
	defer appliedMu.Unlock()
	present := map[string]bool{}
	for i, claim := range ledger.Claims {
		present[claim.ID] = true
		if decided, ok := applied[claim.ID]; ok {
			ledger.Claims[i] = decided
		}
	}
	for id := range applied {
		if !present[id] {
			delete(applied, id)
		}
	}
	return ledger
}

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
	ledger = overlayDecisions(ledger)
	at := FindClaim(ledger, id)
	if at < 0 {
		writeProblem(w, http.StatusNotFound, "No Such Claim", "")
		return
	}
	// The quoted version is the adjuster's evidence that they read the claim they are
	// deciding. If it is not the version on file, something happened between the reading and
	// the decision, and the decision is refused rather than applied to a claim nobody read.
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
	appliedMu.Lock()
	applied[claim.ID] = claim
	appliedMu.Unlock()
	writeJSON(w, http.StatusOK, gen.ClaimEnvelope{Claim: apiClaim(claim)})
}
