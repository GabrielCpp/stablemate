package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sync"
)

// Policy is one insurance policy on file. `Version` is the compare-and-swap token every
// edit has to quote, and it is bumped by every write.
type Policy struct {
	ID              string  `json:"id"`
	PolicyNumber    string  `json:"policy_number"`
	HolderEmail     string  `json:"holder_email"`
	CoverageType    string  `json:"coverage_type"`
	VehicleVIN      string  `json:"vehicle_vin,omitempty"`
	PropertyAddress string  `json:"property_address,omitempty"`
	StartDate       string  `json:"start_date"`
	EndDate         string  `json:"end_date"`
	Premium         float64 `json:"premium"`
	Status          string  `json:"status"`
	Version         int     `json:"version"`
}

// Ledger is the whole of the service's durable state.
type Ledger struct {
	Policies []Policy `json:"policies"`
}

// Store is the JSON-file ledger. It is read on every request rather than cached, and
// written by rename, so a reader never observes half a ledger and a policy written by one
// process is visible to the next request rather than at the next restart.
type Store struct {
	Path string
	mu   sync.Mutex
}

// Read returns the ledger as it is on disk. A ledger that is not there yet reads as empty
// rather than as an error: an empty desk is a legitimate opening state.
func (s *Store) Read() (Ledger, error) {
	raw, err := os.ReadFile(s.Path)
	if os.IsNotExist(err) {
		return Ledger{Policies: []Policy{}}, nil
	}
	if err != nil {
		return Ledger{}, err
	}
	ledger := Ledger{Policies: []Policy{}}
	if err := json.Unmarshal(raw, &ledger); err != nil {
		return Ledger{}, err
	}
	if ledger.Policies == nil {
		ledger.Policies = []Policy{}
	}
	return ledger, nil
}

// Write replaces the ledger atomically.
func (s *Store) Write(ledger Ledger) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if ledger.Policies == nil {
		ledger.Policies = []Policy{}
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
