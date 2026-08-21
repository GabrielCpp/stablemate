package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Claim is one filed claim. `HolderUID` is the Firebase subject of whoever filed it and is
// the whole of the tenancy key — a claim belongs to the identity that wrote it, not to a
// tenant column somebody has to remember to filter on. `Version` is the compare-and-swap
// token a decision has to quote.
type Claim struct {
	ID           string `json:"id"`
	PolicyNumber string `json:"policy_number"`
	HolderUID    string `json:"holder_uid"`
	IncidentDate string `json:"incident_date"`
	AmountCents  int    `json:"amount_cents"`
	Description  string `json:"description"`
	Status       string `json:"status"`
	Version      int    `json:"version"`
	DecisionNote string `json:"decision_note,omitempty"`
}

// Ledger is the whole of the service's durable state.
type Ledger struct {
	Claims []Claim `json:"claims"`
	NextID int     `json:"next_id"`
}

// Store is the JSON-file ledger. It is read on every request rather than cached, and
// written by rename, so a reader never observes half a ledger and a claim written by one
// request is visible to the next rather than at the next restart.
type Store struct {
	Path string
	mu   sync.Mutex
}

// Read returns the ledger as it is on disk. A ledger that is not there yet reads as empty
// rather than as an error: an empty desk is a legitimate opening state.
func (s *Store) Read() (Ledger, error) {
	raw, err := os.ReadFile(s.Path)
	if os.IsNotExist(err) {
		return Ledger{Claims: []Claim{}, NextID: 1001}, nil
	}
	if err != nil {
		return Ledger{}, err
	}
	ledger := Ledger{Claims: []Claim{}}
	if err := json.Unmarshal(raw, &ledger); err != nil {
		return Ledger{}, err
	}
	if ledger.Claims == nil {
		ledger.Claims = []Claim{}
	}
	if ledger.NextID == 0 {
		ledger.NextID = 1001
	}
	return ledger, nil
}

// Write replaces the ledger atomically.
func (s *Store) Write(ledger Ledger) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if ledger.Claims == nil {
		ledger.Claims = []Claim{}
	}
	if err := os.MkdirAll(filepath.Dir(s.Path), 0o755); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(ledger, "", "  ")
	if err != nil {
		return err
	}
	tmp := s.Path + ".tmp"
	if err := os.WriteFile(tmp, append(raw, '\n'), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, s.Path)
}

// NextClaimID mints the next claim address and advances the counter on the ledger it is
// given. The address is derived rather than random so a scenario can name the claim it is
// about to create before it creates it.
func NextClaimID(ledger *Ledger) string {
	id := fmt.Sprintf("cl-%d", ledger.NextID)
	ledger.NextID++
	return id
}

// FindClaim returns the position of a claim in the ledger, or -1.
func FindClaim(ledger Ledger, id string) int {
	for i, claim := range ledger.Claims {
		if claim.ID == id {
			return i
		}
	}
	return -1
}
