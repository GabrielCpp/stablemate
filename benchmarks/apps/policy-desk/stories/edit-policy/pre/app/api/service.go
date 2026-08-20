package main

import (
	"encoding/json"
	"net/http"
	"regexp"
	"strings"
	"time"
)

// Server is the whole machine surface: seven hand-routed paths over `net/http`. Every
// route parses, calls one function, and serialises — a refusal the domain decides is the
// same refusal on the wire.
type Server struct {
	Store *Store
	// Today is the day the start-date rule is judged against. Empty means the real clock.
	Today string
}

// Routes registers every documented endpoint. The web bundle is mounted by the caller,
// under `/`, so anything not matched here is a client route.
func (s *Server) Routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /api/policies", s.handleList)
	mux.HandleFunc("POST /api/policies", s.handleCreate)
	mux.HandleFunc("DELETE /api/policies", s.handleReset)
	mux.HandleFunc("GET /api/policies/{id}", s.handleGet)
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleGet(w http.ResponseWriter, r *http.Request) {
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
	writeJSON(w, http.StatusOK, map[string]any{"policy": ledger.Policies[index]})
}

func (s *Server) handleReset(w http.ResponseWriter, _ *http.Request) {
	if err := s.Store.Write(Ledger{Policies: []Policy{}}); err != nil {
		writeError(w, http.StatusInternalServerError, "Ledger Unwritable", err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) today() string {
	if s.Today != "" {
		return s.Today
	}
	return time.Now().UTC().Format("2006-01-02")
}

func decode(w http.ResponseWriter, r *http.Request) (PolicyInput, bool) {
	var input PolicyInput
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, http.StatusBadRequest, "Unreadable Body", "The request body is not JSON.")
		return input, false
	}
	return input, true
}

func indexOf(ledger Ledger, id string) int {
	for i, policy := range ledger.Policies {
		if policy.ID == id {
			return i
		}
	}
	return -1
}

var slugPattern = regexp.MustCompile(`[^a-z0-9]+`)

// slug is how a policy number becomes an id. It is derived rather than random so that a
// deep link into a policy is writable by hand — `PN-1001` is always `/policies/pn-1001`.
func slug(policyNumber string) string {
	return strings.Trim(slugPattern.ReplaceAllString(strings.ToLower(strings.TrimSpace(policyNumber)), "-"), "-")
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, title, message string) {
	writeJSON(w, status, map[string]any{"error": map[string]string{
		"title":   title,
		"message": message,
	}})
}
