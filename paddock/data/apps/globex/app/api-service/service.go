package main

import (
	"encoding/json"
	"net/http"
)

// Server answers the widget directory's machine surface. It carries no static bundle of
// its own — that is web-app's job, on its own port — which is what makes this a
// separately addressable service rather than a route group inside a bigger process.
type Server struct {
	Store *Store
}

func (s *Server) Routes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /api/widgets", s.handleList)
	mux.HandleFunc("POST /api/widgets", s.handleCreate)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleList(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"widgets": s.Store.List()})
}

type createWidgetRequest struct {
	Name     string `json:"name"`
	Quantity int    `json:"quantity"`
}

func (s *Server) handleCreate(w http.ResponseWriter, r *http.Request) {
	var req createWidgetRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErrors(w, http.StatusUnprocessableEntity, map[string]string{"name": "could not be read"})
		return
	}
	widget, err := s.Store.Create(req.Name, req.Quantity)
	if err != nil {
		if invalid, ok := err.(*ErrInvalidWidget); ok {
			writeErrors(w, http.StatusUnprocessableEntity, map[string]string{invalid.Field: "is required or out of range"})
			return
		}
		writeErrors(w, http.StatusUnprocessableEntity, map[string]string{"name": "is required or out of range"})
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"widget": widget})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeErrors(w http.ResponseWriter, status int, errs map[string]string) {
	writeJSON(w, status, map[string]any{"errors": errs})
}
