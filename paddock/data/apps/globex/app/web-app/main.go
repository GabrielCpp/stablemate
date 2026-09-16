// Command web-app serves the widget directory's browser UI: static HTML/CSS/JS, on its
// own port, talking cross-origin to api-service. It has no server-rendered logic and no
// API routes of its own — every widget read or write the pages make is a browser request
// straight to api-service, which is why this fixture is two services rather than one with
// a web folder bolted on.
package main

import (
	"flag"
	"log"
	"net/http"
)

func main() {
	addr := flag.String("addr", ":18102", "host:port to serve on")
	static := flag.String("static", "static", "directory holding the built UI")
	flag.Parse()

	mux := http.NewServeMux()
	mux.Handle("/healthz", http.HandlerFunc(handleHealth))
	mux.Handle("/", http.FileServer(http.Dir(*static)))

	log.Printf("web-app listening on %s (static %s)", *addr, *static)
	if err := http.ListenAndServe(*addr, mux); err != nil {
		log.Fatalf("web-app stopped: %v", err)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}
