package main

import (
	"net/http"
	"strings"
)

func (s *Server) handleCreate(w http.ResponseWriter, r *http.Request) {
	input, ok := decode(w, r)
	if !ok {
		return
	}
	ledger, err := s.Store.Read()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unreadable", err.Error())
		return
	}
	if errs := Validate(input, ledger, s.today(), true); len(errs) > 0 {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]any{"errors": errs})
		return
	}
	if indexOf(ledger, slug(input.PolicyNumber)) >= 0 {
		writeError(w, http.StatusConflict, "Duplicate Policy Number",
			"Policy number "+input.PolicyNumber+" is already on file.")
		return
	}
	policy := Policy{
		ID:              slug(input.PolicyNumber),
		PolicyNumber:    strings.TrimSpace(input.PolicyNumber),
		HolderEmail:     strings.TrimSpace(input.HolderEmail),
		CoverageType:    input.CoverageType,
		VehicleVIN:      strings.TrimSpace(input.VehicleVIN),
		PropertyAddress: strings.TrimSpace(input.PropertyAddress),
		StartDate:       input.StartDate,
		EndDate:         input.EndDate,
		Premium:         input.Premium,
		Status:          "Draft",
		Version:         1,
	}
	ledger.Policies = append(ledger.Policies, policy)
	if err := s.Store.Write(ledger); err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unwritable", err.Error())
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"policy": policy})
}
