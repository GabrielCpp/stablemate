package main

import (
	"net/http"
	"sort"
)

func (s *Server) handleList(w http.ResponseWriter, _ *http.Request) {
	ledger, err := s.Store.Read()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unreadable", err.Error())
		return
	}
	policies := append([]Policy{}, ledger.Policies...)
	sort.Slice(policies, func(i, j int) bool {
		return policies[i].PolicyNumber < policies[j].PolicyNumber
	})
	writeJSON(w, http.StatusOK, map[string]any{"policies": policies})
}
