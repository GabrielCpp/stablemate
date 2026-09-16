// Command api-service serves the widget directory's HTTP surface on its own port, with no
// bundle attached. It is one of two separately addressable services in this fixture — see
// api-service/web-app.
package main

import (
	"flag"
	"log"
	"net/http"
)

func main() {
	addr := flag.String("addr", ":18101", "host:port to serve on")
	flag.Parse()

	server := &Server{Store: &Store{}}
	mux := http.NewServeMux()
	server.Routes(mux)

	log.Printf("api-service listening on %s", *addr)
	if err := http.ListenAndServe(*addr, allowCORS(mux)); err != nil {
		log.Fatalf("api-service stopped: %v", err)
	}
}

// allowCORS lets web-app's browser origin call this service directly. The two services
// are cross-origin by construction — this is the API a browser reaches on its own, not a
// same-origin path behind a bundle — so without this every fetch from web-app's pages
// would be refused before the handler ever ran.
func allowCORS(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}
