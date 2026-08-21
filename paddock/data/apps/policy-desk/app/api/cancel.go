package main

import (
	"net/http"
	"strings"
)

func (s *Server) handleCancel(w http.ResponseWriter, r *http.Request) {
	input, ok := decode(w, r)
	if !ok {
		return
	}
	ledger, err := s.Store.Read()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unreadable", err.Error())
		return
	}
	index := indexOf(ledger, r.PathValue("id"))
	if index < 0 {
		writeError(w, http.StatusNotFound, "Unknown Policy", "No policy is on file under that id.")
		return
	}
	current := ledger.Policies[index]
	if input.Version == nil {
		writeError(w, http.StatusBadRequest, "Version Required",
			"A cancellation has to quote the version it was prepared against.")
		return
	}
	if *input.Version != current.Version {
		writeError(w, http.StatusConflict, "Stale Policy",
			"This policy has been edited since the form was opened. Reload and try again.")
		return
	}
	if strings.TrimSpace(input.Confirm) != current.PolicyNumber {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{"errors": map[string]string{
			"confirm": "Type the policy number to confirm the cancellation.",
		}})
		return
	}
	current.Status = "Cancelled"
	current.Version = current.Version + 1
	ledger.Policies[index] = current
	if err := s.Store.Write(ledger); err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unwritable", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"policy": current})
}
