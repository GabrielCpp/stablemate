// Command claims-api serves the claims desk's machine surface. There is no client bundle
// and no second origin: every scenario against this service is an HTTP scenario, which is
// the point of the fixture — it asks whether a QA lane can prove an authorization rule with
// nothing to look at.
//
// Routing is the generated chi router rather than a hand-written mux, so the contract in
// `openapi.yml` is load-bearing at build time: an operation the document declares and the
// service does not implement is a compile error, not a 404 discovered in QA.
package main

import (
	"context"
	"flag"
	"log"
	"net/http"

	"github.com/go-chi/chi/v5"

	"example.com/claims-api/gen"
)

func main() {
	addr := flag.String("addr", ":18085", "host:port to serve on")
	data := flag.String("data", "/data/claims.json", "path to the JSON claim ledger")
	project := flag.String("project", "claims-api-example", "Firebase project the bearer tokens are issued for")
	flag.Parse()

	ctx := context.Background()
	auth, err := NewAuth(ctx, *project)
	if err != nil {
		log.Fatalf("claims-api could not reach its identity provider: %v", err)
	}

	server := &Server{Store: &Store{Path: *data}}
	router := chi.NewRouter()
	handler := gen.HandlerWithOptions(server, gen.ChiServerOptions{
		BaseRouter:  router,
		Middlewares: []gen.MiddlewareFunc{auth.Require},
	})

	log.Printf("claims-api listening on %s (ledger %s, project %s)", *addr, *data, *project)
	if err := http.ListenAndServe(*addr, handler); err != nil {
		log.Fatalf("claims-api stopped: %v", err)
	}
}
