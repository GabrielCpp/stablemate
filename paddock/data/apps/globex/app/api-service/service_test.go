package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func newTestServer() *Server {
	return &Server{Store: &Store{}}
}

func TestHandleHealth(t *testing.T) {
	s := newTestServer()
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()

	s.handleHealth(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
}

func TestHandleList(t *testing.T) {
	s := newTestServer()
	if _, err := s.Store.Create("bolt", 3); err != nil {
		t.Fatalf("seed create: %v", err)
	}
	req := httptest.NewRequest(http.MethodGet, "/api/widgets", nil)
	rec := httptest.NewRecorder()

	s.handleList(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusOK)
	}
	var body struct {
		Widgets []Widget `json:"widgets"`
	}
	if err := json.NewDecoder(rec.Body).Decode(&body); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(body.Widgets) != 1 || body.Widgets[0].Name != "bolt" {
		t.Fatalf("widgets = %+v, want one widget named bolt", body.Widgets)
	}
}

func TestHandleCreate(t *testing.T) {
	s := newTestServer()
	payload := strings.NewReader(`{"name":"bolt","quantity":3}`)
	req := httptest.NewRequest(http.MethodPost, "/api/widgets", payload)
	rec := httptest.NewRecorder()

	s.handleCreate(rec, req)

	if rec.Code != http.StatusCreated {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusCreated)
	}
}

func TestHandleCreate_InvalidQuantity(t *testing.T) {
	s := newTestServer()
	payload := strings.NewReader(`{"name":"bolt","quantity":-1}`)
	req := httptest.NewRequest(http.MethodPost, "/api/widgets", payload)
	rec := httptest.NewRecorder()

	s.handleCreate(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusUnprocessableEntity)
	}
}
