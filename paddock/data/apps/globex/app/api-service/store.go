package main

import (
	"sync"
)

// Widget is the one domain record this fixture ships: a name and a quantity on hand.
type Widget struct {
	ID       string `json:"id"`
	Name     string `json:"name"`
	Quantity int    `json:"quantity"`
}

// ErrInvalidWidget names the field a write was refused for.
type ErrInvalidWidget struct {
	Field string
}

func (e *ErrInvalidWidget) Error() string {
	return "invalid widget: " + e.Field
}

// Store is the in-memory widget ledger. A fixture has no persistence claim to prove, so
// nothing here survives a restart — unlike policy-desk's ledger, that is not this node's
// contract.
type Store struct {
	mu      sync.Mutex
	widgets []Widget
}

func (s *Store) List() []Widget {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]Widget, len(s.widgets))
	copy(out, s.widgets)
	return out
}

func (s *Store) Create(name string, quantity int) (Widget, error) {
	if name == "" {
		return Widget{}, &ErrInvalidWidget{Field: "name"}
	}
	if quantity < 0 {
		return Widget{}, &ErrInvalidWidget{Field: "quantity"}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	w := Widget{ID: nextID(len(s.widgets)), Name: name, Quantity: quantity}
	s.widgets = append(s.widgets, w)
	return w, nil
}

func nextID(count int) string {
	const letters = "abcdefghijklmnopqrstuvwxyz"
	n := count + 1
	id := ""
	for n > 0 {
		id = string(letters[(n-1)%26]) + id
		n = (n - 1) / 26
	}
	return "wg-" + id
}
