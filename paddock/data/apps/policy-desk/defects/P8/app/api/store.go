package main

import (
	"encoding/json"
	"os"
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

// Store is the JSON-file ledger, held in memory between requests so that a desk under load
// is not re-reading and re-writing the same file for every policy it touches. The file is
// read once, on the first request the process serves.
type Store struct {
	Path string
	mu   sync.Mutex
}

var (
	ledgerCache  Ledger
	ledgerLoaded bool
)

// Read returns the ledger. A ledger that is not there yet reads as empty rather than as an
// error: an empty desk is a legitimate opening state.
func (s *Store) Read() (Ledger, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if ledgerLoaded {
		return ledgerCache, nil
	}
	raw, err := os.ReadFile(s.Path)
	if os.IsNotExist(err) {
		ledgerCache = Ledger{Policies: []Policy{}}
		ledgerLoaded = true
		return ledgerCache, nil
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
	ledgerCache = ledger
	ledgerLoaded = true
	return ledgerCache, nil
}

// Write replaces the ledger.
func (s *Store) Write(ledger Ledger) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if ledger.Policies == nil {
		ledger.Policies = []Policy{}
	}
	ledgerCache = ledger
	ledgerLoaded = true
	return nil
}
