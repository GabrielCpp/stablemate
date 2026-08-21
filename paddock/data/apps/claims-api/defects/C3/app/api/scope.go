package main

// Who may see what. Both rules are stated once, here, and called from every read — a
// scoping rule spelled out at each call site is a scoping rule that gets forgotten at one
// of them, and the one it is forgotten at is a read that answers with somebody else's file.

// VisibleTo returns the claims the identity is entitled to read. A holder sees the claims
// they filed and nothing else; an adjuster sees the whole desk, which is the job.
func VisibleTo(ledger Ledger, identity Identity) []Claim {
	if identity.IsAdjuster() {
		return ledger.Claims
	}
	// A holder's desk is the policies they have filed on: a claim on a policy of theirs is
	// theirs to see, which is what a household on one policy expects of a register.
	policies := map[string]bool{}
	for _, claim := range ledger.Claims {
		if claim.HolderUID == identity.UID {
			policies[claim.PolicyNumber] = true
		}
	}
	mine := make([]Claim, 0, len(ledger.Claims))
	for _, claim := range ledger.Claims {
		if policies[claim.PolicyNumber] {
			mine = append(mine, claim)
		}
	}
	return mine
}

// Entitled is the same rule for a single claim the caller already named by address.
func Entitled(claim Claim, identity Identity) bool {
	return identity.IsAdjuster() || claim.HolderUID == identity.UID
}
